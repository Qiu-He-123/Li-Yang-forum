"""实时匹配 API 路由。

- POST /match/queue：加入匹配队列
- POST /match/cancel：取消等待中的匹配
- GET  /match/active-session：查询当前活动会话（如有）
- GET  /match/sessions/{id}/messages：查询会话历史消息
- GET  /match/history：查询历史匹配会话列表
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import match_service

router = APIRouter(prefix="/match", tags=["match"])


class MatchEnqueuePayload(BaseModel):
    grades: list[str] = Field(default_factory=list)
    school_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)               # 尽量有（软排序）
    tag_required: list[str] = Field(default_factory=list)       # 必须有（硬过滤）
    target_gender: str = Field(default="any", pattern="^(male|female|any)$")
    # 年龄系统：期望对方年龄范围（None 表示不限）
    age_min: int | None = Field(default=None, ge=13, le=18)
    age_max: int | None = Field(default=None, ge=13, le=18)


@router.post("/queue")
def enqueue_match(
    payload: MatchEnqueuePayload,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """加入匹配队列：需要 verified 状态（已填邀请码）。"""
    return ok(match_service.enqueue_match(
        db,
        user,
        grades=payload.grades,
        school_ids=payload.school_ids,
        tags=payload.tags,
        tag_required=payload.tag_required,
        target_gender=payload.target_gender,
        age_min=payload.age_min,
        age_max=payload.age_max,
    ))


@router.post("/cancel")
def cancel_match(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """取消等待中的匹配。"""
    return ok(match_service.cancel_match(db, user))


@router.get("/active-session")
def get_active_session(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查询当前活动会话（如有）。"""
    return ok(match_service.get_active_session(db, user))


@router.get("/sessions/{session_id}/messages")
def list_session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查询会话历史消息。"""
    return ok(match_service.list_session_messages(db, session_id, user))


@router.get("/history")
def match_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查询历史匹配会话列表。"""
    return ok(match_service.list_my_match_history(db, user, page, page_size))
