"""手机端 APK 下载中转。

网页端左上角「下载手机端」按钮指向本接口：后端解析蓝奏云分享链接，
拿到临时直链后 302 跳转，浏览器直接开始下载 APK。

蓝奏云有 JS 反爬（acw_sc__v2 cookie 挑战），这里用纯 Python 复刻其生成算法，
无需外部服务；直链缓存 10 分钟，解析失败时回退到蓝奏云分享页。
"""

import json
import re
import time

import requests
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from loguru import logger

router = APIRouter(prefix="/api/app-download", tags=["app"])

LANZOU_SHARE_URL = "https://wwaox.lanzouu.com/iVeQ741sql0b"
LANZOU_PASSWORD = "gwfm"
_CACHE_TTL = 600

_BASE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# 蓝奏云自定义 base64 字母表（小写在前）
_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/="

_cache: dict = {"url": None, "ts": 0.0}


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


def _fetch_real_page(session: requests.Session) -> str:
    """抓分享页；遇到验证挑战则解 cookie 后重试。"""
    resp = session.get(LANZOU_SHARE_URL, timeout=15)
    html = resp.text
    if "var arg1=" in html:
        cookie = _solve_acw_cookie(html)
        session.cookies.set("acw_sc__v2", cookie.split("=", 1)[1])
        resp = session.get(LANZOU_SHARE_URL, timeout=15)
        html = resp.text
    return html


def _resolve_direct_url() -> str:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _BASE_UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
    )
    html = _fetch_real_page(session)
    m = re.search(r"ajaxm\.php\?file=(\d+)", html)
    if not m:
        raise RuntimeError("分享页结构解析失败")
    file_id = m.group(1)
    signs = re.findall(r"'sign':'([^']+)'", html)
    if not signs:
        raise RuntimeError("未找到下载签名")
    for sign in signs:
        try:
            resp = session.post(
                f"https://wwaox.lanzouu.com/ajaxm.php?file={file_id}",
                data={
                    "action": "downprocess",
                    "sign": sign,
                    "kd": 1,
                    "p": LANZOU_PASSWORD,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": LANZOU_SHARE_URL,
                },
                timeout=15,
            )
            data = json.loads(resp.text)
            if data.get("zt") == 1 and data.get("dom") and data.get("url"):
                return data["dom"] + data["url"]
        except Exception:
            continue
    raise RuntimeError("未取到可用直链")


@router.get("")
def app_download() -> RedirectResponse:
    """点击后直接下载手机端 APK（302 到蓝奏云直链）。"""
    cached = _cache.get("url")
    if cached and time.time() - _cache.get("ts", 0) < _CACHE_TTL:
        return RedirectResponse(cached, status_code=302)
    try:
        direct = _resolve_direct_url()
        _cache["url"] = direct
        _cache["ts"] = time.time()
        return RedirectResponse(direct, status_code=302)
    except Exception as exc:
        logger.warning("APK 直链解析失败，回退到分享页: {}", exc)
        return RedirectResponse(LANZOU_SHARE_URL, status_code=302)
