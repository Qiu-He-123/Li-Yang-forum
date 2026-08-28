"""组局业务逻辑层：列表、详情、发布、报名、退出、取消、我的组局。"""

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import now_utc, to_iso_zh
from app.models import Gathering, GatheringParticipant, User
from app.services.avatar import avatar_url_or_default

GATHERING_CATEGORIES = ["游戏组局", "现实组局", "运动健身", "吃饭拼单", "学习自习", "其他"]


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


def _parse_images(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(u) for u in data if isinstance(u, str)][:9]
    except (ValueError, TypeError):
        return []


def _host_dict(u: User | None) -> dict:
    if not u:
        return {"id": 0, "nickname": "已注销", "avatar": None}
    return {"id": u.id, "nickname": u.nickname, "avatar": avatar_url_or_default(u.avatar_url)}


def _gathering_dict(
    g: Gathering,
    host: User | None = None,
    joined: bool = False,
    is_host: bool = False,
) -> dict:
    return {
        "id": g.id,
        "title": g.title,
        "type": g.type,
        "category": g.category,
        "start_time": to_iso_zh(g.start_time) if g.start_time else None,
        "end_time": to_iso_zh(g.end_time) if g.end_time else None,
        "location": g.location,
        "max_people": g.max_people,
        "joined_people": g.joined_people,
        "description": g.description,
        "images": _parse_images(g.images),
        "status": g.status,
        "host": _host_dict(host),
        "is_joined": joined,
        "is_host": is_host,
        "created_at": to_iso_zh(g.created_at) if g.created_at else None,
    }


def _load_hosts(db: Session, host_ids: list[int]) -> dict[int, User]:
    if not host_ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(host_ids))).all()}


def _joined_ids(db: Session, user_id: int | None, gathering_ids: list[int]) -> set[int]:
    """当前用户已报名的组局 id 集合。"""
    if user_id is None or not gathering_ids:
        return set()
    return set(
        db.scalars(
            select(GatheringParticipant.gathering_id).where(
                GatheringParticipant.user_id == user_id,
                GatheringParticipant.gathering_id.in_(gathering_ids),
            )
        ).all()
    )


