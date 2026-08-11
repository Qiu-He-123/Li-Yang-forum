"""公开配置接口：首页等无需登录即可读取的轻量设置。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.common import ok
from app.services import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/public")
def public_settings(db: Session = Depends(get_db)) -> dict:
    """首页等公开页面读取的配置（当前：首页滚动字幕内容）。"""
    raw = settings_service.get_setting(db, "home_marquee")
    items = [line.strip() for line in raw.replace("\r", "").splitlines() if line.strip()]
    return ok({
        "marquee_text": raw,
        "marquee_items": items,
    })
