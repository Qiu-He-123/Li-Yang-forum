"""用户浏览历史路由。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import browse_history_service

router = APIRouter(prefix="/history", tags=["browse-history"])


@router.get("")
def list_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取浏览历史列表（分页，按浏览时间倒序）。"""
    return ok(browse_history_service.list_history(db, user, page, page_size))


@router.delete("/{history_id}")
def delete_one(
    history_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """删除单条浏览记录。"""
    return ok(browse_history_service.delete_one(db, user, history_id))


@router.delete("")
def clear_history(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """清空浏览历史。"""
    return ok(browse_history_service.clear_history(db, user))
