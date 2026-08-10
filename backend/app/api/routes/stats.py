"""首页统计 / 漂流瓶统计 / 公告已读 API。

- GET /stats/home：首页在线人数 + 今日发帖 + 注册人数（匿名可访问）
- GET /stats/bottle：漂流瓶页统计（在线人数 + 匹配中人数 + 投放数 + 今日拾取数，匿名可访问）
- GET /announcements/unread：登录后获取未读公告列表（用于弹窗）
- POST /announcements/{id}/read：标记公告已读（点击"我知道了"按钮）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import Announcement, AnnouncementRead, User
from app.core.time_utils import to_iso_zh
from app.schemas.common import ok
from app.services import stats_service

router = APIRouter(tags=["stats"])


@router.get("/stats/home")
def home_stats(db: Session = Depends(get_db)) -> dict:
    """首页统计：在线人数 + 今日发帖 + 注册人数。匿名可访问。"""
    return ok(stats_service.home_stats(db))


@router.get("/stats/bottle")
def bottle_stats(db: Session = Depends(get_db)) -> dict:
    """漂流瓶页统计：在线人数 + 匹配中人数 + 投放数 + 今日拾取数。匿名可访问。"""
    return ok(stats_service.bottle_stats(db))


# ============ 公告已读 ============

def _announcement_dict(item: Announcement, is_read: bool = False) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "content": item.content,
        "school_id": item.school_id,
        "is_active": item.is_active,
        "is_read": is_read,
        "created_at": to_iso_zh(item.created_at),
    }


@router.get("/announcements/unread")
def list_unread_announcements(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """登录后获取当前用户未读的活跃公告（用于登录后弹窗）。

    返回该用户所属校区的公告 + 全校公告，且尚未在 announcement_reads 中记录的。
    按 created_at desc 排序，最多 5 条。
    """
    query = select(Announcement).where(Announcement.is_active.is_(True))
    # 校区过滤：用户校区公告 + 全校公告（school_id IS NULL）
    query = query.where(or_(Announcement.school_id == user.school_id, Announcement.school_id.is_(None)))
    items = db.scalars(query.order_by(desc(Announcement.created_at)).limit(20)).all()
    if not items:
        return ok([])
    # 已读 id 集合
    read_ids = set(
        db.scalars(
            select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
        ).all()
    )
    unread = [item for item in items if item.id not in read_ids]
    return ok([_announcement_dict(item, is_read=False) for item in unread])


@router.get("/announcements/mine")
def list_my_announcements(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我的-公告页：列出该用户可见的所有公告（带 is_read 状态）。"""
    query = select(Announcement).where(Announcement.is_active.is_(True))
    query = query.where(or_(Announcement.school_id == user.school_id, Announcement.school_id.is_(None)))
    items = db.scalars(query.order_by(desc(Announcement.created_at)).limit(50)).all()
    read_ids = set(
        db.scalars(
            select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
        ).all()
    )
    return ok([_announcement_dict(item, is_read=(item.id in read_ids)) for item in items])


@router.post("/announcements/{announcement_id}/read")
def mark_announcement_read(
    announcement_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """标记公告为已读（点击"我知道了"按钮）。

    幂等：已存在记录则不重复插入。
    """
    ann = db.get(Announcement, announcement_id)
    if not ann or not ann.is_active:
        return ok({"ok": True})
    existing = db.scalar(
        select(AnnouncementRead).where(
            AnnouncementRead.user_id == user.id,
            AnnouncementRead.announcement_id == announcement_id,
        )
    )
    if not existing:
        db.add(AnnouncementRead(user_id=user.id, announcement_id=announcement_id))
        db.commit()
    return ok({"ok": True})
