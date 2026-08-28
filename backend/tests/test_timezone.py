"""时区处理回归测试。

统一约定（app/core/time_utils.py）：
- 数据库中的 naive datetime 一律视为 UTC（与 SQLite func.now() 一致）
- API 序列化输出北京时间 +08:00 的 ISO 字符串
- 新写入统一用 now_utc()（naive UTC），禁止直接写 datetime.now()（本地时间）

覆盖：
1. now_utc() 返回 naive UTC
2. beijing_today_start() 是北京时间 0 点对应的 UTC 边界
3. to_iso_zh() 把 naive datetime 视为 UTC 输出 +08:00
4. 邀请码认证的 verified_at：DB 存 UTC、API 输出带 +08:00
5. 浏览历史 viewed_at：DB 存 UTC、API 输出带 +08:00
6. 封禁 ban_until：DB 存 UTC、登录返回的 ban_until 带 +08:00
"""
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.time_utils import BEIJING_TZ, UTC_TZ, beijing_today_start, now_utc, to_iso_zh
from app.models import BrowseHistory, SeedInviteCode, User

from tests.conftest import create_post, register


def test_now_utc_is_naive_utc():
    """now_utc() 必须返回 naive UTC，与 aware UTC 误差在数秒内。"""
    now = now_utc()
    assert now.tzinfo is None
    delta = abs((now - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds())
    assert delta < 5


def test_beijing_today_start_is_beijing_midnight_boundary():
    """beijing_today_start() 是北京时间今天 0 点对应的 UTC 边界。"""
    start = beijing_today_start()
    assert start.tzinfo is None
    # 转回北京时间必须是当天 00:00
    bj = start.replace(tzinfo=UTC_TZ).astimezone(BEIJING_TZ)
    assert bj.hour == 0 and bj.minute == 0 and bj.second == 0
    # 边界距当前时间不超过 24 小时
    assert timedelta(0) <= now_utc() - start < timedelta(hours=24)


def test_to_iso_zh_treats_naive_as_utc():
    """naive datetime 一律视为 UTC，输出北京时间 +08:00。"""
    naive = datetime(2026, 8, 10, 0, 0, 0)
    assert to_iso_zh(naive) == "2026-08-10T08:00:00+08:00"


def test_verified_at_stored_utc_and_serialized_with_offset(client):
    """填写邀请码后：verified_at 落库为 naive UTC，API 输出 +08:00。"""
    register(client, "tz06000001", "时区认证员", invite_code=None)

    with SessionLocal() as db:
        # 本测试专属种子码，避免依赖共享库中其他测试消耗的种子
        code = "TZ" + secrets.token_hex(4).upper()
        db.add(
            SeedInviteCode(
                code=code,
                note="timezone-test",
                status="unused",
                batch_no="tz-regression",
            )
        )
        db.commit()

    resp = client.post("/auth/apply-invite-code", json={"code": code}).json()
    assert resp["code"] == 0, f"apply invite code failed: {resp}"
    data = resp["data"]
    assert data["verification_status"] == "verified"
    assert re.search(r"\+08:00$", data["verified_at"]), data["verified_at"]

    # 验证状态接口同样带时区
    status = client.get("/auth/verification-status").json()
    assert status["code"] == 0
    assert re.search(r"\+08:00$", status["data"]["verified_at"])

    # DB 中必须是 naive UTC（误差在 2 分钟内）
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "tz06000001"))
        assert user.verified_at is not None
        assert user.verified_at.tzinfo is None
        assert abs((user.verified_at - now_utc()).total_seconds()) < 120


def test_browse_history_viewed_at_stored_utc_and_serialized_with_offset(client):
    """浏览历史 viewed_at：DB 存 naive UTC，API 输出 +08:00。"""
    info = register(client, "tz06000002", "时区浏览员")
    post = create_post(client, info["school_id"], content="时区浏览历史测试帖")

    # 浏览历史在 GET 帖子详情时记录
    resp = client.get(f"/posts/{post['id']}").json()
    assert resp["code"] == 0

    history = client.get("/history").json()
    assert history["code"] == 0
    items = history["data"]["items"]
    assert items and items[0]["post_id"] == post["id"]
    assert re.search(r"\+08:00$", items[0]["viewed_at"]), items[0]["viewed_at"]

    with SessionLocal() as db:
        row = db.scalar(select(BrowseHistory).order_by(BrowseHistory.id.desc()))
        assert row.viewed_at.tzinfo is None
        assert abs((row.viewed_at - now_utc()).total_seconds()) < 120


def test_ban_until_stored_utc_and_login_serializes_with_offset(client):
    """封禁 ban_until：DB 存 naive UTC，登录返回的 ban_until 带 +08:00。"""
    info = register(client, "tz06000003", "时区封禁员")
    with SessionLocal() as db:
        user = db.get(User, info["user_id"])
        user.is_active = False
        user.ban_until = now_utc() + timedelta(hours=1)
        db.commit()

    resp = client.post(
        "/auth/login",
        json={"username": "tz06000003", "password": "Pwd@2026"},
    ).json()
    assert resp["code"] == 0, f"login failed: {resp}"
    ban_info = resp["data"]["ban_info"]
    assert ban_info is not None and ban_info["is_banned"] is True
    assert re.search(r"\+08:00$", ban_info["ban_until"]), ban_info["ban_until"]

    with SessionLocal() as db:
        user = db.get(User, info["user_id"])
        assert user.ban_until.tzinfo is None
        assert abs((user.ban_until - now_utc() - timedelta(hours=1)).total_seconds()) < 120
