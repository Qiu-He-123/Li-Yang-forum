"""金币服务：余额查询 + 统一流水记账（所有增减必须经过这里）。"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import CoinTransaction, User


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
