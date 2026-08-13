"""抖音 / 快手分享视频 -> 论坛视频帖（独立「视频」频道）。

流程：粘贴分享口令/链接 -> 解析无水印直链 -> 下载 -> ffmpeg 转码压缩
-> 存 uploads/videos/ -> 发布到「视频」圈子（category=视频），帖子带
video_urls + 封面图。前端 feed 直接 <video> 播放，点进详情是视频体验。

解析复用 获取抖音视频 / 获取快手视频 的实现（backend/app/services/video_fetch/）。
"""

import hashlib
import json
import logging
import re
import time
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models import Post, User
from app.schemas.post import PostCreate
from app.services import post_service, wechat_local

logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path(__file__).resolve().parents[3] / "backend" / "uploads"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

VIDEO_CATEGORY = "视频"

# 解析结果缓存：预览->发布 不再重复解析（抖音解析要多次网络调用，约 3-4 秒）
_parse_cache: dict[str, tuple[float, dict]] = {}
_PARSE_CACHE_TTL = 300  # 5 分钟
# 封面 URL -> 本地路径 缓存（封面带签名，1 小时内复用）
_cover_cache: dict[str, tuple[float, str]] = {}
_COVER_CACHE_TTL = 3600


def parse_share(text: str, use_cache: bool = True) -> dict:
    """识别平台并解析分享链接，返回 {platform, title, cover, video_url, author}。"""
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请粘贴抖音/快手分享链接")
    cache_key = hashlib.md5(text.encode("utf-8")).hexdigest()
    if use_cache:
        hit = _parse_cache.get(cache_key)
        if hit and time.time() - hit[0] < _PARSE_CACHE_TTL:
            return hit[1]
    low = text
    if "kuaishou.com" in low or "gifshow.com" in low or "快手" in low:
        from app.services.video_fetch import kuaishou

        try:
            record = kuaishou.parse_share(text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"快手解析失败：{exc}") from exc
    elif "bilibili.com" in low or "b23.tv" in low or "哔哩" in low or re.search(r"BV[0-9A-Za-z]{10}", low):
        from app.services.video_fetch import bilibili

        try:
            record = bilibili.parse_share(text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"B站解析失败：{exc}") from exc
    else:
        record = _parse_douyin(text)
    if not record.get("video_url"):
        raise HTTPException(status_code=400, detail="未解析到视频直链，请确认分享链接正确")
    _parse_cache[cache_key] = (time.time(), record)
    return record


def _parse_douyin(text: str) -> dict:
    """解析抖音分享链接（走底层函数，不写 output 文件、不刷屏）。

    路径1：Web 详情 API（登录态 cookies + a_bogus 签名）——需要 cookies.json；
    路径2：移动端分享页（无需 Cookie，但抖音改版后经常拿不到视频数据）；
    路径3：浏览器兜底（需 playwright，未安装时跳过）。
    """
    from app.services.video_fetch import douyin_share

    douyin_share.QUIET = True  # 服务端调用：不往日志刷解析过程

    _, aweme_id = douyin_share.resolve_short_url(text)
    if not aweme_id:
        raise HTTPException(status_code=400, detail="无法从链接中解析出视频 ID，请检查链接是否正确")

    record = None
    cookies = douyin_share.find_cookies()
    if cookies:
        try:
            record = douyin_share.parse_by_api(aweme_id, cookies)
        except Exception:
            record = None
    if not record:
        try:
            record = douyin_share.parse_by_share_page(aweme_id)
        except Exception:
            record = None
    if not record:
        try:
            record = douyin_share.parse_by_browser(aweme_id)
        except Exception:
            record = None
    if not record or not record.get("video_urls"):
        raise HTTPException(
            status_code=400,
            detail="抖音解析失败（可能是视频已删除/私密、风控拦截，或登录 cookies 过期）",
        )
    return {
        "platform": "douyin",
        "title": record.get("title") or "",
        "cover": record.get("cover") or "",
        "video_urls": record.get("video_urls") or [],
        "video_url": (record.get("video_urls") or [""])[0],
        "author": record.get("author") or "",
    }


