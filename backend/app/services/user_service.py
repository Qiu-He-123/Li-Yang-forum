"""用户资料业务逻辑层。"""
import json

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.services.avatar import avatar_url_or_default
from app.core.time_utils import calculate_age, to_iso_zh
from app.models import Comment, Favorite, Like, Post, User
from app.schemas.interactions import ProfileUpdate
from app.services.audit_log import log_user_action
from app.services.post_service import post_dict


def profile(user: User, db: Session, viewer: User | None = None) -> dict:
    """组装用户资料响应。

    viewer 为当前登录用户（查看者）。当 viewer 存在且不是 user 本人时，
    返回 is_following / is_following_me / is_mutual 三个关注关系字段，
    供前端个人主页直接渲染关注按钮与互关状态，避免再单独请求 is-following
    接口且避免前端缓存导致的状态不一致（匹配互关后主页仍显示"未关注"）。
    """
    post_count = db.scalar(
        select(func.count())
        .select_from(Post)
        .where(Post.author_id == user.id, Post.is_draft == False, Post.ai_status == "approved")
    ) or 0
    from app.models import UserBadge
    from app.services.badge_service import badge_dict as _badge_dict
    badge_count = db.scalar(
        select(func.count(UserBadge.id)).where(UserBadge.user_id == user.id)
    ) or 0
    # T8-4 优化：用 join 替代子查询
    like_count = (
        db.scalar(
            select(func.count())
            .select_from(Like)
            .join(Post, Post.id == Like.target_id)
            .where(Post.author_id == user.id, Like.target_type == "post")
        )
        or 0
    )
    result = {
        "id": user.id,
        "uid": f"LY{user.id:06d}",
        "nickname": user.nickname,
        "phone": user.phone,
        "school": user.school.name,
        "school_id": user.school_id,
        "avatar_url": avatar_url_or_default(user.avatar_url),
        "background_url": user.background_url,
        "bio": user.bio,
        "grade": user.grade,
        "birthday": user.birthday.isoformat() if user.birthday else None,
        "age": calculate_age(user.birthday),
        "gender": user.gender or "unknown",
        "post_count": post_count,
        "like_count": like_count,
        "following_count": user.following_count or 0,
        "followers_count": user.followers_count or 0,
        "warning_score": user.warning_score or 0,
        "wearing_badge": _badge_dict(user.wearing_badge),
        "badge_count": badge_count,
    }
    # 关注关系字段：仅当查看者存在且不是本人时计算
    if viewer and viewer.id != user.id:
        from app.models import Follow
        forward = db.scalar(
            select(Follow).where(
                Follow.follower_id == viewer.id, Follow.followee_id == user.id
            )
        )
        backward = db.scalar(
            select(Follow).where(
                Follow.follower_id == user.id, Follow.followee_id == viewer.id
            )
        )
        result["is_following"] = bool(forward)
        result["is_following_me"] = bool(backward)
        result["is_mutual"] = bool(forward and backward)
    else:
        result["is_following"] = False
        result["is_following_me"] = False
        result["is_mutual"] = False
    # 标记默认好友（官方账号），前端聊天页/主页据此显示“官方账号”
    from app.services.follow_service import _default_friend_ids
    result["is_default_friend"] = user.id in _default_friend_ids(db)
    return result


def update_me(payload: ProfileUpdate, request: Request, db: Session, user: User) -> dict:
    """更新当前用户资料。"""
    changes = payload.model_dump(exclude_unset=True)
    if "school_id" in changes:
        from app.models import School
        school = db.get(School, changes["school_id"])
        if not school:
            raise HTTPException(status_code=400, detail=ErrorCode.SCHOOL_NOT_FOUND)
    for key, value in changes.items():
        setattr(user, key, value)
    log_user_action(db, user.id, "update_profile", json.dumps({"fields": list(changes.keys())}, ensure_ascii=False), _extract_ip(request))
    db.commit()
    db.refresh(user)
    return profile(user, db)


