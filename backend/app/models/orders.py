"""接单大厅（项目 2）数据模型。

求助 · 接单 · 完单交易平台：
- OrderTask  求助/任务单（含悬赏交易币、状态流转）
- OrderBid   接单人报价/留言
- Wallet     交易币账户（整数"币"为最小单位）
- WalletTransaction  钱包流水（充值/提现/悬赏/抽成/曝光）
- OrderReview 完单评价
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class _Ts:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OrderTask(Base, _Ts):
    """求助/任务单。"""

    __tablename__ = "order_tasks"

    STATUS_OPEN = "open"                # 待接单
    STATUS_IN_PROGRESS = "in_progress"  # 进行中（已被人接单）
    STATUS_DONE = "done"                # 已完成（接单人交付）
    STATUS_COMPLETED = "completed"      # 已验收（帖子确认，悬赏发放）
    STATUS_CANCELLED = "cancelled"      # 已取消（悬赏退回）

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    # 悬赏金额（交易币，整数）。发布时从发布者钱包划入托管(escrow)
    reward: Mapped[int] = mapped_column(Integer, default=0)
    # 托管中的交易币（发布时=reward；完成后发放给接单人=reward-抽成）
    escrow: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # 曝光度：越高在接单大厅越靠前
    boost: Mapped[int] = mapped_column(Integer, default=0)
    # 追加悬赏（曝光/置顶等交易币扩使用范围，可叠加）
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    deliver_note: Mapped[str | None] = mapped_column(Text, default=None)


class OrderBid(Base, _Ts):
    """接单人报价/留言（回应求助）。"""

    __tablename__ = "order_bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("order_tasks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 报价（交易币，整数；0=默认按帖子悬赏）
    quote: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / accepted / rejected / cancelled


class Wallet(Base, _Ts):
    """交易币账户（每用户一行）。"""

    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("user_id", name="uq_wallet_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)      # 可用余额（整数币）
    frozen: Mapped[int] = mapped_column(Integer, default=0)       # 冻结（提现/托管中）


class WalletTransaction(Base, _Ts):
    """钱包流水。"""

    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)   # 正=入账，负=支出
    balance_after: Mapped[int] = mapped_column(Integer, default=0)
    # recharge / withdraw / task_reward / task_commission / task_publish / boost / refund / withdraw_refund / withdraw_paid
    type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed / pending / rejected
    # 关联：订单 id / 提现单 id
    ref_id: Mapped[str | None] = mapped_column(String(64), default=None)
    description: Mapped[str | None] = mapped_column(String(255), default=None)


class OrderReview(Base, _Ts):
    """完单评价（接单方与发布方互评）。"""

    __tablename__ = "order_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("order_tasks.id"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer, default=5)  # 1-5
    content: Mapped[str | None] = mapped_column(Text, default=None)


class WithdrawRequest(Base, _Ts):
    """提现申请单（最低 6 元，经后台审核后打款）。"""

    __tablename__ = "withdraw_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 提现币数（已按汇率换算，从钱包扣除并进入冻结）
    amount_bin: Mapped[int] = mapped_column(Integer, default=0)
    # 到账金额（元，存分为整数，避免浮点误差：6.00 元 -> 600）
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    # 收款信息（支付宝/微信账号）由用户填写，后台打款
    payee: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / completed / rejected
    reject_reason: Mapped[str | None] = mapped_column(String(255), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class OrderAiSession(Base, _Ts):
    """订单 AI 会话（用户每行，跨会话保留聊天记录）。"""

    __tablename__ = "order_ai_sessions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_order_ai_session_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    daily_date: Mapped[str] = mapped_column(String(16), default="")   # 每日额度滚动标记（北京时间 YYYY-MM-DD）
    daily_token: Mapped[int] = mapped_column(Integer, default=0)      # 本日已消耗 token


class OrderAiMessage(Base, _Ts):
    """订单 AI 对话消息（user / assistant / tool 卡片）。"""

    __tablename__ = "order_ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("order_ai_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="assistant")  # user / assistant / tool
    content: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[Any] = mapped_column(JSON, default=None)             # 工具卡片结构化数据