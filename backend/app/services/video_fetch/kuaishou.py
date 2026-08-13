# -*- coding: utf-8 -*-
"""
快手分享链接 -> 视频直链（后端集成封装）。

来源：D:/Users/Downloads/立洋社区/获取快手视频/通过分享链接看视频/快手分享链接解析.py
在原解析函数（normalize_input / fetch_page / parse_photo / collect_urls /
verify_url）基础上，新增统一的 parse_share(text) 入口，供 video_service 调用。

原理：分享链接 302 跳到 www.kuaishou.com/short-video/{作品ID}，页面 HTML 内嵌
window.__APOLLO_STATE__，其中 VisionVideoDetailPhoto 对象带 photoUrl /
photoH265Url / videoResource 字段。纯 Python 标准库，无第三方依赖。
"""

import json
import re
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def normalize_input(link: str) -> str:
    link = link.strip()
    if "kuaishou.com" not in link and "gifshow.com" not in link:
        # 视为纯作品ID
        return f"https://www.kuaishou.com/short-video/{link}"
    return link


def fetch_page(url: str, retries: int = 3):
    """跟随跳转并返回 (最终URL, HTML)，失败自动重试。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                return resp.geturl(), html
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if i < retries - 1:
            time.sleep(3 * (i + 1))
    raise RuntimeError(last or "请求失败")


def parse_photo(html: str) -> dict:
    m = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        return {}
    data = json.loads(m.group(1))
    client = data.get("defaultClient", {})
    for v in client.values():
        if isinstance(v, dict) and v.get("__typename") == "VisionVideoDetailPhoto":
            return v
    return {}


def collect_urls(photo: dict) -> list:
    """收集所有可用的视频直链: [(清晰度/编码, URL), ...]"""
    urls = []
    if photo.get("photoUrl"):
        urls.append(("h264(默认)", photo["photoUrl"]))
    if photo.get("photoH265Url"):
        urls.append(("h265(默认)", photo["photoH265Url"]))
    vr = photo.get("videoResource") or {}
    js = vr.get("json") or {}
    if isinstance(js, str):
        try:
            js = json.loads(js)
        except Exception:
            js = {}
    for codec in ("h264", "hevc"):
        for aset in (js.get(codec, {}) or {}).get("adaptationSet", []) or []:
            for rep in aset.get("representation", []) or []:
                if rep.get("url"):
                    label = rep.get("qualityLabel") or rep.get("id") or ""
                    urls.append((f"{codec}({label})" if label else codec, rep["url"]))
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
                "User-Agent": UA,
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
    # 封面：常见字段 coverUrl / photo.coverUrl
    cover = photo.get("coverUrl") or ""
    if not cover:
        cover_info = photo.get("coverInfo") or {}
        if isinstance(cover_info, dict):
            cover = cover_info.get("url") or ""
    title = photo.get("caption") or photo.get("desc") or ""
    author = (photo.get("user") or {}).get("name") if isinstance(photo.get("user"), dict) else ""
    return {
        "platform": "kuaishou",
        "title": str(title).strip(),
        "cover": str(cover).strip(),
        "video_urls": [str(video_url).strip()] if video_url else [],
        "video_url": str(video_url).strip(),
        "author": str(author or "").strip(),
    }
