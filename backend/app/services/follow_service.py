"""关注业务逻辑层。

- 关注/取关（幂等，更新计数 + 触发通知）
- 关注列表 / 粉丝列表
- 是否已关注
"""
from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Follow, School, User
from app.services.notification_service import create_notification


def follow_user(db: Session, follower: User, followee_id: int) -> dict:
    """关注用户（幂等）。

    - 不允许关注自己
    - 更新 follower.following_count 和 followee.followers_count
    - 触发 type=follow 通知给被关注者
    """
    if follower.id == followee_id:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)

    followee = db.get(User, followee_id)
    if not followee or not followee.is_active:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)

    existing = db.scalar(
        select(Follow).where(
            Follow.follower_id == follower.id, Follow.followee_id == followee_id
        )
    )
    if not existing:
        db.add(Follow(follower_id=follower.id, followee_id=followee_id))
        follower.following_count = (follower.following_count or 0) + 1
        followee.followers_count = (followee.followers_count or 0) + 1
        # 通知被关注者（create_notification 内部已过滤自己关注自己的情况）
        create_notification(
            db,
            followee_id,
            "收到关注",
            f"{follower.nickname} 关注了你",
            ntype="follow",
            sender_id=follower.id,
            reference_type="user",
            reference_id=follower.id,
        )
        db.commit()
        db.refresh(follower)
        db.refresh(followee)
        # 徽章自动发放：粉丝数达到规则阈值自动发徽章
        try:
            from app.services.badge_service import auto_grant_by_action
            auto_grant_by_action(db, followee, "followers_count", followee.followers_count or 0)
        except Exception:
            pass
    return {
        "user_id": followee_id,
        "is_following": True,
        "following_count": follower.following_count,
        "followers_count": followee.followers_count,
    }


def unfollow_user(db: Session, follower: User, followee_id: int) -> dict:
    """取关用户（幂等）。"""
    followee = db.get(User, followee_id)
    if not followee:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)

    existing = db.scalar(
        select(Follow).where(
            Follow.follower_id == follower.id, Follow.followee_id == followee_id
        )
    )
    if existing:
        db.delete(existing)
        if follower.following_count and follower.following_count > 0:
            follower.following_count -= 1
        if followee.followers_count and followee.followers_count > 0:
            followee.followers_count -= 1
        db.commit()
        db.refresh(follower)
        db.refresh(followee)
    return {
        "user_id": followee_id,
        "is_following": False,
        "following_count": follower.following_count,
        "followers_count": followee.followers_count if followee else 0,
    }


def is_following(db: Session, user: User, target_id: int) -> dict:
    """查询当前用户是否已关注 target_id，同时返回互关状态。"""
    if user.id == target_id:
        return {"user_id": target_id, "is_following": False, "is_self": True, "is_mutual": False}
    forward = db.scalar(
        select(Follow).where(
            Follow.follower_id == user.id, Follow.followee_id == target_id
        )
    )
    backward = db.scalar(
        select(Follow).where(
            Follow.follower_id == target_id, Follow.followee_id == user.id
        )
    )
    return {
        "user_id": target_id,
        "is_following": bool(forward),
        "is_self": False,
        "is_mutual": bool(forward and backward),
    }


def is_mutual_follow(db: Session, user_a_id: int, user_b_id: int) -> bool:
    """检查两个用户是否互相关注（双向关注）。"""
    if user_a_id == user_b_id:
        return False
    forward = db.scalar(
        select(Follow).where(
            Follow.follower_id == user_a_id, Follow.followee_id == user_b_id
        )
    )
    if not forward:
        return False
    backward = db.scalar(
        select(Follow).where(
            Follow.follower_id == user_b_id, Follow.followee_id == user_a_id
        )
    )
    return bool(backward)


def list_following(db: Session, user_id: int, current_user_id: int | None = None) -> list[dict]:
    """查询 user_id 关注的用户列表（最新关注在前）。

    current_user_id 用于计算 is_following 字段（当前登录用户是否已关注列表中的每个人）。
    """
    rows = db.scalars(
        select(Follow)
        .where(Follow.follower_id == user_id)
        .order_by(Follow.created_at.desc())
    ).all()
    if not rows:
        return []
    target_ids = [r.followee_id for r in rows]
    users = (
        {u.id: u for u in db.scalars(
            select(User).options(selectinload(User.school)).where(User.id.in_(target_ids))
        ).all()}
        if target_ids else {}
    )
    # 批量查询当前用户关注了哪些 target_ids，避免 N+1
    following_set = _batch_following_ids(db, current_user_id, target_ids) if current_user_id else set()
    result: list[dict] = []
    for r in rows:
        u = users.get(r.followee_id)
        if not u:
            continue
        result.append(_follow_dict(u, r.created_at, following_set))
    return result


def list_followers(db: Session, user_id: int, current_user_id: int | None = None) -> list[dict]:
    """查询 user_id 的粉丝列表（最新关注在前）。

    current_user_id 用于计算 is_following 字段。
    """
    rows = db.scalars(
        select(Follow)
        .where(Follow.followee_id == user_id)
        .order_by(Follow.created_at.desc())
    ).all()
    if not rows:
        return []
    target_ids = [r.follower_id for r in rows]
    users = (
        {u.id: u for u in db.scalars(
            select(User).options(selectinload(User.school)).where(User.id.in_(target_ids))
        ).all()}
        if target_ids else {}
    )
    following_set = _batch_following_ids(db, current_user_id, target_ids) if current_user_id else set()
    result: list[dict] = []
    for r in rows:
        u = users.get(r.follower_id)
        if not u:
            continue
        result.append(_follow_dict(u, r.created_at, following_set))
    return result


def _batch_following_ids(db: Session, current_user_id: int | None, target_ids: list[int]) -> set[int]:
    """批量查询 current_user_id 关注了 target_ids 中的哪些，返回已关注的 id 集合。"""
    if not current_user_id or not target_ids:
        return set()
    rows = db.scalars(
        select(Follow.followee_id).where(
            Follow.follower_id == current_user_id,
            Follow.followee_id.in_(target_ids),
        )
    ).all()
    return set(rows)


def _follow_dict(u: User, created_at, following_set: set[int] | None = None) -> dict:
    """序列化关注/粉丝列表项。

    关键：id 字段返回的是「用户 ID」（不是关注记录 ID），与前端
    FollowUser 类型对齐——前端点击列表项时直接用 id 跳转到 /user/{id}。
    之前的 bug 是返回了 follow_id（关注记录 ID），导致跳转到错误用户。
    is_following 表示「当前登录用户是否已关注此人」，用于前端按钮状态。
    """
    is_following = False
    if following_set is not None and u.id in following_set:
        is_following = True
    from app.services.badge_service import badge_dict as _badge_dict
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "badge": _badge_dict(getattr(u, "wearing_badge", None)),
        "bio": u.bio,
        "school": u.school.name if u.school else None,
        "grade": u.grade,
        "is_following": is_following,
        "created_at": to_iso_zh(created_at),
    }
