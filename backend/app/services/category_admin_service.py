"""吧主（圈子管理员）管理服务。

负责吧主与管理员的增删查、权限校验、吧主删帖等业务逻辑。
与 circle_apply_service.py 解耦，专门处理吧主权限相关操作。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Category, CategoryAdmin, Post, User


def is_category_admin(db: Session, category_id: int, user_id: int) -> bool:
    """检查用户是否是指定圈子的管理员/吧主（owner 或 admin 均可）。"""
    return db.scalar(
        select(CategoryAdmin.id).where(
            CategoryAdmin.category_id == category_id,
            CategoryAdmin.user_id == user_id,
        )
    ) is not None


def is_category_owner(db: Session, category_id: int, user_id: int) -> bool:
    """检查用户是否是指定圈子的吧主（创建者，role=owner）。"""
    return db.scalar(
        select(CategoryAdmin.id).where(
            CategoryAdmin.category_id == category_id,
            CategoryAdmin.user_id == user_id,
            CategoryAdmin.role == "owner",
        )
    ) is not None


def list_category_admins(db: Session, category_id: int) -> list[dict]:
    """列出圈子所有管理员（按 id 排序，owner 排前）。"""
    rows = db.scalars(
        select(CategoryAdmin)
        .where(CategoryAdmin.category_id == category_id)
        .order_by(CategoryAdmin.id)
    ).all()
    result = []
    for ca in rows:
        user = db.get(User, ca.user_id)
        if user:
            result.append({
                "id": ca.id,
                "category_id": ca.category_id,
                "user_id": user.id,
                "nickname": user.nickname,
                "avatar_url": user.avatar_url,
                "role": ca.role,
                "created_at": to_iso_zh(ca.created_at),
            })
    return result


def add_category_admin(db: Session, category_id: int, user_id: int, role: str = "admin") -> dict:
    """添加圈子管理员（仅吧主可操作；幂等：已存在则更新 role）。

    Args:
        db: 数据库会话
        category_id: 圈子 id
        user_id: 待添加用户 id
        role: owner/admin（默认 admin）
    """
    existing = db.scalar(
        select(CategoryAdmin).where(
            CategoryAdmin.category_id == category_id,
            CategoryAdmin.user_id == user_id,
        )
    )
    if existing:
        existing.role = role
    else:
        ca = CategoryAdmin(category_id=category_id, user_id=user_id, role=role)
        db.add(ca)
    db.commit()
    return {"ok": True, "category_id": category_id, "user_id": user_id, "role": role}


def remove_category_admin(db: Session, category_id: int, user_id: int) -> dict:
    """移除圈子管理员（仅吧主可操作，不能移除 owner 自己）。

    Args:
        db: 数据库会话
        category_id: 圈子 id
        user_id: 待移除用户 id
    """
    ca = db.scalar(
        select(CategoryAdmin).where(
            CategoryAdmin.category_id == category_id,
            CategoryAdmin.user_id == user_id,
        )
    )
    if not ca:
        raise HTTPException(status_code=404, detail=ErrorCode.NOT_FOUND)
    if ca.role == "owner":
        raise HTTPException(status_code=400, detail="不能移除吧主")
    db.delete(ca)
    db.commit()
    return {"ok": True, "category_id": category_id, "user_id": user_id}


def delete_post_as_admin(db: Session, category_id: int, post_id: int, admin_user_id: int) -> None:
    """吧主删除吧内帖子。

    校验：
    - 当前用户必须是该吧的吧主/管理员
    - 帖子必须属于该 category（通过 post.category = category.name 反查匹配）
    """
    if not is_category_admin(db, category_id, admin_user_id):
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    # 通过 category_id 反查 Category，校验 post.category 匹配 Category 的 name 或 slug
    # （前端 PostEditor 发送 slug，历史帖子可能存 name，两者都需匹配）
    category = db.get(Category, category_id)
    if not category or post.category not in (category.name, category.slug):
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    db.delete(post)
    # 清理该帖及其评论的关联通知
    from app.models import Comment
    from app.services.notification_service import (
        cleanup_notifications_for_deleted_comments,
        cleanup_notifications_for_deleted_posts,
    )
    comment_ids = db.scalars(select(Comment.id).where(Comment.post_id == post_id)).all()
    cleanup_notifications_for_deleted_comments(db, list(comment_ids))
    cleanup_notifications_for_deleted_posts(db, post_id)
    # 圈子帖子计数减一
    if category.post_count and category.post_count > 0:
        category.post_count -= 1
    db.commit()
