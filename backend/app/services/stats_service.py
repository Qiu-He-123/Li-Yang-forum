"""首页统计 + 漂流瓶/匹配在线统计服务。

提供：
- 首页透明展示数据：当前在线人数 / 今日发帖数 / 注册人数
- 漂流瓶透明展示：在线匹配人数 / 已投放瓶子总数 / 今日拾取次数
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bottle, BottlePick, Post, User
from app.services.connection_manager import manager


def home_stats(db: Session) -> dict:
    """首页统计：在线人数 + 今日发帖 + 注册人数。"""
    # 今日 0 点
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

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
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

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