def _download(url: str, timeout: float = 180, referer: str | None = None,
              kind: str = "video") -> bytes | None:
    """下载资源并校验内容（拒绝 HTML 错误页/防盗链占位页，防止存成黑屏文件）。"""
    try:
        headers = {"User-Agent": UA}
        if referer:
            headers["Referer"] = referer
        r = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True)
        if r.status_code != 200 or not r.content:
            return None
        raw = r.content
        if kind == "video":
            # mp4：前 4 字节是 box 大小，4:8 是 'ftyp'；拒绝 <html / 纯文本
            if len(raw) < 12 or raw[4:8] != b"ftyp" or raw.lstrip()[:1] == b"<":
                return None
        else:
            magic = raw[:12]
            if not (
                magic[:3] == b"\xff\xd8\xff"            # JPEG
                or magic[:8] == b"\x89PNG\r\n\x1a\n"    # PNG
                or magic[:4] in (b"GIF8",)              # GIF
                or (magic[:4] == b"RIFF" and magic[8:12] == b"WEBP")  # WebP
            ):
                return None
        return raw
    except Exception as exc:
        logger.warning("资源下载失败 %s: %s", url, exc)
    return None


def local_cover(url: str | None) -> str:
    """把封面下载到本地（避免前端直连抖音/快手 CDN 被防盗链拦截显示黑图）。"""
    if not url:
        return ""
    hit = _cover_cache.get(url)
    if hit and time.time() - hit[0] < _COVER_CACHE_TTL:
        return hit[1]
    if "douyin" in (url or ""):
        referer = "https://www.douyin.com/"
    elif "kuaishou" in (url or "") or "ndcimgs" in (url or ""):
        referer = "https://www.kuaishou.com/"
    elif "hdslb" in (url or "") or "bili" in (url or ""):
        referer = "https://www.bilibili.com/"
    else:
        referer = "https://www.douyin.com/"
    img = _download(url, timeout=60, referer=referer, kind="image")
    if not img:
        return ""
    comp_img = wechat_local.compress_image_bytes(img)
    if comp_img:
        img = comp_img
    saved = _save_media(img, "cover", ".jpg")
    _cover_cache[url] = (time.time(), saved)
    return saved


def _save_media(raw: bytes, subdir: str, ext: str) -> str:
    """保存到 uploads/videos/<subdir>/，返回 /uploads/videos/... URL。"""
    md5 = hashlib.md5(raw).hexdigest()
    rel_dir = "videos/" + subdir + "/" + md5[:2]
    path = UPLOAD_ROOT / rel_dir / (md5 + ext)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return f"/uploads/{rel_dir}/{md5}{ext}"


async def publish_shared_video(db: Session, user: User, text: str, request: Request) -> dict:
    """解析分享链接 -> 直链播放模式发布（不下载、不转码、不存视频文件）。

    视频直接存抖音/快手 CDN 直链，前端 <video> 从 CDN 播放：
    服务器零视频存储/带宽/转码 CPU，画质原样（不糊），发布秒完成。
    直链会过期，帖子保存原始分享文本，失效时前端调 /videos/refresh-link 换新直链。
    """
    record = parse_share(text)
    video_url = playable_url(record)

    # 封面（小图）下载到本地并压缩，作为帖子图片
    image_urls: list[str] = []
    cover_local = local_cover(record.get("cover"))
    if cover_local:
        image_urls.append(cover_local)

    title = (record.get("title") or "").strip()
    content = title or "分享了一个视频"
    if len(content) < 10:
        content = content + " #视频分享"

    payload = PostCreate(
        content=content,
        image_urls=image_urls,
        video_urls=[video_url],
        source="video_share",
        is_anonymous=False,
        is_public=True,
        school_id=user.school_id,
        category=VIDEO_CATEGORY,
        is_draft=False,
        title=None,
        is_original=False,
        has_ai_content=False,
    )
    post = await post_service.create_post(payload, request, db, user)
    # 保存原始分享文本，供直链过期后重新解析
    post_row = db.get(Post, post.get("id"))
    if post_row is not None:
        post_row.video_share_text = text
        db.commit()
    return {"post": post, "record": record, "mode": "link"}


