"""QQ 号 / 邀请码 登录与 QQ 唯一性 回归测试。

覆盖本次新加的机制：
- 注册时填国民 QQ → 用 QQ 号登录成功（QQ 作为登录凭证）
- 重复 QQ 注册被拒（-307 QQ_EXISTS）
- 用邀请码登录成功（邀请码作为登录凭证，大写不敏感）
- 账号登录仍正常（回归）
"""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User
from tests.conftest import register


def _register_with_qq(client, username: str, qq: str, password: str = "Pwd@2026"):
    """用指定 QQ 注册，返回 dict（不再自动走 conftest.register 的默认邀请码逻辑）。"""
    from sqlalchemy import select as sa_select
    from app.core.database import SessionLocal as SL
    from app.models import SeedInviteCode

    with SL() as db:
        seed = db.scalar(sa_select(SeedInviteCode).where(SeedInviteCode.used_by.is_(None)))
        assert seed is not None
        invite_code = seed.code
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": username,
        "username": username,
        "password": password,
        "confirm_password": password,
        "school_id": schools[0]["id"],
        "agreed": True,
        "qq": qq,
        "invite_code": invite_code,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == 0, f"QQ 注册失败: {resp}"
    return resp["data"]["user_id"]


def _get_qq_by_username(username: str) -> str:
    """取某用户实际落库的 QQ（验证 QQ 已落库）。"""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        return user.qq


def test_register_with_qq_persists(client):
    """注册填 QQ → QQ 确实写入数据库（确认落库）。"""
    _register_with_qq(client, "qquser_01", "100001")
    stored = _get_qq_by_username("qquser_01")
    assert stored == "100001", f"QQ 应落库，实际存储: {stored!r}"


def test_login_with_qq(client):
    """用 QQ 号（而非账号）登录成功。"""
    _register_with_qq(client, "qquser_02", "100002")
    client.post("/auth/logout")
    resp = client.post(
        "/auth/login", json={"username": "100002", "password": "Pwd@2026"}
    ).json()
    assert resp["code"] == 0, f"用 QQ 登录失败: {resp}"
    assert resp["data"]["user_id"] > 0


def test_register_rejects_duplicate_qq(client):
    """相同 QQ 重复注册应返回 -307 QQ_EXISTS。"""
    _register_with_qq(client, "qquser_03", "100003")
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "重复QQ",
        "username": "qquser_03b",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
        "qq": "100003",
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == -307, f"重复 QQ 应被拒 -307, 实际: {resp}"


def test_login_with_invite_code(client):
    """用邀请码登录成功（邀请码即用户自己的 8 位码）。"""
    _register_with_qq(client, "qquser_04", "100004")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "qquser_04"))
        invite_code = user.invite_code
        assert invite_code, "注册后应已分配邀请码"
    client.post("/auth/logout")
    # 小写输入邀请码也应能登录（大写比对转 UTF）
    resp = client.post(
        "/auth/login", json={"username": invite_code.lower(), "password": "Pwd@2026"}
    ).json()
    assert resp["code"] == 0, f"用邀请码登录失败: {resp}"
    assert resp["data"]["user_id"] == user.id


def test_login_with_username_still_works(client):
    """账号登录回归：常规账号（无 QQ）仍正常。"""
    register(client, "qquser_05", "账号登录回归")
    client.post("/auth/logout")
    resp = client.post(
        "/auth/login", json={"username": "qquser_05", "password": "Pwd@2026"}
    ).json()
    assert resp["code"] == 0