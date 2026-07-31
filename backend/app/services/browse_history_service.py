"""用户浏览历史业务逻辑层。

- record_view: 记录用户浏览帖子（幂等，重复浏览更新 viewed_at）
- list_history: 获取浏览历史列表（分页，按浏览时间倒序）
- clear_history: 清空浏览历史
- delete_one: 删除单条浏览记录
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.time_utils import to_iso_zh
from app.models import BrowseHistory, Post, User


def record_view(db: Session, user_id: int, post_id: int) -> dict:
    """记录用户浏览帖子（幂等）。

    - 已存在记录：更新 viewed_at 为当前时间
    - 不存在：新增记录
    - 帖子不存在：忽略，不报错（避免影响正常浏览流程）
    """
    post = db.get(Post, post_id)
    if not post:
        return {"recorded": False, "reason": "post_not_found"}

    existing = db.scalar(
        select(BrowseHistory).where(
            BrowseHistory.user_id == user_id,
            BrowseHistory.post_id == post_id,
        )
    )
    if existing:
        existing.viewed_at = datetime.now()
    else:
        record = BrowseHistory(user_id=user_id, post_id=post_id, viewed_at=datetime.now())
        db.add(record)
    db.commit()
    return {"recorded": True}


def list_history(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
    """获取浏览历史列表（分页，按浏览时间倒序）。"""
    offset = (page - 1) * page_size
    # 查询总数
    total = db.scalar(
        select(BrowseHistory).where(BrowseHistory.user_id == user.id)
    )
    total_count = 0
    # 用 count 查询
    from sqlalchemy import func
    total_count = db.scalar(
        select(func.count(BrowseHistory.id)).where(BrowseHistory.user_id == user.id)
    ) or 0

    # 查询历史记录 + 关联帖子
    rows = db.scalars(
        select(BrowseHistory)
        .where(BrowseHistory.user_id == user.id)
        .order_by(desc(BrowseHistory.viewed_at))
        .offset(offset)
        .limit(page_size)
    ).all()

    if not rows:
        return {"items": [], "total": total_count, "page": page, "page_size": page_size}

    post_ids = [r.post_id for r in rows]
    posts = (
        {p.id: p for p in db.scalars(
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.school))
            .where(Post.id.in_(post_ids))
        ).all()}
        if post_ids else {}
    )

    items = []
    for r in rows:
        p = posts.get(r.post_id)
        if not p:
            continue  # 帖子已删除
        # 解析 image_urls JSON
        import json
        try:
            image_urls = json.loads(p.image_urls) if p.image_urls else []
        except (json.JSONDecodeError, TypeError):
            image_urls = []

        items.append({
            "history_id": r.id,
            "post_id": p.id,
            "title": p.title,
            "content": p.content[:200] if p.content else "",
            "image_urls": image_urls[:3],  # 最多返回前 3 张图
            "category": p.category,
            "author_id": p.author_id,
            "author_nickname": p.author.nickname if p.author else None,
            "author_avatar_url": p.author.avatar_url if p.author else None,
            "like_count": p.like_count,
            "comment_count": p.comment_count,
            "view_count": p.view_count,
            "viewed_at": to_iso_zh(r.viewed_at),
        })

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "page_size": page_size,
    }


def delete_one(db: Session, user: User, history_id: int) -> dict:
    """删除单条浏览记录。"""
    record = db.get(BrowseHistory, history_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="浏览记录不存在")
    db.delete(record)
    db.commit()
    return {"deleted": True, "id": history_id}


def clear_history(db: Session, user: User) -> dict:
    """清空当前用户的浏览历史。"""
    from sqlalchemy import delete
    result = db.execute(
        delete(BrowseHistory).where(BrowseHistory.user_id == user.id)
    )
    db.commit()
    return {"cleared": True, "count": result.rowcount or 0}
