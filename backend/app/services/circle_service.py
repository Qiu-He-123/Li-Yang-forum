"""圈子（Category）业务逻辑层。

圈子是分类的视觉化呈现：每个圈子对应一个 slug，用户可以加入/退出圈子，
帖子可以按圈子过滤浏览。
"""
from fastapi import HTTPException
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Category, CategoryAdmin, CircleView, Post, User, UserCategory
from app.services.post_service import post_dict


def list_circles(db: Session, user: User | None = None) -> list[dict]:
    """查询圈子列表（按 sort_order, id 排序），含 is_joined 字段。

    阶段四：只返回 status=approved 的圈子；登录用户额外可见自己创建的 pending 圈子。
    """
    stmt = select(Category).where(Category.is_active.is_(True))
    if user is not None:
        # approved 或 自己创建的 pending（创建者可在列表里看到审核中状态）
        stmt = stmt.where(
            or_(
                Category.status == "approved",
                (Category.creator_id == user.id) & (Category.status == "pending"),
            )
        )
    else:
        stmt = stmt.where(Category.status == "approved")
    stmt = stmt.order_by(Category.sort_order, Category.id)
    rows = db.scalars(stmt).all()
    joined_ids: set[int] = set()
    if user is not None:
        joined_ids = set(
            db.scalars(
                select(UserCategory.category_id).where(UserCategory.user_id == user.id)
            ).all()
        )
    return [_circle_dict(c, is_joined=c.id in joined_ids) for c in rows]


def get_circle_by_slug(slug: str, db: Session, user: User | None = None) -> Category:
    """根据 slug 查询圈子，不存在抛 404。

    阶段四：非 approved 状态的圈子仅创建者本人可见（pending/rejected）。
    """
    c = db.scalar(select(Category).where(Category.slug == slug))
    if not c:
        raise HTTPException(status_code=404, detail=ErrorCode.CATEGORY_NOT_FOUND)
    # 非已通过的圈子仅创建者本人可见
    if c.status != "approved":
        if user is None or user.id != c.creator_id:
            raise HTTPException(status_code=404, detail=ErrorCode.CATEGORY_NOT_FOUND)
    return c


def get_circle_detail(slug: str, db: Session, user: User | None = None) -> dict:
    """查询圈子详情，含 is_joined 与 is_admin 字段。

    阶段四：is_admin 表示当前用户是否为该吧的吧主/管理员（用于前端展示管理入口）。
    """
    c = get_circle_by_slug(slug, db, user)
    is_joined = False
    is_admin = False
    if user is not None:
        is_joined = bool(
            db.scalar(
                select(UserCategory.id).where(
                    UserCategory.user_id == user.id, UserCategory.category_id == c.id
                )
            )
        )
        is_admin = bool(
            db.scalar(
                select(CategoryAdmin.id).where(
                    CategoryAdmin.category_id == c.id,
                    CategoryAdmin.user_id == user.id,
                )
            )
        )
    return _circle_dict(c, is_joined=is_joined, with_dates=True, is_admin=is_admin)


def list_circle_posts(
    slug: str,
    db: Session,
    user: User | None,
    post_type: str = "all",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询圈子内帖子列表。

    Args:
        slug: 圈子 slug
        db: Session
        user: 当前用户（None 时匿名访问，只返回公开帖子）
        post_type: all / essence / image / video
            - all: 全部
            - essence: 精华（like_count >= 10）
            - image: 有图片的帖子
            - video: 暂用同 image 逻辑（占位，未来扩展 video_urls 字段）
        page: 页码
        page_size: 每页条数
    """
    c = get_circle_by_slug(slug, db, user)
    # 帖子 category 可能存的是圈子 name（如"表白墙"）或 slug（如"confess"），
    # 前端 PostEditor 发送的是 slug，但历史帖子可能存 name，两者都需匹配
    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.school))
        .where(Post.is_draft.is_(False), Post.category.in_([c.name, c.slug]))
    )
    # 私密帖子只有作者本人可见（匿名用户只看公开）
    if user is not None:
        query = query.where(or_(Post.is_public.is_(True), Post.author_id == user.id))
    else:
        query = query.where(Post.is_public.is_(True))

    if post_type == "essence":
        query = query.where(Post.like_count >= 10)
    elif post_type == "image":
        query = query.where(Post.image_urls.like("%http%").or_(Post.image_urls.like("%/uploads/%")))
    elif post_type == "video":
        # 视频字段未独立，暂用同 image 兜底
        query = query.where(Post.image_urls.like("%http%").or_(Post.image_urls.like("%/uploads/%")))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    posts = db.scalars(
        query.order_by(desc(Post.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [post_dict(p) for p in posts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "circle": _circle_dict(c, is_joined=False),
    }


def join_circle(slug: str, db: Session, user: User) -> dict:
    """加入圈子（幂等）。阶段四：仅 status=approved 的圈子可加入。"""
    c = get_circle_by_slug(slug, db, user)
    if c.status != "approved":
        raise HTTPException(status_code=400, detail="该吧尚未通过审核")
    existing = db.scalar(
        select(UserCategory).where(
            UserCategory.user_id == user.id, UserCategory.category_id == c.id
        )
    )
    if not existing:
        db.add(UserCategory(user_id=user.id, category_id=c.id))
        c.member_count = (c.member_count or 0) + 1
        db.commit()
        db.refresh(c)
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "is_joined": True,
        "member_count": c.member_count,
    }


def leave_circle(slug: str, db: Session, user: User) -> dict:
    """退出圈子（幂等）。"""
    c = get_circle_by_slug(slug, db, user)
    existing = db.scalar(
        select(UserCategory).where(
            UserCategory.user_id == user.id, UserCategory.category_id == c.id
        )
    )
    if existing:
        db.delete(existing)
        if c.member_count and c.member_count > 0:
            c.member_count -= 1
        db.commit()
        db.refresh(c)
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "is_joined": False,
        "member_count": c.member_count,
    }


def _circle_dict(c: Category, is_joined: bool = False, with_dates: bool = False, is_admin: bool = False) -> dict:
    """序列化圈子为前端响应字典。"""
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
        "is_active": c.is_active,
        "is_joined": is_joined,
        # 阶段四：用户自创建吧相关字段
        "creator_id": c.creator_id,
        "status": c.status,
        "is_admin": is_admin,
    }
    if with_dates:
        data["created_at"] = to_iso_zh(c.created_at)
    return data


def record_circle_view(db: Session, user_id: int, circle_id: int) -> None:
    """记录用户浏览圈子（幂等，重复浏览更新 viewed_at）。"""
    existing = db.scalar(
        select(CircleView).where(
            CircleView.user_id == user_id,
            CircleView.circle_id == circle_id,
        )
    )
    if existing:
        existing.viewed_at = func.now()
    else:
        db.add(CircleView(user_id=user_id, circle_id=circle_id))
    db.commit()


def list_viewed_circles(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    """获取用户浏览过的圈子列表（按最近浏览排序）。"""
    stmt = (
        select(CircleView, Category)
        .join(Category, Category.id == CircleView.circle_id)
        .where(CircleView.user_id == user_id)
        .order_by(desc(CircleView.viewed_at))
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    result: list[dict] = []
    for view, circle in rows:
        d = _circle_dict(circle, is_joined=False)
        d["viewed_at"] = to_iso_zh(view.viewed_at) if view.viewed_at else None
        result.append(d)
    return result
