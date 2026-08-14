# -*- coding: utf-8 -*-
"""
B站分享链接 -> 视频直链（后端集成）。

流程：分享文本提链（b23.tv 短链 / 完整URL / BV号 / av号）-> view API
拿 cid/标题/封面 -> playurl API（fnval=0, qn=64）拿单文件 mp4 直链（含音轨）。

注意：B站 CDN（bilivideo.com）有 Referer 校验（必须 bilibili.com），
浏览器跨站播放走本站 /api/videos/proxy 反代（与抖音一致）。
匿名可拿 480p；更高清晰度需要登录 cookies（SESSDATA），暂不接。
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BILI_REFERER = "https://www.bilibili.com/"

VIEW_API = "https://api.bilibili.com/x/web-interface/view"
PLAYURL_API = "https://api.bilibili.com/x/player/playurl"
PGC_PLAYURL_API = "https://api.bilibili.com/pgc/player/web/playurl"
UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "uploads"

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


def _extract_ep_id(text: str) -> str | None:
    m = re.search(r"ep(\d+)", text)
    return m.group(1) if m else None


def _extract_ss_id(text: str) -> str | None:
    m = re.search(r"ss(\d+)", text)
    return m.group(1) if m else None


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


def _extract_json_var(html: str, var: str) -> dict | None:
    """提取页面里 `var = {...}` 形式的完整 JSON（raw_decode 正确处理字符串内花括号）。"""
    m = re.search(re.escape(var) + r"\s*=\s*", html)
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


def _parse_next_data(html: str) -> dict | None:
    """提取 Next.js 的 __NEXT_DATA__ JSON（番剧标题/封面/作者等）。"""
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _try_pgc_durl(ep_id: int | None, cid: int) -> list[str]:
    """免费集可通过 PGC playurl 接口拿单文件 mp4（部分需登录/大会员，拿不到返回空）。"""
    if not ep_id:
        return []
    try:
        j = httpx.get(
            PGC_PLAYURL_API,
            params={"ep_id": ep_id, "cid": cid, "qn": 64, "fnval": 0, "platform": "pc"},
            headers=_headers(), timeout=20,
        ).json()
        durl = ((j.get("data") or {}).get("durl")) or []
        return [d.get("url") for d in durl if d.get("url")]
    except Exception:
        return []


def _merge_dash(video: dict, audio: dict, cid: int) -> str | None:
    """下载 DASH 视频/音频流，ffmpeg -c copy 合并为单文件 mp4（按 cid 缓存）。

    PGC 接口对未登录用户不返回 durl，但页面 SSR 内嵌完整 DASH 流；
    取最小清晰度视频+音频，流复制合并（秒级，不转码）。返回本地 /uploads 路径。
    """
    out_path = UPLOAD_ROOT / "videos" / "bangumi" / f"{cid}.mp4"
    if out_path.exists() and out_path.stat().st_size > 0:
        return f"/uploads/videos/bangumi/{cid}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hdr = {"User-Agent": UA, "Referer": "https://www.bilibili.com/bangumi/play/"}
    tmp = Path(tempfile.mkdtemp())
    try:
        for name, stream in (("v.m4s", video), ("a.m4s", audio)):
            url = stream.get("base_url") or ""
            if not url:
                return None
            r = httpx.get(url, headers=hdr, timeout=300)
            if r.status_code != 200 or not r.content:
                return None
            (tmp / name).write_bytes(r.content)
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(tmp / "v.m4s"), "-i", str(tmp / "a.m4s"),
             "-c", "copy", "-movflags", "+faststart", str(out_path)],
            capture_output=True, text=True, timeout=900,
        )
        if r.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            return None
        return f"/uploads/videos/bangumi/{cid}.mp4"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_bangumi(ep_id: str | None, ss_id: str | None) -> dict:
    """解析 B 站番剧/剧集链接（PGC）。

    ep{集数id} / ss{季id}：抓播放页，从 SSR 的 playurlSSRData 拿 cid + DASH 流，
    从 __NEXT_DATA__ 拿标题/封面/作者；直链优先 PGC playurl 接口（免费集），
    拿不到则下载最小 DASH 视频+音频用 ffmpeg 合并为单文件 mp4（按 cid 缓存）。
    """
    key = f"ep{ep_id}" if ep_id else f"ss{ss_id}"
    try:
        page = httpx.get(
            f"https://www.bilibili.com/bangumi/play/{key}",
            headers={"User-Agent": UA}, timeout=25, follow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"番剧页面请求失败：{exc}") from exc
    html = page.text

    ssr = _extract_json_var(html, "const playurlSSRData")
    if not ssr:
        raise RuntimeError("番剧页面缺少播放数据（可能需登录/已下架）")
    result = ((ssr.get("data") or {}).get("result")) or {}
    arc = result.get("arc") or {}
    cid = arc.get("cid")
    if not cid:
        raise RuntimeError("番剧页面缺少 cid")
    ep_info = result.get("episode_info") or {}
    ep_id = ep_info.get("ep_id") or ep_id

    title, cover, author = "", "", ""
    nd = _parse_next_data(html)
    if nd:
        props = (nd.get("props") or {}).get("pageProps") or {}
        queries = ((props.get("dehydratedState") or {}).get("queries")) or []
        if queries:
            sdata = (queries[0].get("state") or {}).get("data") or {}
            title = sdata.get("season_title") or sdata.get("title") or ""
            cover = sdata.get("cover") or sdata.get("square_cover") or ""
            author = ((sdata.get("up_info") or {}).get("uname")) or ""
    if not title:
        title = "B站番剧"

    # 直链：优先 PGC 接口（免费集单文件 mp4）；拿不到则 DASH 合并
    urls = _try_pgc_durl(ep_id, cid)
    if not urls:
        dash = ((result.get("video_info") or {}).get("dash")) or {}
        videos = [v for v in (dash.get("video") or []) if v.get("base_url")]
        audios = [a for a in (dash.get("audio") or []) if a.get("base_url")]
        if not videos or not audios:
            raise RuntimeError("番剧接口无可用直链（该剧可能需大会员/已下架）")
        videos.sort(key=lambda v: v.get("size") or 0)
        audios.sort(key=lambda a: a.get("size") or 0)
        local = _merge_dash(videos[0], audios[0], int(cid))
        if not local:
            raise RuntimeError("番剧视频下载/合并失败，请稍后重试")
        urls = [local]

    return {
        "platform": "bilibili",
        "title": str(title).strip(),
        "cover": str(cover).strip(),
        "video_urls": urls,
        "video_url": urls[0],
        "author": str(author or "").strip(),
    }


def parse_share(text: str) -> dict:
    """解析 B 站分享链接，返回 {platform, title, cover, video_urls, video_url, author}。"""
    final_url = _resolve_short(text or "")
    # 番剧（bangumi）：ep{集数} / ss{季} 走 PGC 接口
    ep_id = _extract_ep_id(final_url)
    ss_id = _extract_ss_id(final_url)
    if ep_id or ss_id:
        return _parse_bangumi(ep_id, ss_id)
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
