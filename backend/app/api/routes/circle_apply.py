"""圈子申请与吧主管理路由（阶段四：用户自创建吧）。

与 circles.py 同前缀 `/circles`，但需在 main.py 中先于 circles.router 注册，
以确保 `/circles/apply` 和 `/circles/my-applies` 不会被 `/circles/{slug}` 抢先匹配。
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.models import User
from app.schemas.common import ok
from app.services import category_admin_service, circle_apply_service, circle_service

router = APIRouter(prefix="/circles", tags=["circles"])


@router.post("/apply")
def apply_create_circle(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """用户申请建吧（需登录）。

    payload:
    - name: 吧名称（必填，2-16 字）
    - slug: 吧标识（必填，英文/数字/横线，2-32 字，用于 URL）
    - description: 简介（可选，最多 200 字）
    - icon: 图标名（可选）
    - color: 主题色（可选，默认 #007aff）
    """
    return ok(
        circle_apply_service.apply_create_circle(
            db,
            user,
            name=payload.get("name", ""),
            slug=payload.get("slug", ""),
            description=payload.get("description"),
            icon=payload.get("icon"),
            color=payload.get("color"),
        )
    )


@router.get("/my-applies")
def list_my_applies(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """我的申请列表（需登录）。"""
    return ok(circle_apply_service.list_my_applies(db, user))


@router.get("/{slug}/admins")
def list_circle_admins(
    slug: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """查看吧主列表（公开，圈子需已通过审核或本人查看）。"""
    c = circle_service.get_circle_by_slug(slug, db, user)
    return ok(category_admin_service.list_category_admins(db, c.id))


@router.post("/{slug}/admins")
def add_circle_admin(
    slug: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """吧主任命管理员（仅 owner 可操作）。

    payload:
    - user_id: int（待添加的用户 id）
    - role: str（可选，admin/owner，默认 admin）
    """
    c = circle_service.get_circle_by_slug(slug, db, user)
    # 校验当前用户是否为吧主
    if not category_admin_service.is_category_owner(db, c.id, user.id):
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    target_user_id = int(payload.get("user_id", 0))
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")
    role = payload.get("role", "admin")
    return ok(category_admin_service.add_category_admin(db, c.id, target_user_id, role))


@router.delete("/{slug}/admins/{user_id}")
def remove_circle_admin(
    slug: str,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """吧主移除管理员（仅 owner 可操作，不能移除 owner 自己）。"""
    c = circle_service.get_circle_by_slug(slug, db, user)
    if not category_admin_service.is_category_owner(db, c.id, user.id):
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    return ok(category_admin_service.remove_category_admin(db, c.id, user_id))


@router.delete("/{slug}/posts/{post_id}")
def delete_post_as_circle_admin(
    slug: str,
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """吧主删帖（需登录且为该吧吧主/管理员）。"""
    c = circle_service.get_circle_by_slug(slug, db, user)
    # 校验 slug 与帖子所属圈子一致（service 内通过 category.name 匹配）
    category_admin_service.delete_post_as_admin(db, c.id, post_id, user.id)
    return ok({"post_id": post_id, "circle_id": c.id})
