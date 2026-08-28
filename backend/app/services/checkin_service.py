"""每日签到业务逻辑层。

- check_in_today: 今日签到（幂等，重复签到返回已签到状态）
- get_status: 获取签到状态（今日是否已签、连续天数、本月签到记录）
- 连续签到奖励：第 1 天 1 分，连续每天 +1，最多 7 分；中断后重置
"""
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time_utils import beijing_wall_midnight
from app.models import CheckIn, User


def _today_start() -> datetime:
    """返回今天 0 点的 datetime。"""
    return beijing_wall_midnight()


def _calc_reward(consecutive_days: int) -> int:
    """根据连续天数计算奖励积分：1,2,3,4,5,6,7（封顶 7）。"""
    return min(7, max(1, consecutive_days))


def check_in_today(db: Session, user: User) -> dict:
    """今日签到。

    幂等：如果今天已签到，返回已有记录（不重复扣分/奖励）。
    连续签到逻辑：如果昨天有签到记录，consecutive_days = 昨天 + 1；否则重置为 1。
    """
    today = _today_start()
    # 检查今日是否已签到
    existing = db.scalar(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.check_in_date == today,
        )
    )
    if existing:
        return {
            "id": existing.id,
            "check_in_date": existing.check_in_date.isoformat(),
            "consecutive_days": existing.consecutive_days,
            "reward_points": existing.reward_points,
            "already_checked_in": True,
            "message": "今日已签到",
        }

    # 查昨天是否签到，决定连续天数
    yesterday = today - timedelta(days=1)
    yesterday_record = db.scalar(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.check_in_date == yesterday,
        )
    )
    consecutive = (yesterday_record.consecutive_days + 1) if yesterday_record else 1
    reward = _calc_reward(consecutive)

    record = CheckIn(
        user_id=user.id,
        check_in_date=today,
        consecutive_days=consecutive,
        reward_points=reward,
    )
    db.add(record)
    # 累加用户积分（如果 User 有 points 字段则更新，否则忽略）
    try:
        if hasattr(user, "points") and user.points is not None:
            user.points = (user.points or 0) + reward
    except Exception:
        pass
    # 签到成功减少警告值（积极行为奖励）
    try:
        from app.services import warning_service
        warning_service.reduce_on_checkin(db, user)
    except Exception:
        pass
    db.commit()
    db.refresh(record)
    # 徽章自动发放：连续签到天数达到规则阈值自动发徽章
    try:
        from app.services.badge_service import auto_grant_by_action
        auto_grant_by_action(db, user, "checkin_consecutive", record.consecutive_days)
    except Exception:
        pass

    return {
        "id": record.id,
        "check_in_date": record.check_in_date.isoformat(),
        "consecutive_days": record.consecutive_days,
        "reward_points": record.reward_points,
        "already_checked_in": False,
        "message": f"签到成功，连续签到 {consecutive} 天，获得 {reward} 积分",
    }


def get_status(db: Session, user: User) -> dict:
    """获取签到状态：今日是否已签、连续天数、本月签到日期列表。"""
    today = _today_start()
    today_record = db.scalar(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.check_in_date == today,
        )
    )

    # 获取本月签到记录
    month_start = today.replace(day=1)
    next_month = (month_start.replace(year=month_start.year + 1, month=1) if month_start.month == 12
                  else month_start.replace(month=month_start.month + 1))
    month_records = db.scalars(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.check_in_date >= month_start,
            CheckIn.check_in_date < next_month,
        ).order_by(CheckIn.check_in_date.asc())
    ).all()

    return {
        "checked_in_today": today_record is not None,
        "today_consecutive_days": today_record.consecutive_days if today_record else 0,
        "today_reward_points": today_record.reward_points if today_record else 0,
        "month_days": [
            {
                "date": r.check_in_date.isoformat(),
                "consecutive_days": r.consecutive_days,
                "reward_points": r.reward_points,
            }
            for r in month_records
        ],
        "month_checked_days": [r.check_in_date.day for r in month_records],
        "total_month_count": len(month_records),
    }


def get_monthly_history(db: Session, user: User, year: int, month: int) -> dict:
    """获取指定年月的签到记录。"""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="月份必须在 1-12 之间")
    if not (2000 <= year <= 2100):
        raise HTTPException(status_code=400, detail="年份不合法")

    month_start = datetime(year, month, 1)
    next_month = (datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1))
    records = db.scalars(
        select(CheckIn).where(
            CheckIn.user_id == user.id,
            CheckIn.check_in_date >= month_start,
            CheckIn.check_in_date < next_month,
        ).order_by(CheckIn.check_in_date.asc())
    ).all()

    return {
        "year": year,
        "month": month,
        "days": [
            {
                "date": r.check_in_date.isoformat(),
                "day": r.check_in_date.day,
                "consecutive_days": r.consecutive_days,
                "reward_points": r.reward_points,
            }
            for r in records
        ],
        "total_count": len(records),
    }
