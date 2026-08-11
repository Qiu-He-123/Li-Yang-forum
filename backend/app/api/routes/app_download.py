"""手机端 APK 下载中转。

网页端左上角「下载手机端」按钮指向本接口：后端解析蓝奏云分享链接，
拿到临时直链后 302 跳转，浏览器直接开始下载 APK。

蓝奏云有 JS 反爬（acw_sc__v2 cookie 挑战），这里用纯 Python 复刻其生成算法，
无需外部服务；直链缓存 10 分钟，解析失败时回退到蓝奏云分享页。

注意：蓝奏云直链令牌只能由真实浏览器兑现（服务端解析出来的直链，
浏览器访问会返回「文件未授权」）。因此优先直接提供本机部署的 APK
（backend/static/），蓝奏云解析仅作为 APK 文件缺失时的后备。

下载地址与密码不写死：从微云笔记（WEIYUN_NOTICE_URL）的
「更新地址{...}」「密码{...}」字段读取，改地址只需改笔记，无需改代码。
"""

import html as _html
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.models import AppDownloadLog

router = APIRouter(prefix="/api/app-download", tags=["app"])

# 微云笔记：里面维护「更新地址」和「密码」两个字段，作为蓝奏云下载源
WEIYUN_NOTICE_URL = "https://share.weiyun.com/SpmKBnmC"
_CACHE_TTL = 600
# 本机部署的 APK（随仓库提交，替换新版本时直接覆盖这个文件即可）
_APK_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "static" / "立洋社区-v1.0.1正式版.apk"
)

_BASE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# 蓝奏云自定义 base64 字母表（小写在前）
_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/="

_cache: dict = {"url": None, "ts": 0.0}
_notice_cache: dict = {"fields": None, "ts": 0.0}


def _custom_b64(s: str) -> bytes:
    """按蓝奏云自定义字母表解码。"""
    vals = [_ALPHA.index(c) for c in s if c in _ALPHA]
    bits = ""
    out = bytearray()
    for v in vals:
        bits += f"{v:06b}"
        while len(bits) >= 8:
            out.append(int(bits[:8], 2))
            bits = bits[8:]
    return bytes(out)


def _solve_acw_cookie(html: str) -> str:
    """复刻蓝奏云 acw_sc__v2 验证 cookie 生成算法。"""
    arg1 = re.search(r"var arg1='([^']+)'", html).group(1)
    m = [int(x, 16) for x in re.search(r"var m=\[(.*?)\]", html).group(1).split(",")]
    n_list = re.findall(r"'([^']*)'", re.search(r"var N=\[(.*?)\];", html, re.S).group(1))
    decoded = [_custom_b64(x).decode("utf-8", errors="replace") for x in n_list]
    # XOR 密钥是一长串纯数字，找到它并旋转数组使密钥落在索引 26
    key_idx = next(i for i, d in enumerate(decoded) if re.fullmatch(r"\d{30,}", d))
    rot = (key_idx - 26) % len(decoded)
    rotated = decoded[rot:] + decoded[:rot]
    p = rotated[26]
    q = [None] * len(m)
    for x, ch in enumerate(arg1):
        for z in range(len(m)):
            if m[z] == x + 1:
                q[z] = ch
    u = "".join(q)
    v = "".join(
        format(int(u[x : x + 2], 16) ^ int(p[x : x + 2], 16), "02x")
        for x in range(0, min(len(u), len(p)), 2)
    )
    return "acw_sc__v2=" + v


def _fetch_real_page(session: requests.Session, share_url: str) -> str:
    """抓分享页；遇到验证挑战则解 cookie 后重试。"""
    resp = session.get(share_url, timeout=15)
    html = resp.text
    if "var arg1=" in html:
        cookie = _solve_acw_cookie(html)
        session.cookies.set("acw_sc__v2", cookie.split("=", 1)[1])
        resp = session.get(share_url, timeout=15)
        html = resp.text
    return html


