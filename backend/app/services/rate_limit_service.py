"""限流与登录失败锁定服务。

T7-8：登录失败锁定持久化（替代 Redis，用 SQLite 表，进程重启不丢失）。
T7-9：IP 限流（登录/注册/发送验证码接口，每分钟最多 10 次）。

设计选择：
- 不引入 Redis 依赖（项目未部署 Redis），用 SQLite 表 + 时间窗口实现。
- rate_limits 表存储 (key, count, window_start)，按 key 索引。
- 登录失败锁定用 login_failures 表存储 (phone, fail_count, locked_until)。

注意：SQLite 的 DateTime 列默认不存储时区信息（naive datetime），
_now() 必须返回 naive UTC 时间，否则与数据库字段比较会抛
TypeError: can't subtract offset-naive and offset-aware datetimes。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.rate_limit import LoginFailure, RateLimit

# 限流配置
RATE_LIMIT_WINDOW_SECONDS = 60  # 1 分钟窗口
RATE_LIMIT_MAX_REQUESTS = 10  # 每窗口最多 10 次

# 登录失败锁定配置
LOGIN_FAIL_THRESHOLD = 10  # 失败 10 次锁定
LOGIN_LOCK_MINUTES = 30  # 锁定 30 分钟


def _now() -> datetime:
    """返回当前 UTC 时间（naive，不带 tzinfo）。

    与 SQLite DateTime 列保持一致，避免 offset-naive vs offset-aware 比较错误。
    注意：datetime.utcnow() 已废弃，用 datetime.now(UTC).replace(tzinfo=None) 替代。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============ T7-9 IP 限流 ============

def check_rate_limit(
    db: Session,
    key: str,
    max_requests: int = RATE_LIMIT_MAX_REQUESTS,
    window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
) -> bool:
    """检查 key 是否超过限流阈值。

    Args:
        key: 限流键，如 "ip:127.0.0.1:login"
        max_requests: 窗口内最大请求数
        window_seconds: 时间窗口长度（秒），默认 60；传 3600 为小时窗口、86400 为日窗口

    Returns:
        True 表示允许请求，False 表示被限流
    """
    now = _now()
    record = db.scalar(select(RateLimit).where(RateLimit.key == key))
    if not record:
        # 首次请求：创建记录
        db.add(RateLimit(key=key, count=1, window_start=now))
        db.commit()
        return True

    # 窗口过期：重置计数
    if now - record.window_start > timedelta(seconds=window_seconds):
        record.count = 1
        record.window_start = now
        db.commit()
        return True

    # 窗口内：检查是否超限
    if record.count >= max_requests:
        return False

    record.count += 1
    db.commit()
    return True


# ============ T7-8 登录失败锁定 ============

def check_login_locked(db: Session, phone: str) -> bool:
    """检查手机号是否被锁定。

    Returns: True 表示被锁定（应拒绝登录），False 表示可继续
    """
    record = db.scalar(select(LoginFailure).where(LoginFailure.phone == phone))
    if not record:
        return False
    now = _now()
    if record.fail_count >= LOGIN_FAIL_THRESHOLD and record.locked_until and record.locked_until > now:
        return True
    # 锁定已过期：重置计数
    if record.locked_until and record.locked_until <= now:
        record.fail_count = 0
        record.locked_until = None
        db.commit()
    return False


def record_login_failure(db: Session, phone: str) -> int:
    """记录一次登录失败，返回当前失败次数。"""
    now = _now()
    record = db.scalar(select(LoginFailure).where(LoginFailure.phone == phone))
    if not record:
        record = LoginFailure(phone=phone, fail_count=1, locked_until=None)
        db.add(record)
    else:
        record.fail_count += 1
        if record.fail_count >= LOGIN_FAIL_THRESHOLD:
            record.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
    db.commit()
    return record.fail_count


def clear_login_failures(db: Session, phone: str) -> None:
    """登录成功后清空失败记录。"""
    db.execute(
        update(LoginFailure).where(LoginFailure.phone == phone).values(fail_count=0, locked_until=None)
    )
    db.commit()
