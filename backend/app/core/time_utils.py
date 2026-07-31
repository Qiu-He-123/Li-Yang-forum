"""时间处理工具。

统一处理数据库存储的 naive datetime（视为 UTC）与 API 序列化的时区问题。

背景：
- SQLite 的 func.now() / CURRENT_TIMESTAMP 返回 UTC 时间（naive，无 tzinfo）
- Python datetime.now() 返回本地时间（naive，无 tzinfo）
- 混用导致同一字段有时是 UTC、有时是本地时间

统一方案：
- 所有数据库返回的 naive datetime 一律视为 UTC
- API 序列化时附加 +08:00（北京时间）后输出 ISO 字符串
- 新代码写入数据库时统一用 now_utc() 返回 naive UTC datetime
"""
from datetime import date, datetime, timedelta, timezone

# 北京时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))
# UTC 时区
UTC_TZ = timezone.utc


def now_utc() -> datetime:
    """返回当前 UTC 时间（naive，无 tzinfo）。

    用于写入数据库，保持与 SQLite func.now() 一致（都是 UTC naive）。
    """
    return datetime.utcnow()


def to_beijing(dt: datetime | None) -> datetime | None:
    """把 datetime 转换为带时区的北京时间。

    - None → None
    - naive datetime → 视为 UTC，转北京时间
    - 带 tzinfo 的 datetime → 转北京时间
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # naive datetime 视为 UTC
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(BEIJING_TZ)


def to_iso_zh(dt: datetime | None) -> str | None:
    """把 datetime 序列化为北京时间的 ISO 字符串。

    输出格式：'2026-07-27T22:51:49+08:00'
    前端 new Date() 可正确解析为本地时间。
    """
    bj = to_beijing(dt)
    if bj is None:
        return None
    return bj.isoformat()


def to_iso_utc(dt: datetime | None) -> str | None:
    """把 datetime 序列化为 UTC ISO 字符串（带 Z 后缀）。

    输出格式：'2026-07-27T14:51:49Z'
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ).strftime('%Y-%m-%dT%H:%M:%SZ')


def calculate_age(birthday: date | None, today: date | None = None) -> int | None:
    """从生日计算年龄（周岁）。

    Args:
        birthday: 生日日期
        today: 参考日期（默认今天）

    Returns:
        年龄（整数），birthday 为 None 时返回 None
    """
    if birthday is None:
        return None
    today = today or date.today()
    age = today.year - birthday.year
    # 今年生日还没过 → 减 1
    if (today.month, today.day) < (birthday.month, birthday.day):
        age -= 1
    return age
