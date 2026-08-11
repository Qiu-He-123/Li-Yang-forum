"""手机端 APK 下载中转。

网页端左上角「下载手机端」按钮指向本接口，行为：

1. 从微云笔记（WEIYUN_NOTICE_URL）读取「更新地址{...}」字段作为下载地址，
   直接 302 跳转到该页面（蓝奏云分享页），用户在原页面下载；
2. 不硬编码蓝奏云链接/密码——以后发新版只需：蓝奏云上传新 APK →
   把新的分享链接写进微云笔记「更新地址」，无需改代码、无需重启；
3. 笔记里没配下载地址时，退回本机 static/ 目录的 APK（兜底，避免入口失效）。

说明：蓝奏云的直链令牌只能由真实浏览器兑现，服务端解析出来的直链
浏览器访问会返回「文件未授权」，所以这里不解析直链，直接跳分享页。
"""

import html as _html
import json
import re
import time
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.models import AppDownloadLog

router = APIRouter(prefix="/api/app-download", tags=["app"])

# 微云笔记：维护「更新地址」「密码」字段（改地址只改笔记）
WEIYUN_NOTICE_URL = "https://share.weiyun.com/SpmKBnmC"
_CACHE_TTL = 600
# 兜底：笔记未配置地址时提供本机 APK
_APK_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "static" / "立洋社区-v1.0.1正式版.apk"
)

_BASE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_notice_cache: dict = {"fields": None, "ts": 0.0}


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


def _record_download(request: Request, db: Session) -> None:
    """记录一次下载点击（IP / UA），供后台数据看板统计。"""
    db.add(
        AppDownloadLog(
            ip=extract_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    db.commit()


@router.get("")
def app_download(request: Request, db: Session = Depends(get_db)):
    """手机端下载：跳转到微云笔记里配置的蓝奏云下载地址（不写死）。"""
    fields = _fetch_notice_fields()
    share_url = fields.get("更新地址") or fields.get("下载地址")
    if not share_url:
        # 笔记没配地址：退回本机静态 APK 兜底，避免下载入口失效
        if _APK_PATH.exists():
            _record_download(request, db)
            return FileResponse(
                _APK_PATH,
                media_type="application/vnd.android.package-archive",
                filename=_APK_PATH.name,
            )
        logger.warning("微云笔记未配置下载地址，且无本地 APK")
        return RedirectResponse("/", status_code=302)
    _record_download(request, db)
    return RedirectResponse(share_url, status_code=302)
