"""徽章（勋章）系统用户接口。

- GET /badges           徽章目录（含 is_owned / is_wearing）
- GET /badges/mine      我的徽章（已拥有 + 当前佩戴 + 目录）
- POST /badges/claim    使用激活码领取徽章（消息 → 系统入口）
- POST /badges/wear     佩戴徽章（{badge_id}）
- DELETE /badges/wear   卸下当前佩戴的徽章
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import badge_service

router = APIRouter(prefix="/badges", tags=["badges"])


class ClaimBadgeIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class WearBadgeIn(BaseModel):
    badge_id: int


@router.get("")
def list_badges(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """徽章目录。"""
    return ok(badge_service.list_badges(db, user))


@router.get("/mine")
def my_badges(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我的徽章：已拥有 + 当前佩戴 + 全部目录。"""
    return ok(badge_service.my_badges(db, user))


@router.post("/claim")
def claim_badge(
    payload: ClaimBadgeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """使用激活码领取徽章。"""
    return ok(badge_service.claim_badge_by_code(db, user, payload.code, request))


@router.post("/wear")
def wear_badge(
    payload: WearBadgeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """佩戴徽章。"""
    return ok(badge_service.wear_badge(db, user, payload.badge_id, request))


@router.delete("/wear")
def unwear_badge(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """卸下当前佩戴的徽章。"""
    return ok(badge_service.unwear_badge(db, user, request))
