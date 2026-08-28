"""话题路由（阶段二）。

提供话题搜索、详情、关注/取消关注、列出话题下的帖子。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.models import User
from app.schemas.common import ok
from app.services import topic_service

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("/search")
def search_topics(
    q: str = Query(default="", max_length=64),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """搜索话题（按 name 模糊匹配，公开访问）。"""
    return ok(topic_service.search_topics(db, q, limit=limit))


@router.get("/hot")
def hot_topics(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """获取热门话题（按 post_count 降序，公开访问）。"""
    return ok(topic_service.hot_topics(db, limit=limit))


@router.get("/{topic_id}")
def get_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """获取话题详情（含当前用户是否已关注，未登录 is_followed=False）。"""
    data = topic_service.get_topic_detail(db, topic_id, user=user)
    if data is None:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    return ok(data)


@router.get("/{topic_id}/posts")
def list_topic_posts(
    topic_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """列出话题下的帖子（分页，公开访问，遵循帖子可见性规则）。"""
    return ok(topic_service.list_topic_posts(db, topic_id, page, page_size, user=user))


@router.post("/{topic_id}/follow")
def follow_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """关注/取消关注话题（toggle，需登录）。

    Returns:
        is_followed: True 刚关注，False 刚取消
    """
    is_followed = topic_service.follow_topic(db, user, topic_id)
    return ok({"is_followed": is_followed})
