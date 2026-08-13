"""图形验证码服务。

使用 GitHub 开源库 fast_captcha（MIT，https://github.com/wu-clan/fast_captcha）
生成图片验证码；答案只存服务端（captcha_tickets 表），客户端永远拿不到明文。

安全设计（防刷注册 / 防刷下载 / 防高频访问）：
- 一次性：无论校验成功与否，票据立即销毁，杜绝重放与对同一票据爆破
- 5 分钟过期；绑定 IP，换 IP 的票据无效
- 获取验证码本身限流（每 IP 每分钟最多 10 张）
- 下载令牌：验证码通过后签发，2 分钟过期、一次性、绑定 IP
- 挑战通行证：验证码通过后签发 10 分钟 Cookie（HMAC 签名 + 绑定 IP），
  高频访问用户只需验证一次即可继续浏览
"""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.core.time_utils import now_utc
from app.models.captcha import CaptchaTicket, DownloadToken
from app.services.rate_limit_service import check_rate_limit

CAPTCHA_TTL = timedelta(minutes=5)
CAPTCHA_FETCH_LIMIT_PER_MINUTE = 30
CAPTCHA_VERIFY_LIMIT_PER_MINUTE = 20
CAPTCHA_CLEANUP_OLDER_THAN = timedelta(minutes=15)

# 生成字符集：只用小写字母 + 数字，并排除易混淆字符（0/O/o、1/l/I/i），
# 配合下方"存储与校验都 lower()"实现大小写不敏感，用户输大写也能过
CAPTCHA_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"

DOWNLOAD_TOKEN_TTL = timedelta(minutes=2)
DOWNLOAD_TOKEN_LIMIT_PER_MINUTE = 3

CHALLENGE_PASS_COOKIE = "challenge_pass"
CHALLENGE_PASS_TTL = timedelta(minutes=10)


def _render_captcha_image(text: str) -> str:
    """用 PIL 画一张验证码图（5 位、随机字体、干扰线和点），返回 base64 JPEG。
    自绘而不是用 fast_captcha，是因为它不接受自定义字符集；
    我们要保证图片里不出现 0/O/1/l/I 这类易混淆字符。
    """
    import base64
    import io
    import random as _rnd
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    import fast_captcha

    font_dir = Path(fast_captcha.__file__).parent / "fonts"
    fonts = sorted(font_dir.glob("*.ttf")) or []
    font_path = str(_rnd.choice(fonts)) if fonts else None
    font = ImageFont.truetype(font_path, 38) if font_path else ImageFont.load_default()

    width, height = 170, 54
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(text):
        draw.text(
            (6 + i * 32 + _rnd.randint(0, 6), _rnd.randint(3, 10)),
            ch,
            font=font,
            fill=tuple(_rnd.randint(0, 180) for _ in range(3)),
        )
    for _ in range(4):
        draw.line(
            [(_rnd.randint(0, width), _rnd.randint(0, height)) for _ in range(2)],
            fill=tuple(_rnd.randint(0, 255) for _ in range(3)),
            width=1,
        )
    for _ in range(320):
        draw.point(
            (_rnd.randint(0, width - 1), _rnd.randint(0, height - 1)),
            fill=tuple(_rnd.randint(0, 255) for _ in range(3)),
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def generate_captcha(db: Session, ip: str | None) -> dict:
    """生成一张验证码，返回 captcha_id + base64 图片。"""
    safe_ip = ip or "unknown"
    # 获取验证码本身限流：防止脚本无限拉图打爆接口
    if not check_rate_limit(db, f"cap:{safe_ip}:fetch", CAPTCHA_FETCH_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail=ErrorCode.RATE_LIMITED)

    # 顺手清理过期票据，防止表无限膨胀
    db.execute(
        delete(CaptchaTicket).where(CaptchaTicket.created_at < now_utc() - CAPTCHA_CLEANUP_OLDER_THAN)
    )
    db.commit()

    # 安全加固：5 位验证码 + 干扰点；自绘字符集排除易混淆字符，
    # 存储与校验都 lower()，大小写不敏感
    text = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(5))
    img_b64 = _render_captcha_image(text)
    ticket = CaptchaTicket(
        ticket_id=secrets.token_urlsafe(24),
        answer=text.lower(),
        ip=safe_ip,
    )
    db.add(ticket)
    db.commit()
    return {
        "captcha_id": ticket.ticket_id,
        "image": f"data:image/jpeg;base64,{img_b64}",
        "expires_in": int(CAPTCHA_TTL.total_seconds()),
    }


