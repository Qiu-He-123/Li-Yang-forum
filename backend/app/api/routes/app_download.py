"""手机端 APK 下载中转（防刷下载 / 防带宽被打满）。

流程：
1. 前端弹验证码，用户通过后 POST /api/app-download/token 换取一次性下载令牌
2. 浏览器跳转 GET /api/app-download?token=xxx 下载

防护：
- 图形验证码：下载前必须通过（一次性、2 分钟过期、绑定 IP）
- 应用层限流：每 IP 每小时最多 5 次、每天最多 20 次
- Nginx 层：独立限频（6 次/分）+ 限速（512KB/s）+ 限并发（同 IP 2 连接）

部署约定：把编译好的 APK 放进 backend/static/ 目录即可，
本接口自动选择目录里最新的 .apk 返回；无需改代码、无需重启
（每次请求实时读取磁盘，新包放进去立即生效）。
"""

import html
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.models import AppDownloadLog
from app.schemas.common import ok
from app.services.captcha_service import (
    consume_download_token,
    issue_download_token as create_download_token,
    verify_captcha,
)
from app.services.rate_limit_service import check_rate_limit

router = APIRouter(prefix="/api/app-download", tags=["app"])

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"

# 下载限流：每 IP 每小时、每天各限一次（验证码仍防刷，阈值放宽避免误触发）
DL_HOURLY_LIMIT = 20
DL_DAILY_LIMIT = 60


class DownloadTokenIn(BaseModel):
    captcha_id: str | None = Field(default=None, min_length=1, max_length=64)
    captcha_text: str | None = Field(default=None, min_length=1, max_length=16)


_VERSION_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)", re.IGNORECASE)


def _version_key(path: Path) -> tuple:
    """按文件名里的版本号取排序键；解析失败时回退到修改时间。

    优先版本号而不是 mtime：多个 APK 的 mtime 可能完全相同（如同一批解压/复制），
    max() 并列时只会取到名称靠前的旧版，导致明明有新包却一直下发旧包。
    """
    m = _VERSION_RE.search(path.name)
    if m:
        return (1, tuple(int(x) for x in m.groups()), path.stat().st_mtime)
    return (0, (0, 0, 0), path.stat().st_mtime)


def _error_page(msg: str, status: int = 400) -> HTMLResponse:
    """下载失败时返回中文提示页（HTTP 非 200）。

    不能用 HTTP 200 + JSON 当下载响应：浏览器/手机只会按扩展名把它
    存成 .apk，一安装就报「安装包已损坏」——这正是下载拿不到真包时的假象。
    返回 4xx + HTML，浏览器直接渲染提示，不再保存坏文件。
    """
    body = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh;margin:0;background:#f5f6f8;color:#1f2329}"
        ".card{background:#fff;padding:36px 28px;border-radius:16px;box-shadow:0 6px 30px "
        "rgba(0,0,0,.08);text-align:center;max-width:340px}"
        "h1{font-size:18px;margin:0 0 12px}"
        "p{font-size:14px;color:#5a6068;margin:0 0 20px;line-height:1.7}"
        "a{display:inline-block;background:#f4645f;color:#fff;text-decoration:none;"
        "padding:10px 26px;border-radius:10px;font-size:14px}</style></head>"
        "<body><div class='card'><h1>下载未完成</h1><p>{MSG}</p>"
        "<a href='javascript:history.back()'>返回重新下载</a></div></body></html>"
    ).replace("{MSG}", html.escape(msg))
    return HTMLResponse(content=body, status_code=status)


def _find_apk() -> Path | None:
    """返回 backend/static 目录中版本号最高的 .apk 文件。"""
    try:
        candidates = [p for p in _STATIC_DIR.glob("*.apk") if p.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=_version_key)


def _record_download(request: Request, db: Session) -> None:
    """记录一次下载（IP / UA），供后台数据看板统计。"""
    db.add(
        AppDownloadLog(
            ip=extract_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    db.commit()


def issue_download_token(request: Request, payload: DownloadTokenIn, db: Session = Depends(get_db)) -> dict:
    """验证码通过后签发一次性下载令牌。"""
    ip = extract_ip(request)
    verify_captcha(db, payload.captcha_id, payload.captcha_text, ip)
    token = create_download_token(db, ip)
    return ok({"download_token": token, "expires_in": 120})


@router.get("")
def app_download(request: Request, db: Session = Depends(get_db)):
    """验证码放行后返回服务器 backend/static 里最新的 APK。"""
    ip = extract_ip(request)
    safe_ip = ip or "unknown"

    # 1. 应用层限流：每 IP 每小时最多 5 次、每天最多 20 次
    if not check_rate_limit(db, f"dl:{safe_ip}:hour", DL_HOURLY_LIMIT, window_seconds=3600):
        return _error_page("下载太频繁，请稍后再试（每小时限 20 次，每天限 60 次）")
    if not check_rate_limit(db, f"dl:{safe_ip}:day", DL_DAILY_LIMIT, window_seconds=86400):
        return _error_page("今日下载次数已达上限，请明天再试")

    # 2. 下载令牌校验：必须先过验证码（一次性、2 分钟、绑定 IP）
    token = request.query_params.get("token")
    if not consume_download_token(db, token, ip):
        return _error_page("下载凭证无效或已过期，请返回页面完成验证码验证后再下载")

    apk = _find_apk()
    if not apk:
        return _error_page("安装包暂未上传，请联系管理员", 404)
    _record_download(request, db)
    return FileResponse(
        apk,
        media_type="application/vnd.android.package-archive",
        filename=apk.name,
        # 禁止浏览器缓存：每次点击都拿服务器上的最新 APK，避免下到旧包
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
