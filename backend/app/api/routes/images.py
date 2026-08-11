import io
import asyncio as aio
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from loguru import logger
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.core.security import decode_token
from app.core.time_utils import to_iso_zh
from app.models import Admin, Image, User
from app.schemas.common import ok
from app.services.storage_service import storage_service

router = APIRouter(prefix="/images", tags=["images"])

ALLOWED_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
# 浏览器可能发送非标准的 image/jpg，统一映射为 image/jpeg
TYPE_ALIASES = {"image/jpg": "image/jpeg"}
MAX_BYTES = 5 * 1024 * 1024
THUMB_MAX_SIZE = (400, 400)  # 缩略图最大尺寸
BACKGROUND_MAX_SIZE = (1920, 1920)  # 背景图压缩后的最长边
BACKGROUND_QUALITY = 82


async def _read_limited(file: UploadFile, max_bytes: int = MAX_BYTES) -> bytes:
    """分块读取上传文件，超过 max_bytes 立即拒绝（P1-2：防内存/磁盘耗尽）。"""
    content = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail="图片大小不能超过 5MB")
    return bytes(content)


def _check_content_length(request: Request) -> None:
    """根据 Content-Length 提前拒绝超大上传（含 multipart 封装开销）。"""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BYTES + 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片大小不能超过 5MB")


def _is_admin_request(db: Session, request: Request) -> bool:
    """校验 admin_token Cookie 是否有效（私密图片允许管理员查看）。"""
    token = request.cookies.get("admin_token")
    if not token:
        return False
    try:
        admin_id = int(decode_token(token))
    except (jwt.InvalidTokenError, ValueError):
        return False
    return db.get(Admin, admin_id) is not None


