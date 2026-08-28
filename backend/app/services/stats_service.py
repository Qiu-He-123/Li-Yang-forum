"""首页统计 + 漂流瓶/匹配在线统计服务。

提供：
- 首页透明展示数据：当前在线人数 / 今日发帖数 / 注册人数
- 漂流瓶透明展示：在线匹配人数 / 已投放瓶子总数 / 今日拾取次数
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.time_utils import beijing_today_start, to_iso_zh
from app.models import Bottle, BottlePick, Post, User
from app.services.badge_service import badge_dict
from app.services.connection_manager import manager


def home_stats(db: Session) -> dict:
    """首页统计：在线人数 + 今日发帖 + 注册人数。"""
    # 今日 0 点
    today = beijing_today_start()

    online_count = manager.online_count()
    logged_in = manager.logged_in_count()
    visitors = manager.visitor_count()

    today_post_count = db.scalar(
        select(func.count())
        .select_from(Post)
        .where(
            Post.is_draft.is_(False),
            Post.ai_status == "approved",
            Post.created_at >= today,
        )
    ) or 0

    total_users = db.scalar(select(func.count()).select_from(User)) or 0

    return {
        "online_count": online_count,
        "logged_in_count": logged_in,
        "visitor_count": visitors,
        "today_post_count": today_post_count,
        "total_users": total_users,
    }


def bottle_stats(db: Session) -> dict:
    """漂流瓶页面透明展示数据。

    - online_count: 当前在线人数（来自 ConnectionManager）
    - matching_count: 当前正在匹配队列中的用户数
    - total_bottles: 累计投放瓶子数（active + picked）
    - today_picks: 今日拾取次数
    """
    today = beijing_today_start()

    online_count = manager.online_count()

    # 匹配中用户数：status=waiting 的 match_queue 记录
    from app.models import MatchQueue
    matching_count = db.scalar(
        select(func.count()).select_from(MatchQueue).where(MatchQueue.status == "waiting")
    ) or 0

    total_bottles = db.scalar(
        select(func.count()).select_from(Bottle).where(Bottle.status.in_(["active", "picked"]))
    ) or 0

    today_picks = db.scalar(
        select(func.count()).select_from(BottlePick).where(BottlePick.created_at >= today)
    ) or 0

    return {
        "online_count": online_count,
        "matching_count": matching_count,
        "total_bottles": total_bottles,
        "today_picks": today_picks,
    }


def online_users_page(
    db: Session, page: int = 1, page_size: int = 20, q: str | None = None
) -> dict:
    """在线登录用户列表（分页，按上线时间倒序）。"""
    details = manager.online_users_detail()
    details.sort(key=lambda x: x[1], reverse=True)
    users = {
        u.id: u
        for u in db.scalars(
            select(User)
            .options(selectinload(User.school))
            .where(User.id.in_([uid for uid, _ in details]))
        ).all()
    }
    # 昵称搜索（在线人数少，先全量过滤再分页）
    keyword = (q or "").strip().lower()
    pairs = [
        (uid, ts)
        for uid, ts in details
        if uid in users
        and (not keyword or keyword in (users[uid].nickname or "").lower())
    ]
    total = len(pairs)
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    chunk = pairs[(page - 1) * page_size : page * page_size]
    items = []
    for uid, ts in chunk:
        u = users.get(uid)
        if not u:
            continue
        items.append(
            {
                "id": u.id,
                "nickname": u.nickname,
                "avatar_url": u.avatar_url,
                "badge": badge_dict(u.wearing_badge),
                "school": u.school.name if u.school else None,
                "connected_at": _iso_from_ts(ts),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def online_guests_page(db: Session, page: int = 1, page_size: int = 20) -> dict:
    """在线游客列表（分页）：游客无账号，仅展示匿名会话。"""
    details = manager.online_guests_detail()
    details.sort(key=lambda x: x[1], reverse=True)
    total = len(details)
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    chunk = details[(page - 1) * page_size : page * page_size]
    items = [
        {
            "id": cid,
            "nickname": "游客",
            "avatar_url": None,
            "badge": None,
            "school": None,
            "connected_at": _iso_from_ts(ts),
        }
        for cid, ts in chunk
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _iso_from_ts(ts: float) -> str | None:
    if not ts:
        return None
    return to_iso_zh(datetime.fromtimestamp(ts, tz=timezone.utc))