def get_user(user_id: int, db: Session, viewer: User | None = None) -> dict:
    """查询指定用户资料。"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)
    return profile(user, db, viewer=viewer)


def user_posts(user_id: int, db: Session, viewer_id: int | None = None, page: int = 1, page_size: int = 20) -> dict:
    """查询指定用户的帖子列表（分页）。

    使用 post_dict 序列化，保留 ai_status / reject_reason / title 等字段，
    使前端 AiStatusBadge 能正确显示审核状态标签（审核中 / 未通过 / 人工复核中）。

    当 viewer_id 不是帖子作者时，审核中(pending)/被拒(rejected)的帖子标题会被加密，
    替换为"该帖子正在审核中"或"该帖子未通过审核"，防止泄露内容。

    私密帖子（is_public=False）仅作者本人可见，他人查询时直接过滤掉，
    避免出现「列表可见但详情 404」的不一致体验。
    匿名帖子（is_anonymous=True）仅作者本人可见：他人无法通过主页定位到匿名帖作者。

    返回: {items, total, page, page_size}
    """
    is_owner = (viewer_id is not None and viewer_id == user_id)
    # 私密帖子仅作者本人可见；他人查询时只返回公开帖子
    if is_owner:
        stmt = select(Post).where(Post.author_id == user_id, Post.is_draft.is_(False))
    else:
        stmt = select(Post).where(
            Post.author_id == user_id,
            Post.is_draft.is_(False),
            Post.is_anonymous.is_(False),
            or_(Post.is_public.is_(True), Post.author_id == viewer_id) if viewer_id else Post.is_public.is_(True),
        )
    # 总数（在排序/分页前计算）
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    posts = db.scalars(
        stmt.order_by(Post.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    result = []
    for p in posts:
        d = post_dict(p)
        if not is_owner and p.ai_status in ("pending", "rejected", "manual_review"):
            if p.ai_status == "pending":
                d["title"] = "该帖子正在审核中"
                d["content"] = "该帖子正在审核中，暂无法查看原文"
            elif p.ai_status == "rejected":
                d["title"] = "该帖子未通过审核"
                d["content"] = "该帖子未通过审核，暂无法查看原文"
            elif p.ai_status == "manual_review":
                d["title"] = "该帖子正在人工复核"
                d["content"] = "该帖子正在人工复核中，暂无法查看原文"
            d["image_urls"] = []
            d["is_viewable"] = False
            d["view_block_reason"] = p.ai_status
        else:
            d["is_viewable"] = True
        result.append(d)
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def user_likers(user_id: int, db: Session) -> list[dict]:
    """查询点赞过该用户帖子的用户列表（按最近点赞排序，去重）。"""
    from app.models import Follow
    from sqlalchemy.orm import selectinload

    # 找到点赞过该用户帖子的所有记录
    rows = db.execute(
        select(Like.user_id, Like.created_at, Post.id.label("post_id"), Post.content.label("post_content"))
        .join(Post, Post.id == Like.target_id)
        .where(Post.author_id == user_id, Like.target_type == "post")
        .order_by(Like.created_at.desc())
    ).all()

    if not rows:
        return []

    # 去重：每个用户只保留最近一次点赞
    seen = set()
    liker_ids = []
    liker_data = {}  # user_id -> {created_at, post_id, post_content}
    for row in rows:
        uid = row.user_id
        if uid in seen:
            continue
        seen.add(uid)
        liker_ids.append(uid)
        liker_data[uid] = {
            "created_at": to_iso_zh(row.created_at),
            "post_id": row.post_id,
            "post_content": (row.post_content or "")[:50],
        }

    # 批量加载用户
    users = {
        u.id: u
        for u in db.scalars(
            select(User).options(selectinload(User.school)).where(User.id.in_(liker_ids))
        ).all()
    }

    # 当前用户是否关注了这些点赞者
    following_ids = set()
    if liker_ids:
        follows = db.scalars(
            select(Follow.followee_id).where(
                Follow.follower_id == user_id, Follow.followee_id.in_(liker_ids)
            )
        ).all()
        following_ids = set(follows)

    result = []
    for uid in liker_ids:
        u = users.get(uid)
        if not u:
            continue
        info = liker_data[uid]
        result.append({
            "id": u.id,
            "nickname": u.nickname,
            "avatar_url": avatar_url_or_default(u.avatar_url),
            "badge": badge_dict(u.wearing_badge),
            "bio": u.bio,
            "school": u.school.name if u.school else None,
            "grade": u.grade,
            "created_at": info["created_at"],
            "post_id": info["post_id"],
            "post_content": info["post_content"],
            "is_following": uid in following_ids,
        })
    return result


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip

        return extract_ip(request)
    except Exception:
        return None


def badge_dict(badge) -> dict | None:
    """序列化佩戴徽章（避免 service 间循环导入）。"""
    from app.services.badge_service import badge_dict as _badge_dict
    return _badge_dict(badge)


def my_liked_post_ids(user_id: int, db: Session) -> list[int]:
    """查询当前用户点赞过的帖子 ID 列表（用于前端 active 态回填）。"""
    rows = db.scalars(
        select(Like.target_id).where(Like.user_id == user_id, Like.target_type == "post")
    ).all()
    return list(rows)


def my_favorited_post_ids(user_id: int, db: Session) -> list[int]:
    """查询当前用户收藏过的帖子 ID 列表（用于前端 active 态回填）。"""
    rows = db.scalars(select(Favorite.post_id).where(Favorite.user_id == user_id)).all()
    return list(rows)


def my_liked_comment_ids(user_id: int, db: Session) -> list[int]:
    """查询当前用户点赞过的评论 ID 列表。"""
    rows = db.scalars(
        select(Like.target_id).where(Like.user_id == user_id, Like.target_type == "comment")
    ).all()
    return list(rows)


def my_drafts(user_id: int, db: Session) -> list[dict]:
    """查询当前用户的草稿列表（T5-3，is_draft=True 的帖子）。"""
    rows = db.scalars(
        select(Post).where(Post.author_id == user_id, Post.is_draft.is_(True)).order_by(Post.updated_at.desc())
    ).all()
    return [post_dict(p) for p in rows]


def my_favorite_posts(user_id: int, db: Session, page: int = 1, page_size: int = 20) -> dict:
    """查询当前用户收藏的帖子完整列表（T5-4，join favorites + posts，分页）。

    返回: {items, total, page, page_size}
    """
    stmt = (
        select(Post)
        .join(Favorite, Favorite.post_id == Post.id)
        .where(Favorite.user_id == user_id)
    )
    # 总数（在排序/分页前计算）
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Favorite.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [post_dict(p) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def my_liked_posts(user_id: int, db: Session, page: int = 1, page_size: int = 20) -> dict:
    """查询当前用户点赞过的帖子完整列表（T5-1 点赞 Tab，分页）。

    返回: {items, total, page, page_size}
    """
    stmt = (
        select(Post)
        .join(Like, Like.target_id == Post.id)
        .where(Like.user_id == user_id, Like.target_type == "post")
    )
    # 总数（在排序/分页前计算）
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Like.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [post_dict(p) for p in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ============ 封号状态 & 申诉 ============

def get_ban_status(user: User, db: Session) -> dict:
    """获取当前用户的封号状态。

    同时返回警告值阈值，供前端 Banned.vue 在 warningStatus 加载失败时仍有阈值兜底，
    避免 0/100 误导（perm_ban_threshold fallback 硬编码）。
    """
    from app.core.time_utils import now_utc
    from app.services import warning_service
    is_banned = False
    ban_until = None
    ban_reason = None
    if user.ban_until:
        if user.ban_until > now_utc():
            is_banned = True
            ban_until = to_iso_zh(user.ban_until)
            ban_reason = user.ban_reason
        else:
            # 封禁已过期，自动恢复
            user.is_active = True
            user.ban_until = None
            user.ban_reason = None
    elif not user.is_active:
        # 永久封禁（ban_until 为 None 但 is_active 为 False）
        is_banned = True
        ban_reason = user.ban_reason

    # 取警告值阈值（失败时回落到默认，避免阻塞封号状态查询）
    try:
        cfg = warning_service.get_warning_config(db)
        warn_threshold = cfg.warn_threshold
        temp_ban_threshold = cfg.temp_ban_threshold
        temp_ban_hours = cfg.temp_ban_hours
        perm_ban_threshold = cfg.perm_ban_threshold
    except Exception:
        warn_threshold = 30
        temp_ban_threshold = 60
        temp_ban_hours = 24
        perm_ban_threshold = 100

    return {
        "is_banned": is_banned,
        "ban_until": ban_until,
        "ban_reason": ban_reason,
        "violation_count": user.violation_count or 0,
        "warning_score": user.warning_score or 0,
        "warn_threshold": warn_threshold,
        "temp_ban_threshold": temp_ban_threshold,
        "temp_ban_hours": temp_ban_hours,
        "perm_ban_threshold": perm_ban_threshold,
    }


def create_appeal(user: User, reason: str, ban_record_id: int | None, db: Session) -> dict:
    """用户提交申诉。"""
    from app.models import Appeal
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="请填写申诉理由")

    appeal = Appeal(
        user_id=user.id,
        ban_record_id=ban_record_id,
        reason=reason,
        status="pending",
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return _appeal_dict(appeal, db)


def my_appeals(user: User, db: Session) -> list[dict]:
    """查询当前用户的申诉列表。"""
    from app.models import Appeal
    rows = db.scalars(
        select(Appeal).where(Appeal.user_id == user.id).order_by(Appeal.created_at.desc())
    ).all()
    return [_appeal_dict(a, db) for a in rows]


def _appeal_dict(a, db: Session) -> dict:
    return {
        "id": a.id,
        "ban_record_id": a.ban_record_id,
        "reason": a.reason,
        "status": a.status,
        "reviewed_at": to_iso_zh(a.reviewed_at) if a.reviewed_at else None,
        "review_comment": a.review_comment,
        "created_at": to_iso_zh(a.created_at),
    }


def recent_users(
    db: Session, page: int = 1, page_size: int = 20, q: str | None = None
) -> dict:
    """最新注册用户列表（分页，按注册时间倒序）。"""
    from sqlalchemy.orm import selectinload

    query = select(User)
    keyword = (q or "").strip()
    if keyword:
        query = query.where(User.nickname.like(f"%{keyword}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query
        .options(selectinload(User.school))
        .order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": u.id,
            "nickname": u.nickname,
            "avatar_url": u.avatar_url,
            "badge": badge_dict(u.wearing_badge),
            "school": u.school.name if u.school else None,
            "created_at": to_iso_zh(u.created_at),
        }
        for u in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
