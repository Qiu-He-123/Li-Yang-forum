"""通用留言板业务逻辑层（组局/活动留言）。"""

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
from app.models import Activity, Gathering, TargetComment, User
from app.services.avatar import avatar_url_or_default

# 支持的留言目标类型（match 为功能页全局留言板，无实体表，值为 None）
TARGET_TYPES = {"gathering": Gathering, "activity": Activity, "match": None}


def _validate_target(db: Session, target_type: str, target_id: int) -> None:
    """校验留言目标存在，不存在则 404。"""
    if target_type not in TARGET_TYPES:
        raise HTTPException(status_code=404, detail="留言目标类型不存在")
    if target_type == "match":
        # 热门玩法/在线匹配页：全局留言板，target_id 固定为 1，无需查表
        if target_id != 1:
            raise HTTPException(status_code=404, detail="留言目标不存在")
        return
    if not db.get(TARGET_TYPES[target_type], target_id):
        raise HTTPException(status_code=404, detail="留言目标不存在")


def _comment_dict(comment: TargetComment, user: User | None) -> dict:
    return {
        "id": comment.id,
        "target_type": comment.target_type,
        "target_id": comment.target_id,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "author": user.nickname if user else "同学",
        "author_avatar_url": avatar_url_or_default(user.avatar_url if user else None),
        "user_id": comment.user_id,
        "created_at": to_iso_zh(comment.created_at),
    }


def list_comments(
    db: Session,
    target_type: str,
    target_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询留言列表（按楼层分页：先分页根留言，再带出所有子孙回复）。"""
    _validate_target(db, target_type, target_id)

    total_count = db.scalar(
        select(func.count(TargetComment.id)).where(
            TargetComment.target_type == target_type,
            TargetComment.target_id == target_id,
            TargetComment.parent_id.is_(None),
        )
    ) or 0

    offset = (page - 1) * page_size
    roots = list(
        db.scalars(
            select(TargetComment)
            .where(
                TargetComment.target_type == target_type,
                TargetComment.target_id == target_id,
                TargetComment.parent_id.is_(None),
            )
            .order_by(desc(TargetComment.created_at))
            .offset(offset)
            .limit(page_size)
        ).all()
    )
    if not roots:
        return {"items": [], "total": total_count, "page": page, "page_size": page_size}

    root_ids = [r.id for r in roots]

    # 查出该目标所有回复，按 parent_id 建树，收集当前页根留言的所有子孙
    all_replies = list(
        db.scalars(
            select(TargetComment)
            .where(
                TargetComment.target_type == target_type,
                TargetComment.target_id == target_id,
                TargetComment.parent_id.is_not(None),
            )
            .order_by(TargetComment.created_at)
        ).all()
    )
    children_map: dict[int, list[TargetComment]] = {}
    for reply in all_replies:
        children_map.setdefault(reply.parent_id, []).append(reply)

    def _collect_descendants(parent_ids: list[int]) -> list[TargetComment]:
        result: list[TargetComment] = []
        for pid in parent_ids:
            for child in children_map.get(pid, []):
                result.append(child)
                result.extend(_collect_descendants([child.id]))
        return result

    descendants = _collect_descendants(root_ids)
    all_comments = roots + descendants

    user_ids = {item.user_id for item in all_comments if item.user_id is not None}
    users = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
        if user_ids
        else {}
    )
    return {
        "items": [_comment_dict(item, users.get(item.user_id)) for item in all_comments],
        "total": total_count,
        "page": page,
        "page_size": page_size,
    }


def create_comment(
    db: Session,
    target_type: str,
    target_id: int,
    payload,
    user: User,
) -> dict:
    """发表留言（content 1-500 字，parent_id 可选）。"""
    _validate_target(db, target_type, target_id)
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="留言内容不能为空")
    if len(content) > 500:
        raise HTTPException(status_code=400, detail="留言内容不能超过 500 字")
    if payload.parent_id:
        parent = db.get(TargetComment, payload.parent_id)
        if not parent or parent.target_type != target_type or parent.target_id != target_id:
            raise HTTPException(status_code=404, detail="被回复的留言不存在")

    # 封号用户禁止留言
    from app.services import user_service

    if user_service.get_ban_status(user, db)["is_banned"]:
        raise HTTPException(status_code=403, detail="账号已被封禁")

    comment = TargetComment(
        target_type=target_type,
        target_id=target_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        content=content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_dict(comment, user)


def delete_comment(
    db: Session,
    target_type: str,
    target_id: int,
    comment_id: int,
    user: User,
) -> dict:
    """删除留言（仅作者本人；根留言会级联删除其所有回复）。"""
    comment = db.get(TargetComment, comment_id)
    if not comment or comment.target_type != target_type or comment.target_id != target_id:
        raise HTTPException(status_code=404, detail="留言不存在")
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权删除他人留言")

    # 级联删除所有子孙回复
    all_replies = list(
        db.scalars(
            select(TargetComment).where(
                TargetComment.target_type == target_type,
                TargetComment.target_id == target_id,
                TargetComment.parent_id.is_not(None),
            )
        ).all()
    )
    children_map: dict[int, list[TargetComment]] = {}
    for reply in all_replies:
        children_map.setdefault(reply.parent_id, []).append(reply)

    def _collect_descendants(parent_id: int) -> list[TargetComment]:
        result: list[TargetComment] = []
        for child in children_map.get(parent_id, []):
            result.append(child)
            result.extend(_collect_descendants(child.id))
        return result

    for reply in _collect_descendants(comment_id):
        db.delete(reply)
    db.delete(comment)
    db.commit()

    remaining = db.scalar(
        select(func.count(TargetComment.id)).where(
            TargetComment.target_type == target_type,
            TargetComment.target_id == target_id,
        )
    ) or 0
    return {"deleted": True, "remaining_count": remaining}
