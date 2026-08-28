"""活动板块公开接口。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, current_user_optional
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import activity_service

router = APIRouter(prefix="/activities", tags=["activities"])


class ActivityJoinIn(BaseModel):
    action: str = Field(default="join", pattern="^(join|cancel)$")


@router.get("")
def list_activities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> dict:
    """活动列表（仅上架活动，登录用户附带 joined 状态）。"""
    return ok(activity_service.list_activities(db, page, page_size, user.id if user else None))


@router.get("/{activity_id}")
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> dict:
    """活动详情。"""
    return ok(activity_service.get_activity(db, activity_id, user.id if user else None))


@router.post("/{activity_id}/join")
def join_activity(
    activity_id: int,
    payload: ActivityJoinIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """报名 / 取消报名活动。"""
    if payload.action == "cancel":
        return ok(activity_service.cancel_activity(db, activity_id, user.id))
    return ok(activity_service.join_activity(db, activity_id, user.id))
