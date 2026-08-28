"""话题业务逻辑层（阶段二）。

负责话题搜索、详情、关注/取消关注、列出话题下的帖子。
"""
from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Post, Topic, TopicFollow, User
from app.services import post_service


def get_or_create_topic(db: Session, name: str, creator_id: int | None = None) -> Topic:
    """获取或创建话题（按 name 唯一）。

    Args:
        db: Session
        name: 话题名称（已 trim+lower 处理保持原始大小写）
        creator_id: 创建者用户 id（可选）

    Returns:
        Topic 实例
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
    topic = db.scalar(select(Topic).where(Topic.name == name))
    if topic:
        return topic
    topic = Topic(name=name, creator_id=creator_id, post_count=0)
    db.add(topic)
    db.flush()
    return topic


def search_topics(db: Session, q: str, limit: int = 10) -> list[dict]:
    """搜索话题（按 name 模糊匹配，按 post_count 降序）。

    Args:
        db: Session
        q: 搜索关键词
        limit: 最多返回条数

    Returns:
        话题字典列表
    """
    q = (q or "").strip()
    stmt = select(Topic)
    if q:
        stmt = stmt.where(Topic.name.like(f"%{q}%"))
    stmt = stmt.order_by(desc(Topic.post_count), desc(Topic.created_at)).limit(max(1, min(50, limit)))
    rows = db.scalars(stmt).all()
    return [_topic_dict(t) for t in rows]


def hot_topics(db: Session, limit: int = 10) -> list[dict]:
    """获取热门话题（按 post_count 降序，仅返回 post_count > 0 的话题）。

    Args:
        db: Session
        limit: 最多返回条数

    Returns:
        话题字典列表
    """
    stmt = (
        select(Topic)
        .where(Topic.post_count > 0)
        .order_by(desc(Topic.post_count), desc(Topic.created_at))
        .limit(max(1, min(50, limit)))
    )
    rows = db.scalars(stmt).all()
    return [_topic_dict(t) for t in rows]


def _topic_dict(t: Topic, is_followed: bool | None = None) -> dict:
    """序列化话题为前端响应字典。"""
    data = {
        "id": t.id,
        "name": t.name,
        "creator_id": t.creator_id,
        "post_count": t.post_count,
        "description": t.description,
        "created_at": to_iso_zh(t.created_at),
    }
    if is_followed is not None:
        data["is_followed"] = is_followed
    return data


def get_topic_detail(db: Session, topic_id: int, user: User | None = None) -> dict | None:
    """获取话题详情（含当前用户是否已关注）。"""
    topic = db.get(Topic, topic_id)
    if not topic:
        return None
    is_followed = False
    if user is not None:
        is_followed = db.scalar(
            select(TopicFollow.id).where(
                TopicFollow.user_id == user.id,
                TopicFollow.topic_id == topic_id,
            )
        ) is not None
    return _topic_dict(topic, is_followed=is_followed)


def follow_topic(db: Session, user: User, topic_id: int) -> bool:
    """关注/取消关注话题（toggle）。

    Returns:
        True 表示已关注（刚关注），False 表示已取消关注
    """
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    existing = db.scalar(
        select(TopicFollow).where(
            TopicFollow.user_id == user.id,
            TopicFollow.topic_id == topic_id,
        )
    )
    if existing:
        db.delete(existing)
        db.commit()
        return False
    db.add(TopicFollow(user_id=user.id, topic_id=topic_id))
    db.commit()
    return True


def list_topic_posts(
    db: Session,
    topic_id: int,
    page: int = 1,
    page_size: int = 20,
    user: User | None = None,
) -> dict:
    """列出话题下的帖子（分页）。

    权限规则同 list_posts：非作者本人私密帖不可见。
    """
    from sqlalchemy import or_

    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)

    query = (
        select(Post)
        .where(Post.topic_id == topic_id, Post.is_draft.is_(False))
    )
    if user is not None:
        query = query.where(or_(Post.is_public.is_(True), Post.author_id == user.id))
    else:
        query = query.where(Post.is_public.is_(True))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    query = query.order_by(desc(Post.created_at)).offset((page - 1) * page_size).limit(page_size)
    posts = db.scalars(query).all()

    # 复用 post_service.post_dict 时需要 author/school 已加载，这里直接用 lazy load
    return {
        "items": [post_service.post_dict(p) for p in posts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "topic": _topic_dict(topic),
    }


def notify_topic_followers(db: Session, post_id: int, topic_id: int, from_user_id: int) -> None:
    """话题有新帖时，给关注该话题的用户发 type='topic' 通知（不 commit）。

    Args:
        db: Session
        post_id: 新帖 id
        topic_id: 话题 id
        from_user_id: 发帖人 id
    """
    from app.services import notification_service

    topic = db.get(Topic, topic_id)
    if not topic:
        return
    # 取关注者
    follower_ids = db.scalars(
        select(TopicFollow.user_id).where(TopicFollow.topic_id == topic_id)
    ).all()
    for uid in follower_ids:
        if uid == from_user_id:
            continue  # 不给自己发
        notification_service.create_notification(
            db,
            user_id=uid,
            title="话题有新帖",
            content=f"话题 #{topic.name} 有新帖子",
            ntype="topic",
            sender_id=from_user_id,
            reference_type="post",
            reference_id=post_id,
        )


def get_topic_name(db: Session, topic_id: int | None) -> str | None:
    """根据 topic_id 查询话题名（用于 post_dict 输出）。"""
    if not topic_id:
        return None
    topic = db.get(Topic, topic_id)
    return topic.name if topic else None