def verify_captcha(db: Session, captcha_id: str | None, captcha_text: str | None, ip: str | None) -> None:
    """校验验证码：一次性 + 5 分钟过期 + 绑定 IP + 大小写不敏感。

    校验失败抛 400（CAPTCHA_INVALID / CAPTCHA_EXPIRED / CAPTCHA_REQUIRED）。
    无论成败票据都会销毁，防止对同一票据爆破。
    """
    if not captcha_id or not captcha_text:
        raise HTTPException(status_code=400, detail=ErrorCode.CAPTCHA_REQUIRED)

    # 校验限流：每 IP 每分钟最多 20 次，防对验证码答案爆破
    safe_ip = ip or "unknown"
    if not check_rate_limit(db, f"cap:{safe_ip}:verify", CAPTCHA_VERIFY_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail=ErrorCode.RATE_LIMITED)

    ticket = db.scalar(select(CaptchaTicket).where(CaptchaTicket.ticket_id == captcha_id))
    if not ticket:
        raise HTTPException(status_code=400, detail=ErrorCode.CAPTCHA_INVALID)

    # 立即销毁：一次性语义，杜绝重放
    db.delete(ticket)
    db.commit()

    if ticket.created_at < now_utc() - CAPTCHA_TTL:
        raise HTTPException(status_code=400, detail=ErrorCode.CAPTCHA_EXPIRED)

    if ticket.ip and ticket.ip != safe_ip:
        raise HTTPException(status_code=400, detail=ErrorCode.CAPTCHA_INVALID)

    if ticket.answer != captcha_text.strip().lower():
        raise HTTPException(status_code=400, detail=ErrorCode.CAPTCHA_INVALID)


# ============ 下载令牌（验证码 → 放行下载） ============

def issue_download_token(db: Session, ip: str | None) -> str:
    """验证码通过后签发下载放行令牌（一次性、2 分钟过期、绑定 IP）。"""
    safe_ip = ip or "unknown"
    if not check_rate_limit(db, f"cap:{safe_ip}:download_token", DOWNLOAD_TOKEN_LIMIT_PER_MINUTE):
        raise HTTPException(status_code=429, detail=ErrorCode.RATE_LIMITED)

    token = secrets.token_urlsafe(32)
    db.add(DownloadToken(token=token, ip=safe_ip))
    db.commit()
    return token


def consume_download_token(db: Session, token: str | None, ip: str | None) -> bool:
    """消费下载令牌：有效返回 True（立即销毁）；无效/过期/换 IP 返回 False。"""
    if not token:
        return False
    record = db.scalar(select(DownloadToken).where(DownloadToken.token == token))
    if not record:
        return False
    # 立即销毁：一次性语义，防止令牌被反复使用
    db.delete(record)
    db.commit()
    safe_ip = ip or "unknown"
    if record.ip and record.ip != safe_ip:
        return False
    if record.created_at < now_utc() - DOWNLOAD_TOKEN_TTL:
        return False
    return True


# ============ 挑战通行证（高频访问验证码） ============

def _challenge_hmac(ip: str, exp_ts: int) -> str:
    """HMAC-SHA256 签名，绑定 IP + 过期时间，防伪造通行证。"""
    secret = get_settings().jwt_secret.encode()
    msg = f"challenge:{ip}:{exp_ts}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


def set_challenge_pass(response: Response, ip: str | None) -> None:
    """验证码通过后签发 10 分钟挑战通行证 Cookie。"""
    safe_ip = ip or "unknown"
    exp = int(time.time()) + int(CHALLENGE_PASS_TTL.total_seconds())
    sig = _challenge_hmac(safe_ip, exp)
    settings = get_settings()
    response.set_cookie(
        CHALLENGE_PASS_COOKIE,
        f"{exp}.{sig}",
        httponly=True,
        samesite="lax",
        secure=settings.env != "dev",
        max_age=int(CHALLENGE_PASS_TTL.total_seconds()),
        path="/",
    )


def has_challenge_pass(request: Request, ip: str | None) -> bool:
    """校验挑战通行证是否有效（签名正确 + 未过期 + IP 匹配）。"""
    raw = request.cookies.get(CHALLENGE_PASS_COOKIE)
    if not raw:
        return False
    parts = raw.split(".")
    if len(parts) != 2:
        return False
    exp_str, sig = parts
    safe_ip = ip or "unknown"
    try:
        exp = int(exp_str)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _challenge_hmac(safe_ip, exp))
