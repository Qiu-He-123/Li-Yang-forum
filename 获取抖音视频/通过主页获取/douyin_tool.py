# -*- coding: utf-8 -*-
"""
抖音作者视频库拉取工具
========================
输入作者抖音号/昵称 -> 搜索并选择作者 -> 自动拉取该作者的全部作品链接。

两种引擎：
  1) 浏览器引擎（默认）：Playwright 驱动本机 Edge，自动滚动作者主页，
     从网络请求中抓取 aweme/post 接口数据。最稳定，不受签名算法变动影响。
  2) API 引擎（快速模式）：使用登录 Cookie + msToken + a_bogus 签名，
     直接分页调用 aweme/v1/web/aweme/post/ 接口。适合已拿到 sec_uid 的场景。

首次使用需要在本机浏览器里登录一次抖音，登录态会保存在 cookies.json，
之后自动复用，过期时窗口会再次弹出要求登录。

仅供学习研究，请遵守抖音用户协议并控制请求频率。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import httpx

try:
    import playwright
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except Exception:  # pragma: no cover
    HAS_PLAYWRIGHT = False

BASE_DIR = Path(__file__).resolve().parent
COOKIE_FILE = BASE_DIR / "cookies.json"
OUTPUT_DIR = BASE_DIR / "output"
AUTHORS_FILE = BASE_DIR / "authors.txt"

# 与 abogus.py 中写死的签名 UA 保持一致，否则 a_bogus 会被风控拒绝
UA90 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
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

SEARCH_ENDPOINT = "https://www.douyin.com/aweme/v1/web/discover/search/"
POST_ENDPOINT = "https://www.douyin.com/aweme/v1/web/aweme/post/"
MS_TOKEN_URL = "https://mssdk.bytedance.com/web/report"


# ---------------------------------------------------------------- 工具函数

def p(msg: str = "") -> None:
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        except Exception:
            pass


def clean_filename(name: str, limit: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t#]', "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    if len(name) > limit:
        name = name[:limit].rstrip()
    return name or "未命名"


def extract_sec_uid(text: str) -> Optional[str]:
    """从主页链接 / 分享口令中提取 sec_uid。"""
    m = re.search(r"user/([A-Za-z0-9_-]{10,})", text)
    if m:
        return m.group(1)
    m = re.search(r"sec_uid=([A-Za-z0-9_-]{10,})", text)
    if m:
        return m.group(1)
    return None


def extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s\u4e00-\u9fff]+", text)
    return m.group(0).rstrip("。，；,;") if m else None


def load_cookies() -> List[Dict[str, Any]]:
    if COOKIE_FILE.exists():
        try:
            data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def cookie_str(cookies: List[Dict[str, Any]]) -> str:
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name"))


def import_cookie_string(cookie_line: str) -> int:
    """把浏览器复制的 Cookie 字符串（k=v; k2=v2）保存为 cookies.json。"""
    cookie_line = cookie_line.strip()
    if cookie_line.startswith("{") or cookie_line.lower().endswith(".json"):
        # 直接给 JSON 文件路径：使用现成的 list 格式
        path = Path(cookie_line)
        if not path.exists():
            raise FileNotFoundError(f"找不到 Cookie 文件: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            COOKIE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return len(data)
        raise ValueError("Cookie JSON 必须是 [{name,value,domain,...}, ...] 列表格式")

    parsed: List[Dict[str, Any]] = []
    for part in cookie_line.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        parsed.append(
            {
                "name": k,
                "value": v,
                "domain": ".douyin.com",
                "path": "/",
                "secure": False,
                "httpOnly": False,
            }
        )
    if not parsed:
        raise ValueError("没有解析到任何 Cookie，请检查格式（分号分隔的 k=v）")
    COOKIE_FILE.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(parsed)


async def save_cookies(ctx: Any) -> None:
    cookies = await ctx.cookies()
    COOKIE_FILE.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def format_time(ts: Any) -> str:
    if not ts:
        return ""
    try:
        ts = int(ts)
        return datetime.datetime.fromtimestamp(
            ts, tz=datetime.timezone(datetime.timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


# ---------------------------------------------------------------- 作品解析

def extract_item(v: Dict[str, Any]) -> Dict[str, Any]:
    aweme_id = str(v.get("aweme_id", ""))
    desc = (v.get("desc") or "").strip()
    aweme_type = v.get("aweme_type")
    video_obj = v.get("video") or {}

    image_urls: List[str] = []
    for im in v.get("images") or []:
        ul = im.get("url_list") or im.get("download_url_list") or []
        if ul:
            image_urls.append(ul[0])

    kind = "图集" if aweme_type == 68 or image_urls else "视频"
    video_urls: List[str] = []
    if kind == "视频":
        for key in ("play_addr", "download_addr"):
            for u in (video_obj.get(key) or {}).get("url_list") or []:
                if u and ".mp4" in u and u not in video_urls:
                    video_urls.append(u)
        if not video_urls:
            for u in (video_obj.get("play_addr") or {}).get("url_list") or []:
                if u and u not in video_urls:
                    video_urls.append(u)
    stats = v.get("statistics") or {}
    author = (v.get("author") or {}).get("nickname", "")

    return {
        "aweme_id": aweme_id,
        "type": kind,
        "aweme_type": aweme_type,
        "title": desc,
        "create_time": format_time(v.get("create_time")),
        "page_url": f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "",
        "video_urls": video_urls,
        "image_urls": image_urls,
        "play_count": stats.get("play_count", 0),
        "digg_count": stats.get("digg_count", 0),
        "comment_count": stats.get("comment_count", 0),
        "share_count": stats.get("share_count", 0),
        "collect_count": stats.get("collect_count", 0),
        "author": author,
    }


def save_outputs(author: Dict[str, Any], records: List[Dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    page_lines = [r["page_url"] for r in records if r["page_url"]]
    (out_dir / "视频链接.txt").write_text("\n".join(page_lines) + "\n", encoding="utf-8")

    direct_lines = []
    for r in records:
        for u in r["video_urls"]:
            direct_lines.append(f"{r['title']}\t{r['page_url']}\t{u}")
        for u in r["image_urls"]:
            direct_lines.append(f"{r['title']}\t{r['page_url']}\t{u}")
    (out_dir / "直链列表.txt").write_text("\n".join(direct_lines) + "\n", encoding="utf-8")

    payload = {
        "author": author,
        "total": len(records),
        "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "videos": records,
    }
    (out_dir / "视频信息.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with open(out_dir / "视频信息.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "序号", "作品ID", "类型", "标题", "发布时间", "作品链接",
                "视频直链", "图片直链", "播放", "点赞", "评论", "分享", "收藏",
            ]
        )
        for i, r in enumerate(records, 1):
            w.writerow(
                [
                    i,
                    r["aweme_id"],
                    r["type"],
                    r["title"],
                    r["create_time"],
                    r["page_url"],
                    " | ".join(r["video_urls"]),
                    " | ".join(r["image_urls"]),
                    r["play_count"],
                    r["digg_count"],
                    r["comment_count"],
                    r["share_count"],
                    r["collect_count"],
                ]
            )

    p(f"\n已保存到: {out_dir}")
    p(f"  视频链接.txt   (作品页链接 {len(page_lines)} 条)")
    p(f"  直链列表.txt   (视频/图片直链)")
    p(f"  视频信息.csv / 视频信息.json")
    return out_dir


# ---------------------------------------------------------------- 下载

def download_records(records: List[Dict[str, Any]], out_dir: Path, cookies: List[Dict[str, Any]]) -> None:
    media_dir = out_dir / "下载"
    media_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": UA90,
        "Referer": "https://www.douyin.com/",
        "Cookie": cookie_str(cookies),
    }
    ok, fail = 0, 0
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as c:
        for i, r in enumerate(records, 1):
            targets = []
            if r["video_urls"]:
                targets = [("mp4", r["video_urls"][0], f"{i:04d}_{clean_filename(r['title'])}_{r['aweme_id']}.mp4")]
            elif r["image_urls"]:
                targets = [
                    ("jpg", u, f"{i:04d}_{clean_filename(r['title'])}_{r['aweme_id']}_{j}.jpg")
                    for j, u in enumerate(r["image_urls"], 1)
                ]
            for kind, url, fname in targets:
                path = media_dir / fname
                if path.exists() and path.stat().st_size > 0:
                    ok += 1
                    continue
                for attempt in range(1, 4):
                    try:
                        with c.stream("GET", url) as resp:
                            resp.raise_for_status()
                            with open(path, "wb") as fh:
                                for chunk in resp.iter_bytes(65536):
                                    fh.write(chunk)
                        ok += 1
                        break
                    except Exception as e:
                        if attempt == 3:
                            fail += 1
                            p(f"  下载失败 [{i}]: {fname} - {e}")
                        else:
                            time.sleep(2)
            if i % 10 == 0:
                p(f"  进度: {i}/{len(records)} 成功 {ok} 失败 {fail}")
    p(f"\n下载完成: 成功 {ok} 个文件, 失败 {fail} 个 -> {media_dir}")


# ---------------------------------------------------------------- API 引擎

def _gen_ms_token() -> str:
    cfg = (BASE_DIR / "abogus_config.yaml")
    if cfg.exists():
        text = cfg.read_text(encoding="utf-8")
        m = re.search(r"strData:\s*(\S+)", text)
        str_data = m.group(1) if m else ""
    else:
        # 兼容旧路径：从项目内默认配置读取
        m = re.search(r"strData:\s*(\S+)", (BASE_DIR / "config.yaml").read_text(encoding="utf-8"))
        str_data = m.group(1) if m else ""
    if not str_data:
        raise RuntimeError("缺少 strData 配置，无法生成 msToken")
    r = httpx.post(
        MS_TOKEN_URL,
        json={"magic": 538969122, "version": 1, "dataType": 8, "strData": str_data},
        headers={"User-Agent": UA90, "Content-Type": "application/json"},
        timeout=15,
    )
    return str(httpx.Cookies(r.cookies).get("msToken"))


def _signed_url(endpoint: str, params: Dict[str, Any], ms_token: str) -> str:
    try:
        from abogus import ABogus
    except ImportError:
        raise RuntimeError("缺少 abogus.py，无法生成 a_bogus 签名")
    p = dict(params)
    p["msToken"] = ms_token
    bogus = ABogus().get_value(p)
    return endpoint + "?" + urlencode(p) + "&a_bogus=" + quote(bogus, safe="")


def fetch_posts_api(sec_uid: str, cookies: List[Dict[str, Any]], max_pages: int = 5000) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": UA90,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie_str(cookies),
    }
    ms_token = _gen_ms_token()
    records: List[Dict[str, Any]] = []
    seen: set = set()
    cursor = 0
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as c:
        for page in range(1, max_pages + 1):
            params = dict(API_BASE_PARAMS)
            params.update(
                {
                    "sec_user_id": sec_uid,
                    "max_cursor": cursor,
                    "count": 18,
                    "locate_query": "false",
                    "show_live_replay_strategy": 1,
                    "need_time_list": 1,
                    "time_list_query": 0,
                    "publish_video_strategy_type": 2,
                }
            )
            url = _signed_url(POST_ENDPOINT, params, ms_token)
            resp = c.get(url)
            body = resp.json()
            code = body.get("status_code")
            if code not in (0, 5):
                raise RuntimeError(f"接口返回异常 status_code={code}: {str(body)[:200]}")
            items = body.get("aweme_list") or []
            added = 0
            for v in items:
                aid = str(v.get("aweme_id", ""))
                if aid and aid not in seen:
                    seen.add(aid)
                    records.append(extract_item(v))
                    added += 1
            p(f"  API 第 {page} 页: 新增 {added} 条, 累计 {len(records)} 条, has_more={body.get('has_more')}")
            if not body.get("has_more"):
                break
            cursor = body.get("max_cursor", cursor)
            if not items:
                break
            time.sleep(0.5)
    return records


# ---------------------------------------------------------------- 浏览器引擎

async def _launch(pw: Any) -> Any:
    try:
        return await pw.chromium.launch(channel="msedge", headless=False)
    except Exception:
        return await pw.chromium.launch(headless=False)


async def _ensure_login(page: Any, ctx: Any) -> bool:
    try:
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass
    await page.wait_for_timeout(3000)
    cks = await ctx.cookies()
    if any(c["name"] in ("sessionid", "sid_tt", "sessionid_ss") for c in cks):
        return True
    try:
        await page.get_by_text("登录", exact=True).first.click(timeout=5000)
    except Exception:
        pass
    p("浏览器窗口已打开，请在窗口内完成抖音登录（App 扫码最快），等待中……")
    deadline = time.time() + 420
    while time.time() < deadline:
        await page.wait_for_timeout(4000)
        cks = await ctx.cookies()
        if any(c["name"] in ("sessionid", "sid_tt", "sessionid_ss") for c in cks):
            await page.wait_for_timeout(2500)
            await save_cookies(ctx)
            p("登录成功，登录态已保存到 cookies.json。")
            return True
    p("登录超时（7 分钟未检测到登录），请重新运行。")
    return False


async def search_author(page: Any, keyword: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set = set()

    async def on_response(resp: Any) -> None:
        if "discover/search" in resp.url and resp.status == 200:
            try:
                body = await resp.json()
                for u in body.get("user_list") or []:
                    ui = u.get("user_info") or {}
                    sid = ui.get("sec_uid")
                    if sid and sid not in seen:
                        seen.add(sid)
                        results.append(ui)
            except Exception:
                pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    await page.goto(
        f"https://www.douyin.com/search/{quote(keyword)}?type=user",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    await page.wait_for_timeout(6000)
    for _ in range(4):
        await page.mouse.wheel(0, 1500)
        await page.wait_for_timeout(1800)
    return results


async def fetch_posts_browser(page: Any, sec_uid: str, max_scrolls: int = 400) -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    seen: set = set()

    async def on_response(resp: Any) -> None:
        if "aweme/v1/web/aweme/post" in resp.url and resp.status == 200:
            try:
                body = await resp.json()
                for v in body.get("aweme_list") or []:
                    aid = str(v.get("aweme_id", ""))
                    if aid and aid not in seen:
                        seen.add(aid)
                        posts.append(v)
            except Exception:
                pass

    page.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    await page.goto(f"https://www.douyin.com/user/{sec_uid}", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(5000)
    empty_rounds = 0
    for i in range(1, max_scrolls + 1):
        before = len(posts)
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(1100)
        if len(posts) == before:
            empty_rounds += 1
        else:
            empty_rounds = 0
        if i % 20 == 0:
            p(f"  滚动加载中…… 已滚动 {i} 次, 当前 {len(posts)} 个作品")
        if empty_rounds >= 6:
            p(f"  连续 {empty_rounds} 次没有新作品，认为已到底。")
            break
    return posts


async def resolve_share_link(page: Any, text: str) -> str:
    """把分享口令/短链解析成最终 URL。"""
    url = extract_url(text)
    if not url:
        return ""
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)
    return page.url


async def run_browser_job(keywords: List[str], download: bool = False, max_scrolls: int = 400) -> None:
    if not HAS_PLAYWRIGHT:
        p("未安装 playwright，请先执行: pip install playwright")
        return
    async with async_playwright() as pw:
        browser = await _launch(pw)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")
        cks = load_cookies()
        if cks:
            try:
                await ctx.add_cookies(cks)
            except Exception:
                pass
        page = await ctx.new_page()
        if not await _ensure_login(page, ctx):
            await browser.close()
            return

        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            p(f"\n================ 处理: {kw} ================")
            sec_uid = extract_sec_uid(kw)
            author: Dict[str, Any] = {}
            if not sec_uid and "douyin.com" in kw:
                final = await resolve_share_link(page, kw)
                sec_uid = extract_sec_uid(final)
                if not sec_uid:
                    p(f"  无法从链接解析作者: {kw}")
                    continue
                p(f"  链接已解析 -> sec_uid: {sec_uid}")
            if not sec_uid:
                users = await search_author(page, kw)
                exact = [u for u in users if u.get("unique_id") == kw]
                candidates = exact or users
                if not candidates:
                    p(f"  未搜索到作者: {kw}")
                    continue
                if len(candidates) == 1:
                    ui = candidates[0]
                else:
                    p(f"  找到 {len(candidates)} 个候选作者：")
                    for idx, u in enumerate(candidates[:15], 1):
                        p(
                            f"    [{idx}] {u.get('nickname')} | 抖音号: {u.get('unique_id')} "
                            f"| 粉丝: {u.get('follower_count')} | 获赞: {u.get('total_favorited')} "
                            f"| {u.get('enterprise_verify_reason') or u.get('custom_verify') or ''}"
                        )
                    try:
                        choice = input("  输入序号选择作者（直接回车选 1）: ").strip()
                    except Exception:
                        choice = ""
                    idx = int(choice) - 1 if choice.isdigit() else 0
                    if idx < 0 or idx >= len(candidates):
                        idx = 0
                    ui = candidates[idx]
                sec_uid = ui.get("sec_uid")
                author = {
                    "nickname": ui.get("nickname", ""),
                    "unique_id": ui.get("unique_id", ""),
                    "follower_count": ui.get("follower_count", 0),
                    "total_favorited": ui.get("total_favorited", 0),
                    "verify": ui.get("enterprise_verify_reason") or ui.get("custom_verify") or "",
                    "sec_uid": sec_uid,
                }
                p(
                    f"  选中: {author['nickname']} (抖音号 {author['unique_id']}), "
                    f"粉丝 {author['follower_count']}"
                )

            if not author:
                author = {"sec_uid": sec_uid, "nickname": kw}
            p("  正在打开作者主页并滚动加载全部作品……")
            posts = await fetch_posts_browser(page, sec_uid, max_scrolls=max_scrolls)
            records = [extract_item(v) for v in posts]
            p(f"  共获取 {len(records)} 个作品")
            out_dir = OUTPUT_DIR / clean_filename(author.get("nickname") or kw or sec_uid)
            save_outputs(author, records, out_dir)
            if download and records:
                download_records(records, out_dir, await ctx.cookies())
        await browser.close()


def resolve_sec_uid_http(text: str) -> Optional[str]:
    """纯 HTTP 方式把主页链接/分享口令解析成 sec_uid（无需浏览器）。"""
    sid = extract_sec_uid(text)
    if sid:
        return sid
    url = extract_url(text)
    if not url:
        return None
    try:
        r = httpx.get(url, follow_redirects=True, timeout=20, headers={"User-Agent": UA90})
        return extract_sec_uid(str(r.url))
    except Exception:
        return None


def run_api_job(sec_uid: str, download: bool = False) -> None:
    cookies = load_cookies()
    if not cookies:
        p("快速 API 模式需要登录态。请先运行一次浏览器模式完成登录，")
        p("或用 --set-cookie \"k=v; k2=v2\" 粘贴你浏览器里的 Cookie。")
        return
    target = sec_uid.strip()
    if "douyin.com" in target or extract_url(target):
        resolved = resolve_sec_uid_http(target)
        if not resolved:
            p(f"无法从链接解析出 sec_uid: {target}")
            return
        p(f"链接已解析 -> sec_uid: {resolved}")
        target = resolved
    p(f"使用 API 引擎拉取 sec_uid={target} 的全部作品……")
    records = fetch_posts_api(target, cookies)
    p(f"共获取 {len(records)} 个作品")
    out_dir = OUTPUT_DIR / f"api_{target[:12]}"
    save_outputs({"sec_uid": target, "nickname": f"API_{target[:12]}"}, records, out_dir)
    if download and records:
        download_records(records, out_dir, cookies)


# ---------------------------------------------------------------- 交互入口

def read_author_file(path: Path) -> List[str]:
    if not path.exists():
        p(f"找不到文件: {path}")
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def interactive() -> None:
    p("=" * 58)
    p("  抖音作者视频库拉取工具")
    p("  输入作者抖音号/昵称，即可拉取该作者的全部作品链接")
    p("=" * 58)
    p("1. 按抖音号/昵称搜索作者并拉取全部作品")
    p("2. 输入作者主页链接/分享口令")
    p("3. 批量处理（每行一个，见 authors.txt）")
    p("4. 快速 API 模式（输入 sec_uid，用登录态直连接口）")
    p("5. 退出")
    while True:
        try:
            choice = input("\n请选择 [1-5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice == "5":
            return
        if choice == "1":
            kw = input("输入作者抖音号或昵称: ").strip()
            if kw:
                asyncio.run(run_browser_job([kw]))
        elif choice == "2":
            text = input("粘贴作者主页链接 / 分享口令: ").strip()
            if text:
                asyncio.run(run_browser_job([text]))
        elif choice == "3":
            kws = read_author_file(AUTHORS_FILE)
            if kws:
                asyncio.run(run_browser_job(kws))
        elif choice == "4":
            sid = input("输入 sec_uid 或主页链接: ").strip()
            sid2 = extract_sec_uid(sid) or sid
            if sid2:
                run_api_job(sid2)
        else:
            p("无效选择")


def main() -> None:
    ap = argparse.ArgumentParser(description="抖音作者视频库拉取工具")
    ap.add_argument("keyword", nargs="?", help="作者抖音号/昵称/主页链接")
    ap.add_argument("--url", help="作者主页链接或分享口令")
    ap.add_argument("--file", help="批量作者列表文件，每行一个")
    ap.add_argument("--api", help="快速 API 模式，传入 sec_uid")
    ap.add_argument("--set-cookie", help="粘贴浏览器 Cookie 字符串或 Cookie JSON 文件路径")
    ap.add_argument("--download", action="store_true", help="同时下载视频/图片")
    ap.add_argument("--max-scrolls", type=int, default=400, help="浏览器模式最大滚动次数")
    args = ap.parse_args()

    if args.set_cookie:
        try:
            n = import_cookie_string(args.set_cookie)
            p(f"Cookie 已导入 {n} 条 -> cookies.json")
        except Exception as e:
            p(f"导入失败: {e}")
    elif args.keyword:
        asyncio.run(run_browser_job([args.keyword], download=args.download, max_scrolls=args.max_scrolls))
    elif args.url:
        asyncio.run(run_browser_job([args.url], download=args.download, max_scrolls=args.max_scrolls))
    elif args.file:
        kws = read_author_file(Path(args.file))
        if kws:
            asyncio.run(run_browser_job(kws, download=args.download, max_scrolls=args.max_scrolls))
    elif args.api:
        run_api_job(extract_sec_uid(args.api) or args.api, download=args.download)
    else:
        interactive()


if __name__ == "__main__":
    main()
