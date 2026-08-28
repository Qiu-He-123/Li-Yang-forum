"""活动板块服务：活动列表 / 详情 / 报名 / 取消报名 / 管理端增删改查。"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Activity, ActivityParticipant, User


def _activity_to_dict(a: Activity, joined: bool = False) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "location": a.location,
        "cover_url": a.cover_url,
        "start_at": a.start_at.isoformat() if a.start_at else None,
        "end_at": a.end_at.isoformat() if a.end_at else None,
        "organizer": a.organizer,
        "contact": a.contact,
        "max_participants": a.max_participants,
        "participant_count": a.participant_count,
        "is_active": a.is_active,
        "joined": joined,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _get_activity(db: Session, activity_id: int) -> Activity:
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(status_code=404, detail="活动不存在")
    return a


def _joined_ids(db: Session, user_id: int | None, activity_ids: list[int]) -> set[int]:
    if not user_id or not activity_ids:
        return set()
    rows = db.scalars(
        select(ActivityParticipant.activity_id).where(
            ActivityParticipant.user_id == user_id,
            ActivityParticipant.activity_id.in_(activity_ids),
        )
    ).all()
    return set(rows)


def list_activities(db: Session, page: int, page_size: int, user_id: int | None) -> dict:
    """活动列表（仅上架活动，登录用户附带 joined 状态）。"""
    total = db.scalar(select(func.count(Activity.id)).where(Activity.is_active.is_(True))) or 0
    rows = db.scalars(
        select(Activity)
        .where(Activity.is_active.is_(True))
        .order_by(Activity.start_at.desc().nulls_last(), Activity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    joined = _joined_ids(db, user_id, [a.id for a in rows])
    return {
        "items": [_activity_to_dict(a, a.id in joined) for a in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_activity(db: Session, activity_id: int, user_id: int | None) -> dict:
    a = _get_activity(db, activity_id)
    joined = user_id is not None and bool(
        db.scalar(
            select(ActivityParticipant.id).where(
                ActivityParticipant.activity_id == activity_id,
                ActivityParticipant.user_id == user_id,
            )
        )
    )
    return _activity_to_dict(a, joined)


def join_activity(db: Session, activity_id: int, user_id: int) -> dict:
    """报名活动：新增报名记录，报名人数 +1。"""
    a = _get_activity(db, activity_id)
    if not a.is_active:
        raise HTTPException(status_code=400, detail="活动已结束，无法报名")
    if a.max_participants is not None and a.participant_count >= a.max_participants:
        raise HTTPException(status_code=400, detail="活动人数已满")
    exists = db.scalar(
        select(ActivityParticipant.id).where(
            ActivityParticipant.activity_id == activity_id,
            ActivityParticipant.user_id == user_id,
        )
    )
    if not exists:
        db.add(ActivityParticipant(activity_id=activity_id, user_id=user_id))
        a.participant_count = (a.participant_count or 0) + 1
        db.flush()
    return _activity_to_dict(a, True)


def cancel_activity(db: Session, activity_id: int, user_id: int) -> dict:
    """取消报名：删除报名记录，报名人数 -1。"""
    a = _get_activity(db, activity_id)
    row = db.scalar(
        select(ActivityParticipant).where(
            ActivityParticipant.activity_id == activity_id,
            ActivityParticipant.user_id == user_id,
        )
    )
    if row:
        db.delete(row)
        a.participant_count = max(0, (a.participant_count or 1) - 1)
        db.flush()
    return _activity_to_dict(a, False)


# ============ 管理端 ============


def admin_list_activities(db: Session, page: int, page_size: int, keyword: str | None) -> dict:
    """活动列表（管理端，含停用，支持标题/地点关键词搜索）。"""
    cond = []
    if keyword:
        kw = f"%{keyword.strip()}%"
        cond.append((Activity.title.like(kw)) | (Activity.location.like(kw)))
    total = db.scalar(select(func.count(Activity.id)).where(*cond)) or 0
    rows = db.scalars(
        select(Activity)
        .where(*cond)
        .order_by(Activity.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_activity_to_dict(a) for a in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def admin_create_activity(db: Session, data: dict, admin_id: int) -> dict:
    a = Activity(
        title=data.get("title", ""),
        description=data.get("description", ""),
        location=data.get("location"),
        cover_url=data.get("cover_url"),
        start_at=_parse_dt(data.get("start_at")),
        end_at=_parse_dt(data.get("end_at")),
        organizer=data.get("organizer"),
        contact=data.get("contact"),
        max_participants=data.get("max_participants"),
        participant_count=0,
        is_active=bool(data.get("is_active", True)),
        created_by=admin_id,
    )
    db.add(a)
    db.flush()
    return _activity_to_dict(a)


def admin_update_activity(db: Session, activity_id: int, payload: dict) -> dict:
    a = _get_activity(db, activity_id)
    for key in (
        "title",
        "description",
        "location",
        "cover_url",
        "organizer",
        "contact",
        "max_participants",
        "is_active",
    ):
        if key in payload and payload[key] is not None:
            setattr(a, key, payload[key])
    for key in ("start_at", "end_at"):
        if key in payload:
            setattr(a, key, _parse_dt(payload.get(key)))
    db.flush()
    return _activity_to_dict(a)


def admin_delete_activity(db: Session, activity_id: int) -> None:
    a = _get_activity(db, activity_id)
    db.query(ActivityParticipant).filter(ActivityParticipant.activity_id == activity_id).delete(
        synchronize_session=False
    )
    db.delete(a)
    db.flush()


def admin_activity_participants(db: Session, activity_id: int, page: int, page_size: int) -> dict:
    """活动报名名单（含报名用户昵称/头像）。"""
    _get_activity(db, activity_id)
    base = (
        select(ActivityParticipant, User)
        .join(User, User.id == ActivityParticipant.user_id)
        .where(ActivityParticipant.activity_id == activity_id)
    )
    total = db.scalar(
        select(func.count(ActivityParticipant.id)).where(ActivityParticipant.activity_id == activity_id)
    ) or 0
    rows = db.execute(
        base.order_by(ActivityParticipant.created_at.desc(), ActivityParticipant.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "user_id": p.user_id,
            "nickname": u.nickname,
            "avatar_url": u.avatar_url,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p, u in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
