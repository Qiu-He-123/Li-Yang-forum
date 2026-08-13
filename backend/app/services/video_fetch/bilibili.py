# -*- coding: utf-8 -*-
"""
B站分享链接 -> 视频直链（后端集成）。

流程：分享文本提链（b23.tv 短链 / 完整URL / BV号 / av号）-> view API
拿 cid/标题/封面 -> playurl API（fnval=0, qn=64）拿单文件 mp4 直链（含音轨）。

注意：B站 CDN（bilivideo.com）有 Referer 校验（必须 bilibili.com），
浏览器跨站播放走本站 /api/videos/proxy 反代（与抖音一致）。
匿名可拿 480p；更高清晰度需要登录 cookies（SESSDATA），暂不接。
"""

import re

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BILI_REFERER = "https://www.bilibili.com/"

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_API = "https://api.bilibili.com/x/player/playurl"

_cookie_jar: str = ""


def _get_cookie_jar() -> str:
    """访问 B站首页拿 buvid3/b_nut cookie（B站风控要求，否则接口 412）。"""
    global _cookie_jar
    if _cookie_jar:
        return _cookie_jar
    try:
        r = httpx.get("https://www.bilibili.com/", headers={"User-Agent": UA}, timeout=20)
        jar = "; ".join(f"{k}={v}" for k, v in r.cookies.items())
        if jar:
            _cookie_jar = jar
    except Exception:
        pass
    return _cookie_jar


def _headers() -> dict:
    """完整浏览器指纹头 + cookie（实测可稳定过 B站风控，命中率 6/6）。"""
    return {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": BILI_REFERER,
        "Origin": "https://www.bilibili.com",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cookie": _get_cookie_jar(),
    }


def _extract_bvid(text: str) -> str | None:
    m = re.search(r"(BV[0-9A-Za-z]{10})", text)
    if m:
        return m.group(1)
    m = re.search(r"av(\d+)", text)
    if m:
        return "av" + m.group(1)
    stripped = text.strip()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", stripped):
        return stripped
    return None


def _resolve_short(text: str) -> str:
    """提取链接；b23.tv 短链跟随跳转拿真实视频页 URL。"""
    m = re.search(r"https?://[^\s\u4e00-\u9fff]+", text)
    if not m:
        return text
    url = m.group(0).rstrip("。，；,;")
    if "b23.tv" in url:
        try:
            r = httpx.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=20)
            return str(r.url)
        except Exception:
            return url
    return url


def parse_share(text: str) -> dict:
    """解析 B 站分享链接，返回 {platform, title, cover, video_urls, video_url, author}。"""
    final_url = _resolve_short(text or "")
    bvid = _extract_bvid(final_url)
    if not bvid:
        raise RuntimeError("未识别到 B 站视频号（BV/av 号），请确认分享链接正确")

    headers = _headers()
    params = {"bvid": bvid} if bvid.startswith("BV") else {"aid": bvid[2:]}
    view = None
    last_err = None
    for attempt in range(3):
        try:
            resp = httpx.get(VIEW_API, params=params, headers=headers, timeout=20)
            view = resp.json()
            break
        except Exception as exc:  # noqa: BLE001  空响应/风控瞬时抖动，重试
            last_err = exc
            import time as _t

            _t.sleep(0.8 * (attempt + 1))
    if view is None:
        raise RuntimeError(f"B 站接口请求失败：{last_err}")
    if view.get("code") != 0:
        raise RuntimeError(f"B 站接口返回异常：{view.get('message')}")
    data = view.get("data") or {}
    if not data:
        raise RuntimeError("B 站接口无数据（视频可能不存在/已删除）")
    cid = data.get("cid")
    if not cid:
        pages = data.get("pages") or []
        cid = pages[0].get("cid") if pages else None
    if not cid:
        raise RuntimeError("B 站接口缺少 cid")

    play = httpx.get(
        PLAYURL_API,
        params={"bvid": bvid, "cid": cid, "fnval": 0, "qn": 64},
        headers=headers,
        timeout=20,
    ).json()
    durl = ((play.get("data") or {}).get("durl")) or []
    urls = [d.get("url") for d in durl if d.get("url")]
    if not urls:
        raise RuntimeError("未拿到 B 站视频直链（可能需要登录）")

    return {
        "platform": "bilibili",
        "title": (data.get("title") or "").strip(),
        "cover": data.get("pic") or "",
        "video_urls": urls,
        "video_url": urls[0],
        "author": ((data.get("owner") or {}).get("name") or "").strip(),
    }
