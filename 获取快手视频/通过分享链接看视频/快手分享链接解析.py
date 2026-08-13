# -*- coding: utf-8 -*-
"""
快手分享链接 -> 视频直链
======================
输入快手分享链接(如 https://v.kuaishou.com/JMmLg1n1)，解析出无水印视频直链
(h264/h265，含全部清晰度)，并验证直链可访问。

注意: 请使用分享链接(v.kuaishou.com/xxx 或带分享参数的视频页)。
      纯作品ID / 裸视频页链接 通常返回不含视频数据的精简页面，解析不到直链。

用法:
    python 快手分享链接解析.py https://v.kuaishou.com/JMmLg1n1
    python 快手分享链接解析.py "链接1" "链接2" ...

依赖: 纯 Python 标准库，无需第三方包

原理: 分享链接会 302 跳到 www.kuaishou.com/short-video/{作品ID}，
      页面 HTML 内嵌 window.__APOLLO_STATE__，其中 VisionVideoDetailPhoto
      对象带有 photoUrl / photoH265Url / videoResource(多清晰度) 字段。
      参考 GitHub 开源项目 CharlesPikachu/videodl 的 kuaishou.py。
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
OUT_FILE = Path(__file__).resolve().parent / f"解析结果_{datetime.now():%Y%m%d_%H%M}.txt"


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
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Referer": "https://www.kuaishou.com/"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", "ignore")
                final_url = resp.geturl()
            if "VisionVideoDetailPhoto" in html:
                return final_url, html
            last = f"页面缺少作品数据(len={len(html)})"
        except Exception as e:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="快手分享链接解析为视频直链")
    ap.add_argument("links", nargs="+", help="分享链接 / 视频页链接 / 作品ID")
    args = ap.parse_args()

    lines = []
    for link in args.links:
        print(f"正在解析: {link}", flush=True)
        try:
            final_url, html = fetch_page(normalize_input(link))
        except Exception as e:
            msg = f"请求失败: {e}"
            print(" ", msg)
            lines.append(f"{link}\n  {msg}\n")
            continue

        pid = re.search(r"/short-video/([A-Za-z0-9_-]+)", final_url)
        pid = pid.group(1) if pid else ""
        print(f"  作品ID: {pid}")

        photo = parse_photo(html)
        if not photo:
            msg = "页面里没有解析到作品数据。请使用分享链接(v.kuaishou.com/xxx)重试；纯作品ID/裸链接无法解析。"
            print(" ", msg)
            lines.append(f"{link} -> {final_url}\n  {msg}\n")
            continue

        urls = collect_urls(photo)
        if not urls:
            msg = "没有找到视频直链(该作品可能是图文/图集)"
            print(" ", msg)
            lines.append(f"{link} -> {final_url}\n  {msg}\n")
            continue

        lines.append(f"链接: {link}\n作品ID: {pid}\n最终页: {final_url}")
        print(f"  标题: {str(photo.get('caption') or '')[:60]}")
        for label, u in urls:
            ok = verify_url(u)
            status = "可访问" if ok else "不可访问"
            print(f"  [{label}] {status}: {u}")
            lines.append(f"[{label}] ({status}) {u}")
        lines.append("")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n结果已保存: {OUT_FILE}")


if __name__ == "__main__":
    main()
