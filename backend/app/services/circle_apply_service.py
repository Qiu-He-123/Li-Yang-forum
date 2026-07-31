"""用户自创建吧（圈子申请）业务逻辑层。

阶段四：参考百度贴吧，普通用户可申请创建圈子，管理员审核通过后正式上线。
- 申请建吧：校验 name/slug 唯一性，落库 status=pending
- 我的申请：用户查看自己申请的吧列表
- 待审核列表：管理员查看待审核吧
- 审核：通过则 status=approved + 创建 CategoryAdmin(owner)，拒绝则 status=rejected + 记录原因
- 吧主权限：判断用户是否为某吧的吧主（用于删帖等管理操作）
"""
import re

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import now_utc, to_iso_zh
from app.models import Category, CategoryAdmin, Post, User

# slug 校验规则：英文/数字/横线，2-32 字
_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9-]{2,32}$")


def apply_create_circle(
    db: Session,
    user: User,
    name: str,
    slug: str,
    description: str | None = None,
    icon: str | None = None,
    color: str | None = None,
) -> dict:
    """用户申请建吧。

    校验：
    - name 长度 2-16
    - slug 格式（英文/数字/横线，2-32 字）且全局唯一
    - name 全局唯一（与现有圈子不重复）
    - 同一用户存在 pending 申请的同 slug 不允许重复提交
    """
    name = (name or "").strip()
    slug = (slug or "").strip().lower()
    description = (description or "").strip() or None
    icon = (icon or "").strip() or None
    color = (color or "").strip() or "#007aff"

    if not (2 <= len(name) <= 16):
        raise HTTPException(status_code=400, detail="吧名称长度需为 2-16 字")
    if not _SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=400, detail="吧标识仅支持英文/数字/横线，长度 2-32 字")

    # 校验 name / slug 唯一性（含所有状态，避免审核中被重复申请）
    exists = db.scalar(
        select(Category.id).where(
            (Category.name == name) | (Category.slug == slug)
        )
    )
    if exists:
        raise HTTPException(status_code=400, detail="吧名称或标识已存在")

    # 同一用户禁止重复提交 pending 状态的同 slug 申请
    dup_pending = db.scalar(
        select(Category.id).where(
            Category.creator_id == user.id,
            Category.slug == slug,
            Category.status == "pending",
        )
    )
    if dup_pending:
        raise HTTPException(status_code=400, detail="该吧已有待审核申请，请等待管理员处理")

    # 新建圈子：sort_order 取当前最大值 + 1（确保排在后面）
    max_sort = db.scalar(select(func.max(Category.sort_order))) or 0
    circle = Category(
        name=name,
        slug=slug,
        icon=icon,
        description=description,
        color=color,
        sort_order=max_sort + 1,
        creator_id=user.id,
        status="pending",
    )
    db.add(circle)
    db.flush()
    db.commit()
    db.refresh(circle)
    return _apply_dict(circle, db, with_creator=True)


def list_my_applies(db: Session, user: User) -> list[dict]:
    """用户查看自己申请的吧列表（含状态：pending/approved/rejected）。"""
    rows = db.scalars(
        select(Category).where(Category.creator_id == user.id).order_by(desc(Category.created_at))
    ).all()
    return [_apply_dict(c, db, with_creator=False) for c in rows]


def list_pending_applies(db: Session, status: str | None = None) -> list[dict]:
    """管理员查看待审核吧列表。

    Args:
        status: 过滤状态，None 表示全部非系统初始化的申请吧（creator_id 非空）
    """
    stmt = select(Category).where(Category.creator_id.is_not(None))
    if status:
        stmt = stmt.where(Category.status == status)
    stmt = stmt.order_by(desc(Category.created_at))
    rows = db.scalars(stmt).all()
    return [_apply_dict(c, db, with_creator=True) for c in rows]


