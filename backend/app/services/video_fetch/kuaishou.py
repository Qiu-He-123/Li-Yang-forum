# -*- coding: utf-8 -*-
"""
快手分享链接 -> 视频直链（后端集成封装）。

新版原理（快手已改版，旧 __APOLLO_STATE__ 页面不再内嵌作品数据）：
- 分享链接用移动端 UA 访问，302 跳到 v.m.chenzhongtech.com/fw/photo/{作品ID}
- 页面 HTML 内嵌 window.INIT_STATE（键名做了 +1 混淆，但值完整），
  其中含 photoType（VIDEO/IMAGE）、manifest.adaptationSet[].representation[].url（多清晰度直链）、
  coverUrls、caption、userName 等。
- 兼容旧路径：部分页面仍有 __APOLLO_STATE__ 的 VisionVideoDetailPhoto，保留兜底。
纯 Python 标准库，无第三方依赖。
"""

import json
import re
import time
import urllib.request

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


def normalize_input(link: str) -> str:
    link = (link or "").strip()
    # 分享文本常带描述文字（"它在做什么？...打开快手观看"）：
    # 只取其中的 URL，否则整段文本会被当成链接打开报错
    m = re.search(r"https?://[^\s\u4e00-\u9fff\"'“”]+", link)
    if m:
        link = m.group(0).rstrip("。，；,;")
    if "kuaishou.com" not in link and "gifshow.com" not in link and "chenzhongtech.com" not in link:
        # 视为纯作品ID
        return f"https://www.kuaishou.com/short-video/{link}"
    return link


def fetch_page(url: str, retries: int = 3):
    """用移动端 UA 跟随跳转并返回 (最终URL, HTML)，失败自动重试。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA_MOBILE})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                return resp.geturl(), html
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if i < retries - 1:
            time.sleep(2 * (i + 1))
    raise RuntimeError(last or "请求失败")


def _extract_js_object(html: str, var: str) -> dict | None:
    """提取 window.XXX = {...} 的完整 JSON（用 raw_decode 正确处理字符串内花括号）。"""
    m = re.search(re.escape(f"window.{var}") + r"\s*=\s*", html)
    if not m:
        return None
    i = html.find("{", m.end())
    if i < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html[i:])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _find_photo_obj(o) -> dict | None:
    """在解析后的 JSON 里递归找作品对象（含 photoType 字段的那个）。"""
    if isinstance(o, dict):
        if "photoType" in o:
            return o
        for v in o.values():
            r = _find_photo_obj(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_photo_obj(v)
            if r:
                return r
    return None


def parse_photo(html: str) -> dict:
    """从页面提取作品对象。优先新结构 INIT_STATE，兜底旧结构 __APOLLO_STATE__。"""
    # 新：移动端页面 window.INIT_STATE
    data = _extract_js_object(html, "INIT_STATE")
    if data:
        photo = _find_photo_obj(data)
        if photo:
            return photo
    # 旧：桌面端 window.__APOLLO_STATE__ 里的 VisionVideoDetailPhoto
    data = _extract_js_object(html, "__APOLLO_STATE__")
    if data:
        client = data.get("defaultClient", {})
        for v in client.values():
            if isinstance(v, dict) and v.get("__typename") == "VisionVideoDetailPhoto":
                return v
    return {}


def collect_urls(photo: dict) -> list:
    """收集所有可用的视频直链: [(清晰度/编码, URL), ...]"""
    urls = []
    man = photo.get("manifest") or {}
    for aset in man.get("adaptationSet") or []:
        for rep in aset.get("representation") or []:
            u = rep.get("url")
            if u:
                q = rep.get("qualityLabel") or rep.get("quality") or ""
                urls.append((str(q) if q else "default", u))
    # mainMvUrls / photoUrl / photoH265Url 兜底
    for u in photo.get("mainMvUrls") or []:
        if isinstance(u, str) and u:
            urls.append(("main", u))
    for k, label in (("photoUrl", "h264"), ("photoH265Url", "h265")):
        u = photo.get(k)
        if u:
            urls.append((label, u))
    # 去重保序
    seen, result = set(), []
    for label, u in urls:
        if u not in seen:
            seen.add(u)
            result.append((label, u))
    return result


def verify_url(url: str) -> bool:
    """用 Range 请求验证直链是否可访问。"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA_MOBILE,
                "Referer": "https://www.kuaishou.com/",
                "Range": "bytes=0-1023",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 206)
    except Exception:
        return False


def parse_share(text: str) -> dict:
    """解析快手分享链接，返回统一 record：
    {platform, title, cover, video_url, author}
    """
    final_url, html = fetch_page(normalize_input(text))
    photo = parse_photo(html)
    if not photo:
        raise RuntimeError("页面里没有解析到作品数据，请使用快手分享链接（v.kuaishou.com/xxx）")
    ptype = str(photo.get("photoType") or "")
    if ptype.upper() in ("IMAGE", "图片"):
        raise RuntimeError("该作品是图文/图集，暂不支持解析为视频")
    urls = collect_urls(photo)
    if not urls:
        raise RuntimeError("没有找到视频直链（该作品可能是图文/图集）")
    video_url = urls[0][1]
    if not verify_url(video_url):
        # 默认直链失效时，尝试下一个
        for _, u in urls[1:]:
            if verify_url(u):
                video_url = u
                break
    # 封面
    cover = ""
    covers = photo.get("coverUrls") or photo.get("webpCoverUrls") or []
    if covers and isinstance(covers[0], dict):
        cover = covers[0].get("url") or ""
    if not cover:
        cover = photo.get("coverUrl") or ""
    title = photo.get("caption") or photo.get("desc") or ""
    author = photo.get("userName") or photo.get("user_name") or ""
    if isinstance(author, dict):
        author = author.get("name") or ""
    return {
        "platform": "kuaishou",
        "title": str(title).strip(),
        "cover": str(cover).strip(),
        "video_urls": [str(video_url).strip()] if video_url else [],
        "video_url": str(video_url).strip(),
        "author": str(author or "").strip(),
    }
