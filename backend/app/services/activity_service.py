"""活动板块业务逻辑层。"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
from app.models import Activity, ActivityParticipant, User


def _activity_dict(a: Activity, joined: bool = False) -> dict:
    """活动序列化（joined: 当前用户是否已报名）。"""
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "location": a.location,
        "cover_url": a.cover_url,
        "start_at": to_iso_zh(a.start_at) if a.start_at else None,
        "end_at": to_iso_zh(a.end_at) if a.end_at else None,
        "organizer": a.organizer,
        "contact": a.contact,
        "max_participants": a.max_participants,
        "participant_count": a.participant_count,
        "is_active": a.is_active,
        "joined": joined,
        "created_at": to_iso_zh(a.created_at) if a.created_at else None,
    }


def list_activities(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    only_active: bool = True,
) -> dict:
    """活动列表（按开始时间倒序，可分页）。"""
    query = select(Activity)
    if only_active:
        query = query.where(Activity.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(Activity.start_at.desc().nulls_last(), Activity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    joined_ids = set()
    if user_id is not None and rows:
        joined_ids = set(
            db.scalars(
                select(ActivityParticipant.activity_id).where(
                    ActivityParticipant.user_id == user_id,
                    ActivityParticipant.activity_id.in_([a.id for a in rows]),
                )
            ).all()
        )
    return {
        "items": [_activity_dict(a, a.id in joined_ids) for a in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def get_activity(db: Session, activity_id: int, user_id: int | None = None, is_admin: bool = False) -> dict:
    """活动详情（未上架/停用活动仅管理员可见，普通用户 404）。"""
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    if not a.is_active and not is_admin:
        raise HTTPException(status_code=404, detail="活动不存在")
    joined = False
    if user_id is not None:
        joined = (
            db.scalar(
                select(func.count(ActivityParticipant.id)).where(
                    ActivityParticipant.activity_id == activity_id,
                    ActivityParticipant.user_id == user_id,
                )
            )
            or 0
        ) > 0
    return _activity_dict(a, joined)


def join_activity(db: Session, activity_id: int, user_id: int) -> dict:
    """报名活动：防重复、人数上限校验。"""
    a = db.get(Activity, activity_id)
    if not a or not a.is_active:
        raise HTTPException(status_code=404, detail="活动不存在或已下线")
    exists = (
        db.scalar(
            select(func.count(ActivityParticipant.id)).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user_id,
            )
        )
        or 0
    )
    if exists:
        raise HTTPException(status_code=400, detail="你已报名该活动")
    if a.max_participants is not None and a.participant_count >= a.max_participants:
        raise HTTPException(status_code=400, detail="活动名额已满")
    db.add(ActivityParticipant(activity_id=activity_id, user_id=user_id))
    a.participant_count += 1
    db.commit()
    db.refresh(a)
    return _activity_dict(a, joined=True)


def cancel_activity(db: Session, activity_id: int, user_id: int) -> dict:
    """取消报名。"""
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    row = db.scalar(
        select(ActivityParticipant).where(
            ActivityParticipant.activity_id == activity_id,
            ActivityParticipant.user_id == user_id,
        )
    )
    if not row:
        raise HTTPException(status_code=400, detail="你尚未报名该活动")
    db.delete(row)
    a.participant_count = max(0, a.participant_count - 1)
    db.commit()
    db.refresh(a)
    return _activity_dict(a, joined=False)


# ============ 管理端 ============

def admin_list_activities(db: Session, page: int = 1, page_size: int = 20, keyword: str | None = None) -> dict:
    """管理端活动列表（含停用活动）。"""
    query = select(Activity)
    if keyword:
        query = query.where(Activity.title.contains(keyword))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(Activity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_activity_dict(a) for a in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _parse_dt(value) -> datetime | None:
    """把 ISO 字符串或 datetime 统一成 naive datetime（UTC）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def admin_create_activity(db: Session, payload: dict, admin_id: int) -> dict:
    """创建活动。"""
    a = Activity(
        title=payload.get("title", "").strip(),
        description=(payload.get("description") or "").strip(),
        location=(payload.get("location") or "").strip() or None,
        cover_url=(payload.get("cover_url") or "").strip() or None,
        start_at=_parse_dt(payload.get("start_at")),
        end_at=_parse_dt(payload.get("end_at")),
        organizer=(payload.get("organizer") or "").strip() or None,
        contact=(payload.get("contact") or "").strip() or None,
        max_participants=payload.get("max_participants"),
        is_active=bool(payload.get("is_active", True)),
        created_by=admin_id,
    )
    if not a.title:
        raise HTTPException(status_code=400, detail="请填写活动标题")
    if not a.description:
        raise HTTPException(status_code=400, detail="请填写活动内容")
    db.add(a)
    db.commit()
    db.refresh(a)
    return _activity_dict(a)


def admin_update_activity(db: Session, activity_id: int, payload: dict) -> dict:
    """更新活动。"""
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    for key in ("title", "description", "location", "cover_url", "start_at", "end_at",
                "organizer", "contact", "max_participants", "is_active"):
        if key in payload and payload[key] is not None:
            value = payload[key]
            if key in ("start_at", "end_at"):
                value = _parse_dt(value)
            setattr(a, key, value)
    if payload.get("title") == "":
        raise HTTPException(status_code=400, detail="活动标题不能为空")
    db.commit()
    db.refresh(a)
    return _activity_dict(a)


def admin_delete_activity(db: Session, activity_id: int) -> None:
    """删除活动（连带报名记录）。"""
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    db.execute(
        ActivityParticipant.__table__.delete().where(
            ActivityParticipant.activity_id == activity_id
        )
    )
    db.delete(a)
    db.commit()


def admin_activity_participants(db: Session, activity_id: int, page: int = 1, page_size: int = 20) -> dict:
    """查看活动报名名单。"""
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    query = select(ActivityParticipant).where(ActivityParticipant.activity_id == activity_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(query.order_by(ActivityParticipant.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    from app.services.avatar import avatar_url_or_default

    users = {u.id: u for u in db.scalars(
        select(User).where(User.id.in_([r.user_id for r in rows]))
    ).all()}
    items = []
    for r in rows:
        u = users.get(r.user_id)
        items.append({
            "user_id": r.user_id,
            "nickname": u.nickname if u else "已注销",
            "avatar_url": avatar_url_or_default(u.avatar_url) if u else None,
            "created_at": to_iso_zh(r.created_at) if r.created_at else None,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}
