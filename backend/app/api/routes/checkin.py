"""每日签到路由。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import checkin_service

router = APIRouter(prefix="/checkin", tags=["checkin"])


@router.post("/today")
def check_in_today(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """今日签到（幂等：重复签到返回已签到状态）。"""
    return ok(checkin_service.check_in_today(db, user))


@router.get("/status")
def get_checkin_status(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """获取签到状态：今日是否已签、连续天数、本月签到日期列表。"""
    return ok(checkin_service.get_status(db, user))


@router.get("/history")
def get_monthly_history(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取指定年月的签到记录。"""
    return ok(checkin_service.get_monthly_history(db, user, year, month))
