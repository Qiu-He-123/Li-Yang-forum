# -*- coding: utf-8 -*-
"""
抖音分享链接 -> 无水印直链 解析工具
====================================
粘贴抖音分享口令/短链/完整链接，直接解析出该视频的无水印 mp4 直链。

解析路径（自动降级）：
  1) Web 详情 API：登录态 Cookie + a_bogus 签名，拿到最高质量无水印直链
  2) 移动端分享页：无需 Cookie，解析页面内嵌数据，把 playwm 换成 play 去水印
  3) 浏览器兜底：Playwright 打开视频页，截获 aweme/detail 接口响应

仅供学习研究，请遵守抖音用户协议。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, quote

import httpx

# 最近一次 API 解析失败原因（供上层给出准确提示，空串=成功）
_last_api_fail: str = ""

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

UA90 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

API_BASE_PARAMS: Dict[str, Any] = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": 1,
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": 1920,
    "screen_height": 1080,
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "130.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "130.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": 12,
    "device_memory": 8,
    "platform": "PC",
}

DETAIL_ENDPOINT = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
MS_TOKEN_URL = "https://mssdk.bytedance.com/web/report"


# ---------------------------------------------------------------- 基础工具

# 作为后端服务调用时置 True，不刷屏（避免"短链/跳转/路径N"打进服务日志）
QUIET = False


def p(msg: str = "") -> None:
    if QUIET:
        return
    try:
        print(msg)
    except Exception:
        pass


def extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s\u4e00-\u9fff]+", text)
    return m.group(0).rstrip("。，；,;") if m else None


def extract_aweme_id(url: str) -> Optional[str]:
    for pat in (r"video/(\d+)", r"note/(\d+)", r"modal_id=(\d+)", r"[?&]vid=(\d+)"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def find_cookies() -> List[Dict[str, Any]]:
    candidates = [
        BASE_DIR / "cookies.json",
        BASE_DIR.parent / "通过主页获取" / "cookies.json",
        BASE_DIR.parent / "cookies.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return data
            except Exception:
                continue
    return []


def cookie_str(cookies: List[Dict[str, Any]]) -> str:
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name"))


def clean_filename(name: str, limit: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t#]', "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:limit].rstrip() if len(name) > limit else name) or "未命名"


def format_time(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(
            int(ts), tz=datetime.timezone(datetime.timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


# ---------------------------------------------------------------- 解析实现

def _gen_ms_token() -> str:
    cfg_paths = [BASE_DIR / "abogus_config.yaml", BASE_DIR.parent / "通过主页获取" / "abogus_config.yaml"]
    str_data = ""
    for path in cfg_paths:
        if path.exists():
            m = re.search(r"strData:\s*(\S+)", path.read_text(encoding="utf-8"))
            if m:
                str_data = m.group(1)
                break
    if not str_data:
        raise RuntimeError("缺少 strData 配置（abogus_config.yaml）")
    r = httpx.post(
        MS_TOKEN_URL,
        json={"magic": 538969122, "version": 1, "dataType": 8, "strData": str_data},
        headers={"User-Agent": UA90, "Content-Type": "application/json"},
        timeout=15,
    )
    return str(httpx.Cookies(r.cookies).get("msToken"))


def _signed_detail_url(aweme_id: str, ms_token: str) -> str:
    try:
        from abogus import ABogus
    except ImportError:
        # 作为后端包运行时，abogus 在 app.services.video_fetch 内
        try:
            from app.services.video_fetch.abogus import ABogus
        except ImportError:
            raise RuntimeError("缺少 abogus.py")
    params = dict(API_BASE_PARAMS)
    params.update({"aweme_id": aweme_id, "msToken": ms_token})
    bogus = ABogus().get_value(params)
    return DETAIL_ENDPOINT + "?" + urlencode(params) + "&a_bogus=" + quote(bogus, safe="")


def _item_to_record(item: Dict[str, Any], page_url: str = "") -> Dict[str, Any]:
    video_obj = item.get("video") or {}
    image_urls: List[str] = []
    for im in item.get("images") or []:
        ul = im.get("url_list") or im.get("download_url_list") or []
        if ul:
            image_urls.append(ul[0])

    video_urls: List[str] = []
    for key in ("play_addr", "download_addr"):
        for u in (video_obj.get(key) or {}).get("url_list") or []:
            if u and ".mp4" in u and u not in video_urls:
                video_urls.append(u)
    if not video_urls:
        for u in (video_obj.get("play_addr") or {}).get("url_list") or []:
            if u and u not in video_urls:
                video_urls.append(u)

    kind = "图集" if item.get("aweme_type") == 68 or image_urls else "视频"
    stats = item.get("statistics") or {}
    author = (item.get("author") or {}).get("nickname", "")
    return {
        "aweme_id": str(item.get("aweme_id", "")),
        "type": kind,
        "title": (item.get("desc") or "").strip(),
        "author": author,
        "create_time": format_time(item.get("create_time")),
        "page_url": page_url or (f"https://www.douyin.com/video/{item.get('aweme_id')}" if item.get("aweme_id") else ""),
        "video_urls": video_urls,
        "image_urls": image_urls,
        "cover": ((video_obj.get("cover") or {}).get("url_list") or [""])[0],
        "music": ((item.get("music") or {}).get("play_url", {}) or {}).get("url_list", [""])[0] if item.get("music") else "",
        "play_count": stats.get("play_count", 0),
        "digg_count": stats.get("digg_count", 0),
        "comment_count": stats.get("comment_count", 0),
        "share_count": stats.get("share_count", 0),
    }


def resolve_short_url(text: str) -> tuple[Optional[str], Optional[str]]:
    """解析分享文本，返回 (最终URL, aweme_id)。纯 HTTP，无需浏览器。"""
    url = extract_url(text)
    if not url:
        return None, None
    p(f"短链: {url}")
    try:
        r = httpx.get(url, follow_redirects=True, timeout=25, headers={"User-Agent": UA90})
        final = str(r.url)
        p(f"跳转: {final[:160]}")
        return final, extract_aweme_id(final)
    except Exception as e:
        p(f"短链解析失败: {e}")
        return None, None


def parse_by_api(aweme_id: str, cookies: List[Dict[str, Any]], attempts: int = 3) -> Optional[Dict[str, Any]]:
    """路径1：Web 详情 API + a_bogus + 登录 Cookie。

    抖音风控是瞬时/间歇的：失败自动重试 attempts 次；
    并记录具体失败原因到 _last_api_fail，供上层给出准确提示。
    """
    global _last_api_fail
    if not cookies:
        _last_api_fail = "缺少 cookies.json（未登录抖音）"
        return None
    headers = {
        "User-Agent": UA90,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie_str(cookies),
    }
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as c:
        for attempt in range(attempts):
            try:
                ms_token = _gen_ms_token()
                r = c.get(_signed_detail_url(aweme_id, ms_token))
            except Exception as e:  # noqa: BLE001
                _last_api_fail = f"接口请求失败：{e}"
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                body = r.json()
            except Exception:  # noqa: BLE001  非 JSON = 风控验证页
                _last_api_fail = "接口返回非 JSON（疑似风控拦截，需重新抓取抖音 cookies）"
                time.sleep(1.5 * (attempt + 1))
                continue
            code = body.get("status_code")
            if code != 0:
                _last_api_fail = f"接口返回 status_code={code}（风控或登录态失效，需重新抓取抖音 cookies）"
                time.sleep(1.5 * (attempt + 1))
                continue
            detail = body.get("aweme_detail") or {}
            if not detail:
                _last_api_fail = "接口无详情（视频可能已删除或私密）"
                continue
            _last_api_fail = ""
            return _item_to_record(detail, f"https://www.douyin.com/video/{aweme_id}")
    return None


def parse_by_share_page(aweme_id: str) -> Optional[Dict[str, Any]]:
    """路径2：移动端分享页（无需 Cookie），playwm 转 play 去水印。"""
    for ua in (UA_MOBILE, UA90):
        try:
            r = httpx.get(
                f"https://www.iesdouyin.com/share/video/{aweme_id}/",
                headers={"User-Agent": ua, "Referer": "https://www.douyin.com/"},
                timeout=25,
                follow_redirects=True,
            )
            txt = r.text
            m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>", txt, re.S)
            if not m:
                continue
            data = json.loads(m.group(1))
            page = (data.get("loaderData") or {}).get("video_(id)/page") or {}
            items = (page.get("videoInfoRes") or {}).get("item_list") or []
            if not items:
                continue
            item = items[0]
            play = ((item.get("video") or {}).get("play_addr") or {}).get("url_list") or []
            clean_plays = [u.replace("/playwm/", "/play/") for u in play]
            # 强制清掉视频地址里的水印参数并去重
            clean_plays = list(dict.fromkeys(clean_plays))
            record = _item_to_record(item, f"https://www.douyin.com/video/{aweme_id}")
            record["video_urls"] = clean_plays or record["video_urls"]
            return record
        except Exception:
            continue
    return None


def parse_by_browser(aweme_id: str) -> Optional[Dict[str, Any]]:
    """路径3：浏览器兜底，截获 aweme/detail 接口响应。"""
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None

    async def _run() -> Optional[Dict[str, Any]]:
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(channel="msedge", headless=False)
            except Exception:
                browser = await pw.chromium.launch(headless=False)
            ctx = await browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")
            cookies = find_cookies()
            if cookies:
                try:
                    await ctx.add_cookies(cookies)
                except Exception:
                    pass
            page = await ctx.new_page()
            result: Dict[str, Any] = {}

            async def on_response(resp: Any) -> None:
                if "aweme/v1/web/aweme/detail" in resp.url and resp.status == 200:
                    try:
                        body = await resp.json()
                        detail = body.get("aweme_detail") or {}
                        if detail and not result:
                            result.update(_item_to_record(detail, f"https://www.douyin.com/video/{aweme_id}"))
                    except Exception:
                        pass

            page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
            try:
                await page.goto(f"https://www.douyin.com/video/{aweme_id}", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(8000)
            except Exception:
                pass
            await browser.close()
            return result or None

    return asyncio.run(_run())


def save_result(record: Dict[str, Any]) -> Path:
    title = clean_filename(record.get("title") or f"视频_{record.get('aweme_id')}")
    out_dir = OUTPUT_DIR / f"{record.get('aweme_id')}_{title}"
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    for u in record["video_urls"]:
        lines.append(u)
    for u in record["image_urls"]:
        lines.append(u)
    (out_dir / "直链.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "视频信息.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_dir


def download_record(record: Dict[str, Any], out_dir: Path) -> None:
    media_dir = out_dir / "下载"
    media_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": UA_MOBILE,
        "Referer": "https://www.douyin.com/",
    }
    targets = []
    if record["video_urls"]:
        targets.append((record["video_urls"][0], f"视频_{record['aweme_id']}.mp4"))
    for i, u in enumerate(record["image_urls"], 1):
        ext = "jpg"
        m = re.search(r"\.(\w{3,4})(?:\?|$)", u)
        if m:
            ext = m.group(1)
        targets.append((u, f"图片_{i}.{ext}"))
    with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as c:
        for url, fname in targets:
            path = media_dir / fname
            if path.exists() and path.stat().st_size > 0:
                p(f"  已存在: {fname}")
                continue
            try:
                with c.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with open(path, "wb") as fh:
                        for chunk in resp.iter_bytes(65536):
                            fh.write(chunk)
                p(f"  已下载: {fname} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
            except Exception as e:
                p(f"  下载失败: {fname} - {e}")


def run_share(text: str, download: bool = False, no_cookie: bool = False) -> Optional[Dict[str, Any]]:
    final_url, aweme_id = resolve_short_url(text)
    if not aweme_id:
        p("无法从链接中解析出视频 ID，请检查链接是否正确。")
        return None

    record: Optional[Dict[str, Any]] = None
    cookies = [] if no_cookie else find_cookies()
    if cookies:
        p("路径1: Web 详情 API（登录态 + a_bogus）……")
        try:
            record = parse_by_api(aweme_id, cookies)
        except Exception as e:
            p(f"  路径1失败: {e}")
    if not record:
        p("路径2: 移动端分享页（无需 Cookie）……")
        record = parse_by_share_page(aweme_id)
    if not record:
        p("路径3: 浏览器兜底……")
        record = parse_by_browser(aweme_id)

    if not record:
        p("三条路径都失败了，可能是视频已删除/私密或风控拦截。")
        return None

    p("\n================ 解析结果 ================")
    p(f"作者: {record['author'] or '未知'}")
    p(f"标题: {record['title'][:80]}")
    p(f"类型: {record['type']} | 发布时间: {record['create_time']}")
    p(f"播放: {record['play_count']} | 点赞: {record['digg_count']} | 评论: {record['comment_count']}")
    p(f"作品页: {record['page_url']}")
    for u in record["video_urls"]:
        p(f"无水印直链: {u}")
    for u in record["image_urls"]:
        p(f"图片直链: {u}")

    out_dir = save_result(record)
    p(f"\n已保存到: {out_dir}")
    if download:
        p("开始下载……")
        download_record(record, out_dir)
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description="抖音分享链接 -> 无水印直链")
    ap.add_argument("text", nargs="?", help="抖音分享口令/短链/完整链接")
    ap.add_argument("--download", action="store_true", help="解析后直接下载")
    ap.add_argument("--no-cookie", action="store_true", help="强制不走登录态，仅用移动端分享页")
    args = ap.parse_args()

    if args.text:
        run_share(args.text, download=args.download, no_cookie=args.no_cookie)
        return

    p("=" * 58)
    p("  抖音分享链接 -> 无水印直链")
    p("  粘贴分享口令/链接即可（Ctrl+Z 退出）")
    p("=" * 58)
    while True:
        try:
            text = input("\n请输入分享链接/口令: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if text:
            run_share(text)


if __name__ == "__main__":
    main()
