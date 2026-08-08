import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(subject: str, minutes: int | None = None, days: int | None = None) -> str:
    """生成 JWT。

    T2-6 修复：加入 jti（JWT ID）随机字符串，避免同一秒为同一 user 生成的
    refresh_token 完全相同导致 UNIQUE constraint failed。
    """
    settings = get_settings()
    # 兼容 Python 3.10：使用 timezone.utc 代替 Python 3.11+ 的 UTC
    expire = datetime.now(timezone.utc) + (timedelta(days=days) if days else timedelta(minutes=minutes or 30))
    payload = {"sub": subject, "exp": expire, "jti": secrets.token_urlsafe(16)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    return str(payload["sub"])
