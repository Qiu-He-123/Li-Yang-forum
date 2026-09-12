"""抽奖（提现改抽奖）与同伴圈 AI 助手日志数据模型。

抽奖系统：
- LotteryAccount  用户抽奖券账户（每用户一行，券数量）
- LotteryPrize    奖池奖品（管理员配置：中奖权重 / 数量范围 / 爆率峰值 / 广告加成）
- LotteryDraw     一次抽取记录（含看广告加成后的总量）
- LotteryInventory 中奖待领/兑付明细
AI 日志：
- AiChatLog      全局 AI 助手对话埋点日志
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class _Ts:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LotteryAccount(Base, _Ts):
    """用户抽奖券账户（每用户一行）。"""

    __tablename__ = "lottery_accounts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_lottery_account_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_qty: Mapped[int] = mapped_column(Integer, default=0)   # 抽奖券张数
    total_draws: Mapped[int] = mapped_column(Integer, default=0)  # 累计抽奖次数


class LotteryPrize(Base, _Ts):
    """奖池奖品（后台配置）。"""

    __tablename__ = "lottery_prizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    image_url: Mapped[str | None] = mapped_column(String(255), default=None)
    weight: Mapped[int] = mapped_column(Integer, default=10)      # 中奖权重（越大越容易抽到）
    min_qty: Mapped[int] = mapped_column(Integer, default=1)      # 数量下限
    max_qty: Mapped[int] = mapped_column(Integer, default=1)      # 数量上限
    hot_qty: Mapped[int] = mapped_column(Integer, default=1)      # 爆率峰值数量（[min,max] 内命中概率最大的值）
    ad_qty: Mapped[int] = mapped_column(Integer, default=1)       # 每看一次广告追加的数量
    max_ad_times: Mapped[int] = mapped_column(Integer, default=4) # 单次中奖可看广告最大次数
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class LotteryDraw(Base, _Ts):
    """一次抽取记录。"""

    __tablename__ = "lottery_draws"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("lottery_prizes.id"))
    prize_name: Mapped[str] = mapped_column(String(64), default="")  # 快照，防止奖品删除后无显示
    base_qty: Mapped[int] = mapped_column(Integer, default=0)        # 首次摇号数量
    ad_times_used: Mapped[int] = mapped_column(Integer, default=0)   # 已看广告次数
    ad_qty_granted: Mapped[int] = mapped_column(Integer, default=0)  # 广告加成数量
    total_qty: Mapped[int] = mapped_column(Integer, default=0)       # = base + ad（单次抽取数量锁定）
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / claimed


class LotteryInventory(Base, _Ts):
    """中奖待领/兑付明细。"""

    __tablename__ = "lottery_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    draw_id: Mapped[int] = mapped_column(ForeignKey("lottery_draws.id"), index=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("lottery_prizes.id"))
    prize_name: Mapped[str] = mapped_column(String(64), default="")
    image_url: Mapped[str | None] = mapped_column(String(255), default=None)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / claimed
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class AiChatLog(Base, _Ts):
    """全局 AI 助手对话埋点日志（best-effort）。"""

    __tablename__ = "ai_chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    input: Mapped[str] = mapped_column(String(255), default="")   # 用户原话
    intent: Mapped[str] = mapped_column(String(100), default="")  # 命中意图
    reply: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(50), default="")   # 跳转路径 / 纯文字
    hit: Mapped[bool] = mapped_column(Boolean, default=False)     # 是否命中意图