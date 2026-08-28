from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user_optional, extract_ip
from app.core.database import get_db
from app.models import Announcement, AnnouncementGuestView, User
from app.schemas.common import ok

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements(
    school_id: int | None = Query(default=None),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> dict:
    """查询公告列表（T7-7：按校区过滤，school_id=None 表示全校公告）。

    可见范围 scope：
    - all   ：所有人可见
    - user  ：仅登录用户可见
    - guest ：仅游客可见，且同一 IP 只投递一次（首次投递即记录，之后不再下发）
    """
    is_guest = user is None
    query = select(Announcement).where(Announcement.is_active.is_(True))
    if school_id is not None:
        # T7-7：只返回该校区公告 + 全校公告（school_id 为空）
        query = query.where(or_(Announcement.school_id == school_id, Announcement.school_id.is_(None)))
    rows = db.scalars(query.order_by(desc(Announcement.created_at)).limit(20)).all()

    items: list[dict] = []
    if is_guest:
        # 游客：all + guest 范围；guest 范围按 IP 去重（同 IP 发过一次就不再发）
        ip = extract_ip(request) or ""
        guest_ids = [a.id for a in rows if (a.scope or "all") == "guest"]
        viewed: set[int] = set()
        if ip and guest_ids:
            viewed = set(
                db.scalars(
                    select(AnnouncementGuestView.announcement_id).where(
                        AnnouncementGuestView.ip == ip,
                        AnnouncementGuestView.announcement_id.in_(guest_ids),
                    )
                ).all()
            )
        for a in rows:
            scope = a.scope or "all"
            if scope == "user":
                continue  # 游客看不到"仅登录用户"的公告
            if scope == "guest" and a.id in viewed:
                continue  # 该 IP 已投递过，不再下发
            items.append({"id": a.id, "title": a.title, "content": a.content, "scope": scope})
            if scope == "guest" and ip:
                db.add(AnnouncementGuestView(announcement_id=a.id, ip=ip))
        if ip and any(a.scope == "guest" for a in rows):
            db.commit()  # 记录本次游客投递
    else:
        # 登录用户：all + user 范围；guest 范围不展示（那是给游客的）
        for a in rows:
            scope = a.scope or "all"
            if scope == "guest":
                continue
            items.append({"id": a.id, "title": a.title, "content": a.content, "scope": scope})
    return ok(items[:5])