def _resolve_direct_url(share_url: str, password: str) -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _BASE_UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    )
    html = _fetch_real_page(session, share_url)
    m = re.search(r"ajaxm\.php\?file=(\d+)", html)
    if not m:
        raise RuntimeError("分享页结构解析失败")
    file_id = m.group(1)
    parsed = urlparse(share_url)
    host_base = f"{parsed.scheme}://{parsed.netloc}"
    signs = re.findall(r"'sign':'([^']+)'", html)
    if not signs:
        raise RuntimeError("未找到下载签名")
    for sign in signs:
        try:
            resp = session.post(
                f"{host_base}/ajaxm.php?file={file_id}",
                data={
                    "action": "downprocess",
                    "sign": sign,
                    "kd": 1,
                    "p": password,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": share_url,
                },
                timeout=15,
            )
            data = json.loads(resp.text)
            if data.get("zt") == 1 and data.get("dom") and data.get("url"):
                return data["dom"] + data["url"]
        except Exception:
            continue
    raise RuntimeError("未取到可用直链")


def _fetch_notice_fields() -> dict[str, str]:
    """从微云笔记读取「标签{内容}」字段（含更新地址/密码），缓存 10 分钟。"""
    cached = _notice_cache.get("fields")
    if cached and time.time() - _notice_cache.get("ts", 0) < _CACHE_TTL:
        return cached
    try:
        resp = requests.get(
            WEIYUN_NOTICE_URL,
            headers={
                "User-Agent": _BASE_UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            timeout=15,
        )
        fields = _parse_notice_fields(resp.text)
        _notice_cache["fields"] = fields
        _notice_cache["ts"] = time.time()
        return fields
    except Exception as exc:
        logger.warning("微云笔记读取失败: {}", exc)
        return _notice_cache.get("fields") or {}


def _parse_notice_fields(html_text: str) -> dict[str, str]:
    """解析微云笔记：window.syncData → 第一条笔记 → 逐行「标签{内容}」。"""
    m = re.search(r"window\.syncData\s*=\s*(\{.*?\})\s*;", html_text, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
        share = data.get("shareInfo") or data
        notes = share.get("note_list") or []
        if not notes:
            return {}
        content = notes[0].get("html_content") or notes[0].get("note_title") or ""
    except Exception:
        return {}
    plain = _html.unescape(re.sub(r"<[^>]+>", "\n", content))
    fields: dict[str, str] = {}
    for raw in plain.split("\n"):
        line = raw.strip()
        fm = re.match(r"^(.+?)\{(.*)\}$", line)
        if fm:
            fields[fm.group(1).strip()] = fm.group(2).strip()
    return fields


@router.get("")
def app_download(request: Request, db: Session = Depends(get_db)):
    """点击后直接下载手机端 APK。

    优先返回本机 static/ 目录里的 APK（真实可靠、无第三方反爬限制）；
    文件缺失时按微云笔记中的「更新地址/密码」走蓝奏云解析，失败回退分享页。
    """
    if _APK_PATH.exists():
        # 记录一次下载（IP / UA），供后台数据看板统计下载数与独立 IP
        db.add(
            AppDownloadLog(
                ip=extract_ip(request),
                user_agent=(request.headers.get("user-agent") or "")[:255],
            )
        )
        db.commit()
        return FileResponse(
            _APK_PATH,
            media_type="application/vnd.android.package-archive",
            filename=_APK_PATH.name,
        )
    fields = _fetch_notice_fields()
    share_url = fields.get("更新地址") or fields.get("下载地址")
    password = fields.get("密码") or fields.get("下载密码")
    if not share_url:
        logger.warning("微云笔记中未配置下载地址")
        return RedirectResponse("/", status_code=302)
    if password:
        cached = _cache.get("url")
        if cached and time.time() - _cache.get("ts", 0) < _CACHE_TTL:
            return RedirectResponse(cached, status_code=302)
        try:
            direct = _resolve_direct_url(share_url, password)
            _cache["url"] = direct
            _cache["ts"] = time.time()
            return RedirectResponse(direct, status_code=302)
        except Exception as exc:
            logger.warning("APK 直链解析失败，回退到分享页: {}", exc)
    return RedirectResponse(share_url, status_code=302)
