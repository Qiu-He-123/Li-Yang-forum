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
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
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
    return {
        "items": [_notification_dict(n) for n in rows],
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
        post_id = n.reference_id
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
        n.read_at = datetime.now()
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
    now = datetime.now()
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return {"updated": len(rows)}


def unread_count(user_id: int, db: Session) -> dict:
    """返回未读通知总数 + 各类型未读数（前端红点 + 分类 badge 用）。"""
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
