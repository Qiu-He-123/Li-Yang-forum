"""意见反馈业务逻辑层。

- create_feedback: 用户创建反馈
- list_my_feedbacks: 查看自己的反馈列表（分页）
- list_all_feedbacks: 管理员查看所有反馈（分页，支持状态过滤）
- get_feedback: 查看反馈详情（用户只能看自己的，管理员可看所有）
- reply_feedback: 管理员回复反馈（同时更新状态为 replied）
- close_feedback: 关闭反馈
"""
from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Admin, Feedback, FeedbackReply, User


def create_feedback(db: Session, user_id: int, payload) -> dict:
    """创建反馈。"""
    feedback = Feedback(
        user_id=user_id,
        category=payload.category,
        title=payload.title,
        content=payload.content,
        contact=payload.contact,
        image_urls=payload.image_urls,
        status="pending",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return _feedback_to_dict(db, feedback, include_replies=True)


def list_my_feedbacks(db: Session, user_id: int, page: int = 1, page_size: int = 20) -> dict:
    """查看自己的反馈列表（分页，按创建时间倒序）。"""
    offset = (page - 1) * page_size
    total = db.scalar(
        select(func.count(Feedback.id)).where(Feedback.user_id == user_id)
    ) or 0
    rows = db.scalars(
        select(Feedback)
        .where(Feedback.user_id == user_id)
        .order_by(desc(Feedback.created_at))
        .offset(offset)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "items": [_feedback_to_dict(db, f, include_replies=True) for f in rows],
        "page": page,
        "page_size": page_size,
    }


def list_all_feedbacks(
    db: Session, page: int = 1, page_size: int = 20, status_filter: str | None = None
) -> dict:
    """管理员查看所有反馈（分页，支持状态过滤）。"""
    stmt = select(Feedback)
    count_stmt = select(func.count(Feedback.id))
    if status_filter:
        stmt = stmt.where(Feedback.status == status_filter)
        count_stmt = count_stmt.where(Feedback.status == status_filter)
    total = db.scalar(count_stmt) or 0
    offset = (page - 1) * page_size
    rows = db.scalars(
        stmt.order_by(desc(Feedback.created_at)).offset(offset).limit(page_size)
    ).all()
    return {
        "total": total,
        "items": [_feedback_to_dict(db, f, include_replies=True) for f in rows],
        "page": page,
        "page_size": page_size,
    }


def get_feedback(db: Session, feedback_id: int, user_id: int, is_admin: bool = False) -> dict:
    """查看反馈详情（用户只能看自己的，管理员可看所有）。"""
    feedback = db.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if not is_admin and feedback.user_id != user_id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    return _feedback_to_dict(db, feedback, include_replies=True)


def reply_feedback(db: Session, feedback_id: int, replier_id: int, content: str) -> dict:
    """管理员回复反馈（同时更新状态为 replied）。"""
    feedback = db.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    reply = FeedbackReply(
        feedback_id=feedback_id,
        replier_id=replier_id,
        content=content,
    )
    db.add(reply)
    feedback.status = "replied"
    db.commit()
    db.refresh(feedback)
    db.refresh(reply)
    return _feedback_to_dict(db, feedback, include_replies=True)


def close_feedback(db: Session, feedback_id: int) -> dict:
    """关闭反馈。"""
    feedback = db.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    feedback.status = "closed"
    db.commit()
    db.refresh(feedback)
    return _feedback_to_dict(db, feedback, include_replies=True)


def _feedback_to_dict(db: Session, f: Feedback, include_replies: bool = True) -> dict:
    """序列化反馈详情（含 user_name 和 replies）。"""
    user = db.get(User, f.user_id)
    data = {
        "id": f.id,
        "user_id": f.user_id,
        "user_name": user.nickname if user else None,
        "category": f.category,
        "title": f.title,
        "content": f.content,
        "contact": f.contact,
        "status": f.status,
        "image_urls": f.image_urls,
        "replies": [],
        "created_at": to_iso_zh(f.created_at),
    }
    if include_replies and f.replies:
        for r in f.replies:
            data["replies"].append(_reply_to_dict(db, r))
    return data


def _reply_to_dict(db: Session, r: FeedbackReply) -> dict:
    """序列化回复详情（含 replier_name，优先查 users 表，未命中查 admin 表）。"""
    replier_name = None
    user = db.get(User, r.replier_id)
    if user:
        replier_name = user.nickname
    else:
        admin = db.get(Admin, r.replier_id)
        if admin:
            replier_name = admin.username
    return {
        "id": r.id,
        "feedback_id": r.feedback_id,
        "replier_id": r.replier_id,
        "replier_name": replier_name,
        "content": r.content,
        "created_at": to_iso_zh(r.created_at),
    }