def list_gatherings(
    db: Session,
    category: str | None = None,
    type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    include_all_status: bool = False,
) -> dict:
    """组局列表（默认仅招募中，按开始时间升序：最快开始的在前）。"""
    query = select(Gathering)
    if not include_all_status:
        query = query.where(Gathering.status == "recruiting")
    if category:
        query = query.where(Gathering.category == category)
    if type:
        query = query.where(Gathering.type == type)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(Gathering.start_time.asc(), Gathering.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    hosts = _load_hosts(db, [g.host_id for g in rows])
    joined = _joined_ids(db, user_id, [g.id for g in rows])
    return {
        "items": [_gathering_dict(g, hosts.get(g.host_id), g.id in joined, g.host_id == user_id) for g in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def get_gathering(db: Session, gathering_id: int, user_id: int | None = None) -> dict:
    """组局详情（含成员列表）。"""
    g = db.get(Gathering, gathering_id)
    if not g:
        raise HTTPException(status_code=404, detail="组局不存在")
    host = db.get(User, g.host_id)
    joined = False
    members: list[dict] = []
    parts = db.scalars(
        select(GatheringParticipant)
        .where(GatheringParticipant.gathering_id == gathering_id)
        .order_by(GatheringParticipant.created_at.asc())
    ).all()
    if parts:
        users = {
            u.id: u
            for u in db.scalars(select(User).where(User.id.in_([p.user_id for p in parts]))).all()
        }
        for p in parts:
            u = users.get(p.user_id)
            if u:
                members.append({
                    "user_id": u.id,
                    "nickname": u.nickname,
                    "avatar": avatar_url_or_default(u.avatar_url),
                    "is_host": u.id == g.host_id,
                    "joined_at": to_iso_zh(p.created_at) if p.created_at else None,
                })
            if user_id is not None and p.user_id == user_id:
                joined = True
    result = _gathering_dict(g, host, joined, user_id is not None and g.host_id == user_id)
    result["members"] = members
    return result


def create_gathering(db: Session, payload: dict, user_id: int) -> dict:
    """发布组局：校验必填项，发起人自动报名占一个名额。"""
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="请输入组局标题")
    if len(title) > 100:
        raise HTTPException(status_code=400, detail="标题不能超过 100 字")

    start_time = _parse_dt(payload.get("start_time"))
    if not start_time:
        raise HTTPException(status_code=400, detail="请选择有效的开始时间")
    if start_time <= now_utc():
        raise HTTPException(status_code=400, detail="开始时间必须晚于当前时间")
    end_time = _parse_dt(payload.get("end_time"))
    if end_time and end_time <= start_time:
        raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")

    g_type = payload.get("type") or "online"
    if g_type not in ("online", "offline"):
        raise HTTPException(status_code=400, detail="组局类型无效")
    location = (payload.get("location") or "").strip() or None
    if g_type == "offline" and not location:
        raise HTTPException(status_code=400, detail="线下组局请填写活动地点")

    category = (payload.get("category") or "").strip() or "其他"
    try:
        max_people = int(payload.get("max_people") or 10)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="人数上限无效") from None
    if max_people < 2 or max_people > 100:
        raise HTTPException(status_code=400, detail="人数上限须在 2-100 之间")

    images = _parse_images(json.dumps(payload.get("images") or []))

    g = Gathering(
        title=title,
        type=g_type,
        category=category,
        start_time=start_time,
        end_time=end_time,
        location=location,
        max_people=max_people,
        joined_people=1,  # 发起人自动占用一个名额
        description=(payload.get("description") or "").strip() or None,
        images=json.dumps(images, ensure_ascii=False),
        status="recruiting",
        host_id=user_id,
    )
    db.add(g)
    db.flush()
    db.add(GatheringParticipant(gathering_id=g.id, user_id=user_id))
    db.commit()
    db.refresh(g)
    host = db.get(User, user_id)
    result = _gathering_dict(g, host, joined=True, is_host=True)
    result["members"] = [{
        "user_id": user_id,
        "nickname": host.nickname if host else "",
        "avatar": avatar_url_or_default(host.avatar_url) if host else None,
        "is_host": True,
        "joined_at": to_iso_zh(g.created_at) if g.created_at else None,
    }]
    return result


def join_gathering(db: Session, gathering_id: int, user_id: int) -> dict:
    """报名组局：防重复、人数上限、招募中校验。"""
    g = db.get(Gathering, gathering_id)
    if not g:
        raise HTTPException(status_code=404, detail="组局不存在")
    if g.status != "recruiting":
        raise HTTPException(status_code=400, detail="该组局已停止报名")
    if g.start_time <= now_utc():
        raise HTTPException(status_code=400, detail="组局已开始，无法报名")
    if g.host_id == user_id:
        raise HTTPException(status_code=400, detail="你是组局发起人，无需报名")
    exists = db.scalar(
        select(GatheringParticipant).where(
            GatheringParticipant.gathering_id == gathering_id,
            GatheringParticipant.user_id == user_id,
        )
    )
    if exists:
        raise HTTPException(status_code=400, detail="你已报名该组局")
    if g.joined_people >= g.max_people:
        raise HTTPException(status_code=400, detail="组局人数已满")

    db.add(GatheringParticipant(gathering_id=gathering_id, user_id=user_id))
    g.joined_people += 1
    db.commit()
    db.refresh(g)
    return get_gathering(db, gathering_id, user_id)


def leave_gathering(db: Session, gathering_id: int, user_id: int) -> dict:
    """退出组局（发起人不能退出，只能取消组局）。"""
    g = db.get(Gathering, gathering_id)
    if not g:
        raise HTTPException(status_code=404, detail="组局不存在")
    if g.host_id == user_id:
        raise HTTPException(status_code=400, detail="发起人不能退出，可选择取消组局")
    row = db.scalar(
        select(GatheringParticipant).where(
            GatheringParticipant.gathering_id == gathering_id,
            GatheringParticipant.user_id == user_id,
        )
    )
    if not row:
        raise HTTPException(status_code=400, detail="你尚未报名该组局")
    db.delete(row)
    g.joined_people = max(0, g.joined_people - 1)
    db.commit()
    db.refresh(g)
    return get_gathering(db, gathering_id, user_id)


def cancel_gathering(db: Session, gathering_id: int, user_id: int) -> dict:
    """取消组局（仅发起人）。"""
    g = db.get(Gathering, gathering_id)
    if not g:
        raise HTTPException(status_code=404, detail="组局不存在")
    if g.host_id != user_id:
        raise HTTPException(status_code=403, detail="只有发起人可以取消组局")
    if g.status == "cancelled":
        raise HTTPException(status_code=400, detail="组局已取消")
    g.status = "cancelled"
    db.commit()
    db.refresh(g)
    return get_gathering(db, gathering_id, user_id)


def my_gatherings(db: Session, user_id: int) -> dict:
    """我的组局：我发起的 + 我报名的。"""
    hosting_rows = db.scalars(
        select(Gathering)
        .where(Gathering.host_id == user_id)
        .order_by(Gathering.start_time.desc())
    ).all()
    joined_rows = db.scalars(
        select(Gathering)
        .join(GatheringParticipant, GatheringParticipant.gathering_id == Gathering.id)
        .where(GatheringParticipant.user_id == user_id, Gathering.host_id != user_id)
        .order_by(Gathering.start_time.desc())
    ).all()
    host = db.get(User, user_id)
    return {
        "hosting": [_gathering_dict(g, host, True, True) for g in hosting_rows],
        "joined": [_gathering_dict(g, host, True, False) for g in joined_rows],
    }


def categories() -> list[str]:
    """组局分类（前端发布页/大厅筛选一致）。"""
    return GATHERING_CATEGORIES
