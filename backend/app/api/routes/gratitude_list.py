"""感谢名单路由。

用户侧（前端列表 + 详情页）：
    GET /gratitude-list          上架名单列表（sort_order 升序）
    GET /gratitude-list/{id}     单条详情

管理侧（后台：可编辑，含头像/名字/简介/详情/排序/上架）：
    GET    /admin/gratitude-list  全部名单（含下架）
    POST   /admin/gratitude-list  新增
    PUT    /admin/gratitude-list/{id}  编辑
    DELETE /admin/gratitude-list/{id}  删除
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import admin_user
from app.core.database import get_db
from app.models import Admin, GratitudeList
from app.schemas.common import ok


_user_router = APIRouter(prefix="/gratitude-list", tags=["gratitude-list"])
_admin_router = APIRouter(prefix="/admin/gratitude-list", tags=["admin-gratitude-list"])


def _item_dict(g: GratitudeList) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "avatar_url": g.avatar_url,
        "bio": g.bio,
        "detail": g.detail,
        "sort_order": g.sort_order or 0,
        "is_active": bool(g.is_active),
    }


class GratitudeItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    avatar_url: str | None = None
    bio: str | None = Field(default=None, max_length=200)
    detail: str | None = None
    sort_order: int = 0
    is_active: bool = True


# ============ 用户侧 ============


@_user_router.get("")
def list_active(
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(GratitudeList)
        .where(GratitudeList.is_active)
        .order_by(GratitudeList.sort_order.asc(), GratitudeList.id.asc())
    ).all()
    return ok([_item_dict(g) for g in rows])


@_user_router.get("/{gid}")
def get_detail(
    gid: int,
    db: Session = Depends(get_db),
) -> dict:
    g = db.get(GratitudeList, gid)
    if not g or not g.is_active:
        raise HTTPException(status_code=404, detail="名单不存在")
    return ok(_item_dict(g))


# ============ 管理侧 ============


@_admin_router.get("")
def admin_list(
    keyword: str | None = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    query = select(GratitudeList)
    if keyword:
        query = query.where(GratitudeList.name.contains(keyword))
    rows = db.scalars(query.order_by(GratitudeList.sort_order.asc(), GratitudeList.id.asc())).all()
    return ok([_item_dict(g) for g in rows])


@_admin_router.post("")
def admin_create(
    payload: GratitudeItemIn,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写名字")
    g = GratitudeList(
        name=name,
        avatar_url=(payload.avatar_url or "").strip() or None,
        bio=(payload.bio or "").strip() or None,
        detail=payload.detail,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return ok(_item_dict(g))


@_admin_router.put("/{gid}")
def admin_update(
    gid: int,
    payload: GratitudeItemIn,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    g = db.get(GratitudeList, gid)
    if not g:
        raise HTTPException(status_code=404, detail="名单不存在")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写名字")
    g.name = name
    g.avatar_url = (payload.avatar_url or "").strip() or None
    g.bio = (payload.bio or "").strip() or None
    g.detail = payload.detail
    g.sort_order = payload.sort_order
    g.is_active = payload.is_active
    db.commit()
    db.refresh(g)
    return ok(_item_dict(g))


@_admin_router.post("/upload-avatar")
async def admin_upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """上传感谢名单成员头像（jpg/png/webp/gif ≤5MB），返回可访问 URL（已存到云存储）。"""
    import io
    from uuid import uuid4

    from PIL import Image as PILImage

    from app.services.storage_service import storage_service

    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    }
    content_type = (file.content_type or "").lower()
    ext = ext_map.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / WEBP / GIF 图片")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 5MB")
    try:
        img = PILImage.open(io.BytesIO(content))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="图片文件无效") from None

    filename = f"gratitude/{uuid4().hex}{ext}"
    url = await storage_service.upload_image_async(filename, content, content_type)
    db.commit()
    return ok({"url": url, "size": len(content)})


@_admin_router.delete("/{gid}")
def admin_delete(
    gid: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    g = db.get(GratitudeList, gid)
    if not g:
        raise HTTPException(status_code=404, detail="名单不存在")
    db.delete(g)
    db.commit()
    return ok(True)


router = _user_router
admin_router = _admin_router