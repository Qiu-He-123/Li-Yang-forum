from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/history")
def list_search_history(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """当前用户搜索历史（最近 20 条，去重）。"""
    return ok(search_service.list_search_history(user, db, limit=20))


@router.delete("/history")
def clear_search_history(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """清空当前用户搜索历史。"""
    deleted = search_service.clear_search_history(user, db)
    return ok({"deleted": deleted})


@router.delete("/history/{keyword}")
def delete_search_history_by_keyword(keyword: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """删除单条搜索历史（按 keyword 匹配删除所有相同 keyword 的记录）。"""
    deleted = search_service.delete_search_history_by_keyword(user, keyword, db)
    return ok({"deleted": deleted})


@router.get("/hot")
def list_hot_searches(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """热搜榜（前 10，按 count 降序；不足用预设热门词兜底）。"""
    return ok(search_service.list_hot_searches(db, limit=10))
