"""通知业务逻辑层（T5-5）。

互动发生时（点赞/评论/收藏/关注）由 interactions_service / comment_service /
follow_service 调用本模块写入通知。

通知类型 type：
- interaction: 互动（通用，如收藏）
- comment: 评论
- like: 点赞
- follow: 关注
- system: 系统通知
- announcement: 公告
- mention: @提及（阶段二）
- topic: 话题新帖（阶段二）
- vote_end: 投票结束（阶段二）
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.time_utils import now_utc, to_iso_zh
from app.models import Notification


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    content: str,
    *,
    ntype: str = "system",
    sender_id: int | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
) -> None:
    """写一条通知（不 commit，由调用方统一提交）。

    Args:
        user_id: 通知接收人
        title: 通知标题
        content: 通知内容
        ntype: 通知类型（interaction/comment/like/follow/system/announcement）
        sender_id: 触发通知的用户 id（系统通知为 None）
        reference_type: 关联对象类型（post/comment/user）
        reference_id: 关联对象 id
    """
    if user_id <= 0:
        return
    # 不允许给自己发互动类通知（点赞/评论/关注/收藏）
    if sender_id is not None and sender_id == user_id and ntype != "system":
        return
    db.add(
        Notification(
            user_id=user_id,
            title=title[:100],
            content=content,
            type=ntype,
            sender_id=sender_id,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )


def cleanup_notifications_for_deleted_comments(db: Session, comment_ids: list[int]) -> None:
    """评论删除后清理关联通知（收到评论/评论审核通知等），不 commit。"""
    ids = [i for i in (comment_ids or []) if i is not None]
    if not ids:
        return
    db.execute(
        delete(Notification).where(
            Notification.reference_type == "comment",
            Notification.reference_id.in_(ids),
        )
    )


def cleanup_notifications_for_deleted_posts(db: Session, post_id: int) -> None:
    """帖子删除后清理关联互动通知（点赞/收藏/@提及等），不 commit。

    保留 type='system' 的系统通知（如"帖子已被管理员删除"的历史留痕）。
    """
    db.execute(
        delete(Notification).where(
            Notification.reference_type == "post",
            Notification.reference_id == post_id,
            Notification.type != "system",
        )
    )


def _cleanup_stale_notifications(db: Session, user_id: int) -> None:
    """懒清理：删除当前用户指向已删除帖子/评论的互动通知（保留 system 通知）。

    修复历史遗留脏数据：帖子/评论被删除后，旧通知仍展示在消息列表。
    """
    from app.models import Comment, Post

    db.execute(
        delete(Notification).where(
            Notification.user_id == user_id,
            Notification.type != "system",
            Notification.reference_type == "post",
            Notification.reference_id.is_not(None),
            ~Notification.reference_id.in_(select(Post.id)),
        )
    )
    db.execute(
        delete(Notification).where(
            Notification.user_id == user_id,
            Notification.reference_type == "comment",
            Notification.reference_id.is_not(None),
            ~Notification.reference_id.in_(select(Comment.id)),
        )
    )
    db.commit()


def list_notifications(
    user_id: int,
    db: Session,
    ntype: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询当前用户的通知列表（最新在前），支持按类型过滤与分页。

    Args:
        user_id: 用户 id
        db: Session
        ntype: 通知类型过滤（None 表示全部）
        page: 页码
        page_size: 每页条数

    Returns: {items, total, page, page_size}
    """
    # 先清理指向已删除内容的旧通知，避免消息列表展示失效内容
    _cleanup_stale_notifications(db, user_id)

    query = select(Notification).where(Notification.user_id == user_id)
    if ntype:
        query = query.where(Notification.type == ntype)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_notification_dict(n) for n in rows]
    # 为帖子/评论类通知补充 post_id，前端跳转原帖用（评论的 reference_id 是 comment_id）
    from app.models import Comment, Post

    post_refs = {
        n.reference_id for n in rows if n.reference_type == "post" and n.reference_id
    }
    comment_refs = {
        n.reference_id for n in rows if n.reference_type == "comment" and n.reference_id
    }
    alive_posts = (
        set(db.scalars(select(Post.id).where(Post.id.in_(post_refs)))) if post_refs else set()
    )
    comment_post: dict[int, int] = {}
    if comment_refs:
        for c in db.scalars(select(Comment).where(Comment.id.in_(comment_refs))):
            comment_post[c.id] = c.post_id
    for n, d in zip(rows, items):
        if n.reference_type == "post":
            d["post_id"] = n.reference_id if n.reference_id in alive_posts else None
        elif n.reference_type == "comment":
            d["post_id"] = comment_post.get(n.reference_id)
        else:
            d["post_id"] = None
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _notification_dict(n: Notification) -> dict:
    """序列化通知为前端响应字典。"""
    return {
        "id": n.id,
        "user_id": n.user_id,
        "title": n.title,
        "content": n.content,
        "is_read": n.is_read,
        "type": n.type,
        "sender_id": n.sender_id,
        "reference_type": n.reference_type,
        "reference_id": n.reference_id,
        "read_at": to_iso_zh(n.read_at),
        "created_at": to_iso_zh(n.created_at),
    }


def get_notification(notification_id: int, user_id: int, db: Session) -> dict:
    """查询单条通知详情（仅本人可查）。"""
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user_id:
        from app.core.errors import ErrorCode
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=ErrorCode.NOT_FOUND)
    # 附带 post_id（如果 reference 是评论，需要查 post_id）
    post_id: int | None = None
    if n.reference_type == "post":
        from app.models import Post
        # 帖子已删除则不提供跳转目标
        post_id = n.reference_id if db.get(Post, n.reference_id) else None
    elif n.reference_type == "comment" and n.reference_id:
        from app.models import Comment
        comment = db.get(Comment, n.reference_id)
        if comment:
            post_id = comment.post_id
    data = _notification_dict(n)
    data["post_id"] = post_id
    return data


def mark_read(notification_id: int, user_id: int, db: Session) -> dict:
    """标记单条通知为已读（仅本人可操作）。"""
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user_id:
        return {"id": notification_id, "is_read": False}
    if not n.is_read:
        n.is_read = True
        n.read_at = now_utc()
        db.commit()
    return {"id": n.id, "is_read": True}


def mark_all_read(user_id: int, db: Session, ntype: str | None = None) -> dict:
    """全部已读（可按类型过滤）。"""
    query = (
        select(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )
    if ntype:
        query = query.where(Notification.type == ntype)
    rows = db.scalars(query).all()
    now = now_utc()
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return {"updated": len(rows)}


def unread_count(user_id: int, db: Session) -> dict:
    """返回未读通知总数 + 各类型未读数（前端红点 + 分类 badge 用）。"""
    _cleanup_stale_notifications(db, user_id)
    count = db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )
    # 按类型统计未读（含阶段二新增 mention/topic/vote_end）
    type_counts = {}
    for ntype in ["comment", "like", "follow", "system", "interaction", "announcement", "mention", "topic", "vote_end"]:
        tc = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.type == ntype,
            )
        )
        type_counts[ntype] = int(tc or 0)
    return {"unread": int(count or 0), "by_type": type_counts}