def audit_circle(
    db: Session,
    category_id: int,
    approved: bool,
    reject_reason: str | None = None,
    admin_id: int | None = None,
) -> dict:
    """管理员审核吧申请。

    通过：status=approved + 创建 CategoryAdmin(owner) 关系（创建者自动成为吧主）
    拒绝：status=rejected + 记录 reject_reason

    Args:
        admin_id: 审核管理员 id（用于记录 audited_by）
    """
    circle = db.get(Category, category_id)
    if not circle:
        raise HTTPException(status_code=404, detail="圈子不存在")
    if circle.status != "pending":
        raise HTTPException(status_code=400, detail="该吧已审核，无法重复操作")

    circle.audit_at = now_utc()
    if admin_id is not None:
        circle.audited_by = admin_id
    if approved:
        circle.status = "approved"
        circle.reject_reason = None
        # 创建者自动成为吧主（owner），幂等：已存在则跳过
        if circle.creator_id is not None:
            existing = db.scalar(
                select(CategoryAdmin.id).where(
                    CategoryAdmin.category_id == circle.id,
                    CategoryAdmin.user_id == circle.creator_id,
                )
            )
            if not existing:
                db.add(
                    CategoryAdmin(
                        category_id=circle.id,
                        user_id=circle.creator_id,
                        role="owner",
                    )
                )
    else:
        circle.status = "rejected"
        circle.reject_reason = (reject_reason or "").strip() or "未提供拒绝原因"

    db.commit()
    db.refresh(circle)
    return _apply_dict(circle, db, with_creator=True)


def is_circle_admin(db: Session, category_id: int, user_id: int) -> bool:
    """判断用户是否是该吧的吧主（owner 或 admin）。"""
    row = db.scalar(
        select(CategoryAdmin.id).where(
            CategoryAdmin.category_id == category_id,
            CategoryAdmin.user_id == user_id,
        )
    )
    return row is not None


def list_circle_admins(db: Session, category_id: int) -> list[dict]:
    """列出某吧的管理员列表。"""
    rows = db.scalars(
        select(CategoryAdmin)
        .where(CategoryAdmin.category_id == category_id)
        .order_by(CategoryAdmin.id)
    ).all()
    result = []
    for ca in rows:
        u = db.get(User, ca.user_id)
        result.append(
            {
                "id": ca.id,
                "category_id": ca.category_id,
                "user_id": ca.user_id,
                "role": ca.role,
                "nickname": u.nickname if u else None,
                "avatar_url": u.avatar_url if u else None,
                "created_at": to_iso_zh(ca.created_at),
            }
        )
    return result


def delete_post_as_admin(post_id: int, db: Session, user: User) -> None:
    """吧主删帖：仅该吧的吧主可删除本圈子内的帖子。"""
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    # 通过帖子 category（存圈子 name）反查 Category
    circle = db.scalar(select(Category).where(Category.name == post.category))
    if not circle:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    if not is_circle_admin(db, circle.id, user.id):
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    db.delete(post)
    # 圈子帖子计数减一
    if circle.post_count and circle.post_count > 0:
        circle.post_count -= 1
    db.commit()


def _apply_dict(c: Category, db: Session, with_creator: bool = False) -> dict:
    """序列化吧申请详情。"""
    data = {
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "icon": c.icon,
        "description": c.description,
        "color": c.color,
        "post_count": c.post_count,
        "member_count": c.member_count,
        "sort_order": c.sort_order,
        "creator_id": c.creator_id,
        "status": c.status,
        "reject_reason": c.reject_reason,
        "audit_at": to_iso_zh(c.audit_at),
        "audited_by": c.audited_by,
        "created_at": to_iso_zh(c.created_at),
    }
    if with_creator and c.creator_id is not None:
        creator = db.get(User, c.creator_id)
        data["creator_nickname"] = creator.nickname if creator else None
        data["creator_avatar_url"] = creator.avatar_url if creator else None
    return data
