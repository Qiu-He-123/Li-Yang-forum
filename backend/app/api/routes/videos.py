"""视频分享发布接口（抖音/快手）。

- POST /videos/parse       解析分享链接，返回标题/封面/平台（预览用，不发布）
- POST /videos/publish     解析并发布（直链播放：快手直链 / 抖音走反代）
- POST /videos/refresh-link 直链过期后重新解析换新直链
- GET  /videos/proxy       抖音视频反代播放（带平台 Referer，Range 透传，不落盘）
"""

import urllib.parse

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import video_service

router = APIRouter(prefix="/videos", tags=["videos"])

# 只允许转发这些视频 CDN 域（防止变成开放代理/SSRF）
ALLOWED_VIDEO_HOSTS = (
    "douyinvod.com",
    "douyin.com",
    "iesdouyin.com",
    "ndcimgs.com",
    "kuaishou.com",
    "gifshow.com",
    "bilivideo.com",
    "bilibili.com",
    "hdslb.com",
)

PROXY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@router.post("/parse")
def parse_video_share(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """解析分享链接，返回 {platform, title, cover, video_url, author}（不发布）。

    封面会先下载到本地再返回（避免前端直连抖音/快手 CDN 被防盗链拦截显示黑图）。
    """
    record = video_service.parse_share(payload.get("text") or "")
    cover = video_service.local_cover(record.get("cover"))
    return ok(
        {
            "platform": record.get("platform", ""),
            "title": record.get("title", ""),
            "cover": cover,
            "author": record.get("author", ""),
        }
    )


@router.post("/publish")
async def publish_video_share(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """解析分享链接并发布为视频帖（category=视频，直链播放模式）。"""
    result = await video_service.publish_shared_video(
        db, user, payload.get("text") or "", request
    )
    return ok(result)


@router.post("/refresh-link")
def refresh_video_link(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """直链过期后重新解析换新直链（帖子需保存了原始分享文本）。"""
    return ok(video_service.refresh_video_link(db, int(payload.get("post_id") or 0)))


@router.get("/proxy")
def proxy_video(
    url: str = Query(..., description="抖音/快手视频直链"),
    request: Request = None,
) -> StreamingResponse:
    """抖音视频反代播放：服务器带平台 Referer 拉流，Range 透传，不落盘不转码。

    抖音 CDN 对浏览器跨站请求做防盗链（必 403），但对服务器请求（带
    Referer: douyin.com）正常放行。前端 <video> 指向本接口即可播放。
    仅允许白名单 CDN 域名，防止开放代理/SSRF。
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        parsed = urllib.parse.urlparse("")
    if parsed.scheme not in ("http", "https") or not any(
        host in parsed.netloc for host in ALLOWED_VIDEO_HOSTS
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="仅允许转发抖音/快手视频直链")

    headers = {
        "User-Agent": PROXY_UA,
        "Referer": "https://www.douyin.com/",
    }
    range_h = request.headers.get("range") if request else None
    if range_h:
        headers["Range"] = range_h

    upstream = httpx.stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=180
    )
    resp = upstream.__enter__()
    if resp.status_code >= 400:
        upstream.__exit__(None, None, None)
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail="视频源不可用")

    out_headers = {}
    for k in ("content-type", "content-length", "content-range", "accept-ranges"):
        if resp.headers.get(k):
            out_headers[k] = resp.headers[k]
    out_headers["Cache-Control"] = "public, max-age=3600"

    def _gen():
        try:
            for chunk in resp.iter_bytes():
                yield chunk
        finally:
            upstream.__exit__(None, None, None)

    return StreamingResponse(
        _gen(),
        status_code=resp.status_code,
        headers=out_headers,
        media_type=resp.headers.get("content-type") or "video/mp4",
    )
