import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 类型声明：用户 token 绝不能当管理员 token 用（越权提权修复）
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
TOKEN_TYPE_ADMIN = "admin"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(
    subject: str,
    minutes: int | None = None,
    days: int | None = None,
    token_type: str = TOKEN_TYPE_ACCESS,
) -> str:
    """生成 JWT。

    T2-6 修复：加入 jti（JWT ID）随机字符串，避免同一秒为同一 user 生成的
    refresh_token 完全相同导致 UNIQUE constraint failed。

    安全修复（越权提权）：payload 增加 "type" 声明（access/refresh/admin），
    用户 token 与管理员 token 无法互相冒充；decode_token 校验类型不匹配直接拒绝。
    """
    settings = get_settings()
    # 兼容 Python 3.10：使用 timezone.utc 代替 Python 3.11+ 的 UTC
    expire = datetime.now(timezone.utc) + (timedelta(days=days) if days else timedelta(minutes=minutes or 30))
    payload = {
        "sub": subject,
        "exp": expire,
        "jti": secrets.token_urlsafe(16),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str | None = None) -> str:
    """解码 JWT；expected_type 指定时校验 payload["type"] 必须匹配。

    类型不匹配抛 jwt.InvalidTokenError（与过期/伪造同等对待），
    防止普通用户 token 被塞进 admin_token Cookie 提权。
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("token type mismatch")
    return str(payload["sub"])