def _pick_direct_url(record: dict) -> str:
    """选一条直链。抖音：优先官方签名播放接口 aweme/v1/play；快手：photoUrl。"""
    urls = record.get("video_urls") or []
    if not urls:
        raise HTTPException(status_code=400, detail="未解析到视频直链，请确认分享链接正确")
    if record.get("platform") == "douyin":
        for u in urls:
            if "aweme/v1/play" in u:
                return u
    return urls[0]


def playable_url(record: dict) -> str:
    """生成浏览器可直接播放的 URL。

    - 快手：直链即可（实测浏览器跨站 206 可播）；
    - 抖音/B站：CDN 有防盗链（浏览器跨站必 403），走本站 /api/videos/proxy 反代
      （服务器带平台 Referer 拉流，Range 透传，不落盘、不转码）。
    """
    raw = _pick_direct_url(record)
    if record.get("platform") in ("douyin", "bilibili"):
        from urllib.parse import quote

        return f"/api/videos/proxy?url={quote(raw, safe='')}"
    return raw


def refresh_video_link(db: Session, post_id: int) -> dict:
    """直链过期后重新解析，换新直链（帖子需保存了原始分享文本）。"""
    from app.models import Post as _Post

    post = db.get(_Post, post_id)
    if post is None or not post.video_share_text:
        raise HTTPException(status_code=404, detail="该帖子没有可刷新的分享链接")
    record = parse_share(post.video_share_text)
    post.video_urls = json.dumps([playable_url(record)], ensure_ascii=False)
    db.commit()
    return {"video_url": json.loads(post.video_urls)[0]}


def probe_video_link(playable: str) -> bool:
    """探测直链是否还活着（服务器带平台 Referer，浏览器头才会被防盗链拦）。"""
    from urllib.parse import unquote

    if playable.startswith("/api/videos/proxy?"):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(playable).query)
        raw = (qs.get("url") or [""])[0]
    else:
        raw = playable
    if not raw.startswith(("http://", "https://")):
        return False
    if "kuaishou" in raw or "ndcimgs" in raw:
        referer = "https://www.kuaishou.com/"
    elif "bili" in raw or "hdslb" in raw:
        referer = "https://www.bilibili.com/"
    else:
        referer = "https://www.douyin.com/"
    try:
        r = httpx.get(
            raw,
            headers={"User-Agent": UA, "Referer": referer, "Range": "bytes=0-4095"},
            follow_redirects=True,
            timeout=15,
        )
        body = r.content
        return r.status_code in (200, 206) and (len(body) >= 12 and body[4:8] == b"ftyp")
    except Exception:
        return False


def check_and_restore_video_links(db: Session) -> int:
    """后台定时任务：扫描抖音/快手视频帖，修复不可播/失效的链接。

    - 旧帖存的是抖音裸直链（浏览器必 403）→ 包成 /api/videos/proxy 代理地址；
    - 直链失效（服务器探测 403）→ 用存的分享文本重新解析换新直链。
    返回修复条数。只处理保存了分享文本（video_share_text）的帖子。
    """
    from urllib.parse import quote

    from app.models import Post as _Post
    from sqlalchemy import select

    fixed = 0
    posts = db.scalars(
        select(_Post).where(
            _Post.video_share_text.isnot(None),
            _Post.video_urls != "[]",
        )
    ).all()
    for post in posts:
        try:
            urls = json.loads(post.video_urls or "[]")
            if not urls:
                continue
            current = urls[0]
            if not current.startswith("/api/videos/proxy?"):
                # 裸直链：抖音包成代理地址（浏览器才能播），快手直链可直接播
                if "douyin.com" in current or "iesdouyin.com" in current:
                    post.video_urls = json.dumps(
                        [f"/api/videos/proxy?url={quote(current, safe='')}"],
                        ensure_ascii=False,
                    )
                    fixed += 1
                    continue
                if probe_video_link(current):
                    continue
            elif probe_video_link(current):
                continue
            # 失效 -> 重新解析换新直链
            record = parse_share(post.video_share_text)
            post.video_urls = json.dumps([playable_url(record)], ensure_ascii=False)
            fixed += 1
        except Exception as exc:
            logger.warning("视频直链恢复失败 post#%s: %s", post.id, exc)
    if fixed:
        db.commit()
    return fixed
