"""组局（线上/线下）用户侧路由：列表、详情、发布、报名、退出、取消、我的组局。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import gathering_service

router = APIRouter(prefix="/gatherings", tags=["gatherings"])


class GatheringCreateIn(BaseModel):
    title: str
    type: str = Field(default="online", pattern="^(online|offline)$")
    category: str = ""
    start_time: str
    end_time: str | None = None
    location: str | None = None
    max_people: int = Field(default=10, ge=2, le=100)
    description: str = ""
    images: list[str] = []


@router.get("")
def gathering_list(
    category: str | None = Query(None, description="分类筛选"),
    type: str | None = Query(None, description="online/offline", pattern="^(online|offline)$"),
    all_status: bool = Query(False, description="返回全部状态（含已结束/已取消/已过期）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """组局列表（默认仅招募中且未过截止时间，按开始时间升序）。"""
    return ok(
        gathering_service.list_gatherings(
            db, category, type, page, page_size, user.id if user else None,
            include_all_status=all_status,
        )
    )


@router.get("/categories")
def gathering_categories() -> dict:
    """组局分类列表。"""
    return ok(gathering_service.categories())


@router.get("/mine")
def my_gatherings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我的组局（我发起的 + 我报名的）。"""
    return ok(gathering_service.my_gatherings(db, user.id))


@router.get("/{gathering_id}")
def gathering_detail(
    gathering_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """组局详情（含成员列表、报名状态）。"""
    return ok(gathering_service.get_gathering(db, gathering_id, user.id if user else None))


@router.post("")
def create_gathering(
    payload: GatheringCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """发布组局（发起人自动占用一个名额）。"""
    return ok(gathering_service.create_gathering(db, payload.model_dump(), user.id))


@router.post("/{gathering_id}/join")
def join_gathering(
    gathering_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """报名参加组局。"""
    return ok(gathering_service.join_gathering(db, gathering_id, user.id))


@router.post("/{gathering_id}/leave")
def leave_gathering(
    gathering_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """退出组局。"""
    return ok(gathering_service.leave_gathering(db, gathering_id, user.id))


@router.post("/{gathering_id}/cancel")
def cancel_gathering(
    gathering_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """取消组局（仅发起人）。"""
    return ok(gathering_service.cancel_gathering(db, gathering_id, user.id))
