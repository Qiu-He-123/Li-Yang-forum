"""验证码与下载令牌模型。

- captcha_tickets：图形验证码一次性票据（答案只存服务端，5 分钟过期、绑定 IP）
- download_tokens：APK 下载放行令牌（验证码通过后签发，2 分钟过期、一次性、绑定 IP）
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CaptchaTicket(Base):
    """图形验证码票据。"""

    __tablename__ = "captcha_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    answer: Mapped[str] = mapped_column(String(16))
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class DownloadToken(Base):
    """下载放行令牌：验证码通过后签发，GET 下载时一次性消费。"""

    __tablename__ = "download_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
