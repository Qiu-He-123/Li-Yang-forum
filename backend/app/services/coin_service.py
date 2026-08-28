"""金币服务：余额查询 + 统一流水记账（所有增减必须经过这里）。"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CoinTransaction, User
from app.core.time_utils import beijing_today_start


def get_balance(db: Session, user_id: int) -> int:
    user = db.get(User, user_id)
    return user.coins if user and user.coins is not None else 0


def record_transaction(
    db: Session,
    user: User,
    amount: int,
    type_: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> int:
    """写入流水并更新余额，返回扣/增后的余额。"""
    user.coins = (user.coins or 0) + amount
    db.flush()
    db.add(
        CoinTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.coins,
            type=type_,
            ref_id=ref_id,
            description=description,
        )
    )
    db.flush()
    return user.coins


def grant_coins(
    db: Session,
    user: User,
    amount: int,
    type_: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> int:
    if amount <= 0:
        return get_balance(db, user.id)
    return record_transaction(db, user, amount, type_, ref_id, description)


def charge_coins(
    db: Session,
    user: User,
    amount: int,
    type_: str,
    ref_id: str | None = None,
    description: str | None = None,
) -> int:
    """扣金币，余额不足抛 400。"""
    if amount <= 0:
        return get_balance(db, user.id)
    if (user.coins or 0) < amount:
        raise HTTPException(status_code=400, detail="金币不足")
    return record_transaction(db, user, -amount, type_, ref_id, description)


def grant_daily_task(
    db: Session,
    user: User,
    key: str,
    amount: int,
    cap: int,
    description: str = "",
) -> int:
    """每日任务金币发放（带每日笔数上限，防刷）。

    - 同一 user + 同一天 + 同 key 计次，达到 cap 后不再发放。
    - 返回本次实际发放的金币数（0 表示已达今日上限）。
    计次直接查 CoinTransaction 流水（type='daily_task'），无需额外建表字段。
    """
    if amount <= 0 or cap <= 0:
        return 0
    today = beijing_today_start()
    cnt = db.scalar(
        select(func.count(CoinTransaction.id)).where(
            CoinTransaction.user_id == user.id,
            CoinTransaction.type == "daily_task",
            CoinTransaction.ref_id == key,
            CoinTransaction.created_at >= today,
        )
    ) or 0
    if cnt >= cap:
        return 0
    record_transaction(db, user, amount, "daily_task", key, description or f"每日任务：{key}")
    return amount
