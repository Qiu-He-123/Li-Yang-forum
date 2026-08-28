"""限流与登录失败锁定模型。

T7-8：登录失败锁定持久化（替代内存变量，进程重启不丢失）。
T7-9：IP 限流（防暴力破解）。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RateLimit(Base):
    """T7-9：IP 限流计数表。

    key 格式：ip:{ip}:{action}，如 ip:127.0.0.1:login
    每个窗口（60 秒）内最多 10 次请求。
    """

    __tablename__ = "rate_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoginFailure(Base):
    """T7-8：登录失败锁定持久化表。

    替代原内存变量 failed_login dict，进程重启后锁定状态仍保留。
    失败 10 次锁定 30 分钟。
    """

    __tablename__ = "login_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, default=None)
