"""每日任务中心（赚金币）。

每个任务 = 一个可今天的动作，达到目标后可领取一次金币奖励（每日限领一次）。
任务进度直接按今日行为计数（查现有表），领取通过 coin_service.grant_daily_task 防重复。

支持的任务（key）：
- checkin   每日签到       目标 1
- post      发布动态       目标 1
- comment   发布评论       目标 2
- like      收获赞         目标 3
- guess     完成今日竞猜   目标 1
"""
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import beijing_today_start, beijing_wall_midnight
from app.models import (
    CheckIn,
    CoinTransaction,
    Comment,
    GuessBet,
    Like,
    Post,
    User,
)
from app.services import coin_service


# 任务定义：key -> 元信息 + 单次奖励 + 目标次数
def _mission_defs() -> list[dict]:
    return [
        {"key": "checkin", "name": "每日签到", "icon": "📅", "desc": "每天点一次签到", "reward": 10, "target": 1},
        {"key": "post", "name": "发布一条动态", "icon": "✍️", "desc": "在自己的校园圈发一条动态", "reward": 10, "target": 1},
        {"key": "comment", "name": "发表评论", "icon": "💬", "desc": "今天发出 2 条评论", "reward": 8, "target": 2},
        {"key": "like", "name": "收获 3 个赞", "icon": "❤️", "desc": "今天发布的内容累计收到 3 个赞", "reward": 10, "target": 3},
        {"key": "guess", "name": "完成今日竞猜", "icon": "🏆", "desc": "参与一次今日竞猜押注", "reward": 8, "target": 1},
    ]


def _goal_reward(db: Session, user: User, key: str):
    for m in _mission_defs():
        if m["key"] == key:
            return m["target"], m["reward"], m
    return 0, 0, None


def mission_progress(db: Session, user: User, key: str) -> int:
    """计算某任务今天已累计的次数（>= 目标即视为完成）。"""
    # created_at 按 UTC naive 存储，用北京今日 0 点的 UTC 时刻比较；
    # 签到 check_in_date 是北京墙钟日期字段，仍用北京墙钟 0 点。
    today = beijing_today_start()
    wall = beijing_wall_midnight()
    user_id = user.id

    if key == "checkin":
        return 1 if db.scalar(
            select(func.count(CheckIn.id)).where(
                CheckIn.user_id == user_id, CheckIn.check_in_date >= wall
            )
        ) else 0

    if key == "post":
        return db.scalar(
            select(func.count(Post.id)).where(Post.author_id == user_id, Post.created_at >= today)
        ) or 0

    if key == "comment":
        return db.scalar(
            select(func.count(Comment.id)).where(Comment.user_id == user_id, Comment.created_at >= today)
        ) or 0

    if key == "like":
        # 今天收到赞 = 对我今天发布的 posts 收到的赞（target 用 post）
        my_posts = select(Post.id).where(Post.author_id == user_id, Post.created_at >= today)
        return db.scalar(
            select(func.count(Like.id)).where(
                Like.target_type == "post",
                Like.target_id.in_(my_posts),
                Like.created_at >= today,
            )
        ) or 0

    if key == "guess":
        return 1 if db.scalar(
            select(func.count(GuessBet.id)).where(
                GuessBet.user_id == user_id, GuessBet.created_at >= today
            )
        ) else 0

    return 0


def list_missions(db: Session, user: User) -> list[dict]:
    """返回任务列表，附进度/可领取状态。"""
    out = []
    for m in _mission_defs():
        key = m["key"]
        progress = mission_progress(db, user, key)
        claimed = bool(db.scalar(
            select(func.count(CoinTransaction.id)).where(
                CoinTransaction.user_id == user.id,
                CoinTransaction.type == "daily_task",
                CoinTransaction.ref_id == key,
                CoinTransaction.created_at >= beijing_today_start(),
            )
        ))
        out.append({
            "key": key,
            "name": m["name"],
            "icon": m["icon"],
            "desc": m["desc"],
            "reward": m["reward"],
            "target": m["target"],
            "progress": min(progress, m["target"]),
            "done": progress >= m["target"],
            "claimed": claimed,
        })
    return out


def claim_mission(db: Session, user: User, key: str) -> dict:
    target, reward, m = _goal_reward(db, user, key)
    if not m:
        raise ValueError("任务不存在")

    progress = mission_progress(db, user, key)
    if progress < target:
        return {
            "awarded": 0,
            "message": "任务还没完成，加油！",
            "coins": coin_service.get_balance(db, user.id),
            "progress": progress,
            "target": target,
        }

    awarded = coin_service.grant_daily_task(
        db, user, key, reward, cap=1, description=f"每日任务：{m['name']}（+{reward}金币）"
    )
    db.commit()
    if awarded <= 0:
        return {
            "awarded": 0,
            "message": "今日该任务奖励已领取过了",
            "coins": coin_service.get_balance(db, user.id),
            "progress": progress,
            "target": target,
        }
    return {
        "awarded": awarded,
        "message": f"恭喜获得 {awarded} 金币",
        "coins": coin_service.get_balance(db, user.id),
        "progress": progress,
        "target": target,
    }