def _detect_image_type(content: bytes) -> str | None:
    """根据 magic bytes 检测真实图片类型，返回 mime_type 或 None。"""
    if len(content) < 12:
        return None
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    # WEBP: RIFF....WEBP
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _make_thumbnail(content: bytes, mime_type: str) -> bytes | None:
    """生成缩略图（最大 400x400），用于列表快速加载。

    返回缩略图的 bytes，失败返回 None（由调用方使用原图）。
    GIF 动图不生成缩略图（保留动效）。
    """
    if mime_type == "image/gif":
        return None
    try:
        img = PILImage.open(io.BytesIO(content))
        img.thumbnail(THUMB_MAX_SIZE, PILImage.LANCZOS)
        # 转 RGB（处理 RGBA/PNG 透明背景→白底）
        if img.mode in ("RGBA", "P"):
            background = PILImage.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def _compress_background(content: bytes, mime_type: str) -> bytes | None:
    """压缩背景图：最长边不超过 1920px，JPEG q82；GIF 动图保留原样。"""
    if mime_type == "image/gif":
        return content
    try:
        img = PILImage.open(io.BytesIO(content))
        img.thumbnail(BACKGROUND_MAX_SIZE, PILImage.LANCZOS)
        if img.mode in ("RGBA", "P"):
            background = PILImage.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=BACKGROUND_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    purpose: str = Query(default="post", pattern="^(post|avatar|background)$"),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    _check_content_length(request)
    # 统一 content_type：image/jpg → image/jpeg
    raw_content_type = file.content_type or ""
    content_type = TYPE_ALIASES.get(raw_content_type, raw_content_type)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="图片格式仅支持 jpg、png、webp、gif")
    content = await _read_limited(file)

    # T7-10：用 magic bytes 校验真实文件类型，防止伪装 content_type 上传可执行文件（S9）
    real_type = _detect_image_type(content)
    if not real_type:
        logger.warning("[IMAGE_UPLOAD] magic bytes 无法识别图片类型, user={}", user.id)
        raise HTTPException(status_code=400, detail="无法识别的图片格式，请重新选择文件")
    if real_type != content_type:
        raise HTTPException(status_code=400, detail="图片内容与声明格式不符，疑似伪装文件")

    # 背景图：上传前先压缩（最长边 1920 / JPEG q82），避免大图原样存储拖慢页面
    if purpose == "background":
        loop = aio.get_running_loop()
        compressed = await loop.run_in_executor(
            None, _compress_background, content, content_type
        )
        if compressed:
            content = compressed
            content_type = "image/jpeg"

    ext = ALLOWED_TYPES[content_type]
    filename = f"{uuid4().hex}{ext}"

    # 异步上传原图 + 缩略图（并行）
    upload_task = storage_service.upload_image_async(filename, content, content_type)

    # 生成缩略图（CPU 密集型，放到线程池）
    loop = aio.get_running_loop()
    thumb_content = await loop.run_in_executor(None, _make_thumbnail, content, content_type)
    thumb_url: str | None = None
    thumb_task = None
    if thumb_content:
        thumb_filename = f"{uuid4().hex}_thumb.jpg"
        thumb_task = storage_service.upload_image_async(thumb_filename, thumb_content, "image/jpeg")

    # 等待上传完成
    try:
        url = await upload_task
    except Exception as exc:
        logger.error("[IMAGE_UPLOAD] 原图存储失败, user={}, err={}", user.id, exc)
        raise HTTPException(status_code=500, detail="图片存储失败，请稍后重试") from exc
    if thumb_task:
        try:
            thumb_url = await thumb_task
        except Exception:
            thumb_url = None  # 缩略图失败不影响主流程

    # 记录入库；头像不参与内容审核（直接 approved），帖子图片一律 pending 人工审核
    image = Image(
        user_id=user.id,
        url=url,
        mime_type=content_type,
        size_bytes=len(content),
        audit_status="approved" if purpose in ("avatar", "background") else "pending",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    result = {
        "id": image.id,
        "url": url,
        "thumb_url": thumb_url or url,
        "audit_status": image.audit_status,
    }
    if image.audit_status == "pending":
        result["audit_note"] = "图片内容需人工审核"
    return ok(result)


@router.post("/verification")
async def upload_verification_image(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """学生认证照片专用私密上传（P0-1）。

    与公开 /images 不同：存入隔离目录，URL 为 /images/private/*，
    只能由本人或管理员通过鉴权接口读取。
    """
    _check_content_length(request)
    raw_content_type = file.content_type or ""
    content_type = TYPE_ALIASES.get(raw_content_type, raw_content_type)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="图片格式仅支持 jpg、png、webp、gif")
    content = await _read_limited(file)

    real_type = _detect_image_type(content)
    if not real_type:
        logger.warning("[IMAGE_UPLOAD] magic bytes 无法识别图片类型, user={}", user.id)
        raise HTTPException(status_code=400, detail="无法识别的图片格式，请重新选择文件")
    if real_type != content_type:
        raise HTTPException(status_code=400, detail="图片内容与声明格式不符，疑似伪装文件")

    ext = ALLOWED_TYPES[content_type]
    filename = f"{uuid4().hex}{ext}"
    url = await storage_service.upload_private_image_async(filename, content, content_type)

    image = Image(
        user_id=user.id,
        url=url,
        mime_type=content_type,
        size_bytes=len(content),
        is_private=True,
        # 学生证照片由「学生认证审核」流程人工把关，不进入图片审核队列
        audit_status="approved",
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return ok({"id": image.id, "url": url})


@router.get("/private/{filename}")
async def get_private_image(
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """鉴权读取私密图片：仅图片所有者或管理员可见（P0-1）。"""
    image = db.scalar(
        select(Image).where(
            Image.url == f"/images/private/{filename}",
            Image.is_private.is_(True),
        )
    )
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    user_id: int | None = None
    token = request.cookies.get("access_token")
    if token:
        try:
            user_id = int(decode_token(token))
        except (jwt.InvalidTokenError, ValueError):
            user_id = None

    if not (user_id == image.user_id or _is_admin_request(db, request)):
        raise HTTPException(status_code=403, detail="无权查看该图片")

    data = await storage_service.read_private(filename)
    if data is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    return Response(
        content=data,
        media_type=image.mime_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )

@router.get("")
async def list_my_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """个人素材库：返回当前用户历史上传的图片（最新在前），供发帖时复用。"""
    query = db.query(Image).filter(Image.user_id == user.id).order_by(Image.id.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return ok(
        {
            "items": [
                {
                    "id": img.id,
                    "url": img.url,
                    "mime_type": img.mime_type,
                    "is_private": img.is_private,
                    "created_at": to_iso_zh(img.created_at) if img.created_at else None,
                }
                for img in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
