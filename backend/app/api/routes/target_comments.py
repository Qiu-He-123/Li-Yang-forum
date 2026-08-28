"""通用留言板路由（组局/活动留言与回复）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import target_comment_service

router = APIRouter(prefix="/comments/{target_type}/{target_id}", tags=["comments"])


class TargetCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    parent_id: int | None = None


@router.get("")
def list_target_comments(
    target_type: str,
    target_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """留言列表（游客也可查看）。"""
    return ok(target_comment_service.list_comments(db, target_type, target_id, page, page_size))


@router.post("")
def create_target_comment(
    target_type: str,
    target_id: int,
    payload: TargetCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """发表留言 / 回复留言（需登录）。"""
    return ok(target_comment_service.create_comment(db, target_type, target_id, payload, user))


@router.delete("/{comment_id}")
def delete_target_comment(
    target_type: str,
    target_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """删除留言（仅作者本人，根留言级联删除回复）。"""
    return ok(target_comment_service.delete_comment(db, target_type, target_id, comment_id, user))
