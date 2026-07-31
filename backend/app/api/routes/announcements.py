from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Announcement
from app.schemas.common import ok

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements(school_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> dict:
    """查询公告列表（T7-7：按校区过滤，school_id=None 表示全校公告）。

    返回该校区的公告 + 全校公告（school_id IS NULL）。
    """
    query = select(Announcement).where(Announcement.is_active.is_(True))
    if school_id is not None:
        # T7-7：只返回该校区公告 + 全校公告（school_id 为空）
        query = query.where(or_(Announcement.school_id == school_id, Announcement.school_id.is_(None)))
    items = db.scalars(query.order_by(desc(Announcement.created_at)).limit(5)).all()
    return ok([{"id": item.id, "title": item.title, "content": item.content} for item in items])

