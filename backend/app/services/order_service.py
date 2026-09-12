"""接单大厅（项目 2）业务逻辑：交易币钱包 + 求助/接单/完单。

金额均以整数「交易币」或「分」存储，避免浮点误差。
配置项（用 Setting 表，后台可改）：
- task_exchange_rate   充值汇率：1 元 = N 交易币（默认 100）
- task_commission_rate 发布任务抽成百分比（默认 5）
- task_withdraw_min_cents 最低提现金额（分，默认 600 = 6 元）
- task_boost_price     每次曝光（置顶）消耗交易币（默认 10）
"""

from math import floor

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
from app.models import (
    OrderBid,
    OrderTask,
    User,
    Wallet,
    WalletTransaction,
    WithdrawRequest,
)
from app.services import settings_service

# ==================== 配置读取 ====================
def _rate(db: Session) -> int:
    return max(1, settings_service.get_int(db, "task_exchange_rate", 100))


def _commission(db: Session) -> int:
    v = settings_service.get_int(db, "task_commission_rate", 5)
    return min(100, max(0, v))


def _withdraw_min_cents(db: Session) -> int:
    return max(1, settings_service.get_int(db, "task_withdraw_min_cents", 600))


def _boost_price(db: Session) -> int:
    return max(1, settings_service.get_int(db, "task_boost_price", 10))


# ==================== 钱包 ====================
def get_wallet(db: Session, user_id: int) -> Wallet:
    w = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if w is None:
        w = Wallet(user_id=user_id, balance=0, frozen=0)
        db.add(w)
        db.flush()
    return w


def _ledger(
    db: Session,
    user_id: int,
    amount: int,
    type_: str,
    ref_id: str | None = None,
    description: str | None = None,
    status: str = "completed",
    balance_after: int | None = None,
) -> WalletTransaction:
    w = get_wallet(db, user_id)
    final = w.balance if balance_after is None else balance_after
    tx = WalletTransaction(
        user_id=user_id,
        amount=amount,
        balance_after=final,
        type=type_,
        status=status,
        ref_id=ref_id,
        description=description,
    )
    db.add(tx)
    return tx


def credit(db: Session, user: User, amount: int, type_: str, ref_id: str | None = None, description: str | None = None) -> None:
    if amount <= 0:
        return
    w = get_wallet(db, user.id)
    w.balance += amount
    _ledger(db, user.id, amount, type_, ref_id, description, balance_after=w.balance)


def debit(db: Session, user: User, amount: int, type_: str, ref_id: str | None = None, description: str | None = None) -> None:
    if amount <= 0:
        return
    w = get_wallet(db, user.id)
    if w.balance < amount:
        raise ValueError("交易币不足")
    w.balance -= amount
    _ledger(db, user.id, -amount, type_, ref_id, description, balance_after=w.balance)


# ==================== 任务序列化 ====================
def task_dict(db: Session, t: OrderTask, me: int | None) -> dict:
    poster = db.get(User, t.user_id)
    assignee = db.get(User, t.assignee_id) if t.assignee_id else None
    return {
        "id": t.id,
        "user_id": t.user_id,
        "poster_name": poster.nickname if poster else "",
        "poster_avatar": poster.avatar_url if poster else "",
        "title": t.title,
        "content": t.content,
        "category": t.category,
        "reward": t.reward,
        "escrow": t.escrow,
        "status": t.status,
        "assignee_id": t.assignee_id,
        "assignee_name": assignee.nickname if assignee else "",
        "boost": t.boost,
        "deliver_note": t.deliver_note,
        "is_mine": me is not None and t.user_id == me,
        "is_assigned_to_me": me is not None and t.assignee_id == me,
        "created_at": to_iso_zh(t.created_at),
        "completed_at": to_iso_zh(t.completed_at),
    }


def status_text(status: str) -> str:
    return {
        "open": "待接单",
        "in_progress": "进行中",
        "done": "已交付",
        "completed": "已完成",
        "cancelled": "已取消",
    }.get(status, status)