"""认证模块回归测试（当前契约：用户名+密码，邀请码选填）。

覆盖：
- 注册（成功 / 重复用户名 / 无效邀请码 / 密码不一致）
- 邀请码流程（填种子码直接 verified / 不填为 unverified）
- 登录（密码登录 / 错误密码 / 不存在用户）
- 登出（清 Cookie + 撤销 refresh_token）
- /auth/me 会话校验
- /auth/refresh refresh_token 轮转
- 登录失败锁定（T7-8 持久化）
"""
import pytest

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import SeedInviteCode
from tests.conftest import register


def _unused_seed_code() -> str:
    """从启动时自动生成的种子码里取一个未使用的（测试用）。"""
    with SessionLocal() as db:
        seed = db.scalar(
            select(SeedInviteCode).where(SeedInviteCode.used_by.is_(None))
        )
        assert seed is not None, "测试环境应存在种子邀请码"
        return seed.code


def test_register_success(client):
    """注册成功 → 返回 user_id + 下发 access_token / refresh_token Cookie。"""
    info = register(client, "user_001", "认证测试员")
    assert info["user_id"] > 0
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies


def test_register_rejects_duplicate_username(client):
    """重复用户名注册返回 -306 USERNAME_EXISTS。"""
    register(client, "user_002", "用户A")
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "用户B",
        "username": "user_002",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == -306, f"重复用户名应被拒: {resp}"


def test_register_rejects_invalid_invite_code(client):
    """无效邀请码返回 -303 INVITE_CODE_INVALID。"""
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "错码用户",
        "username": "user_003",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
        "invite_code": "ZZZZ9999",
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == -303, f"无效邀请码应被拒: {resp}"


def test_register_rejects_password_mismatch(client):
    """两次密码不一致返回 -102 PASSWORD_MISMATCH。"""
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "密码不一致",
        "username": "user_004",
        "password": "Pwd@2026",
        "confirm_password": "Different@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == -201, f"密码不一致应被拒: {resp}"


def test_register_with_seed_code_is_verified(client):
    """填种子邀请码注册 → 直接 verified。"""
    code = _unused_seed_code()
    register(client, "user_005", "种子码用户", invite_code=code)
    me = client.get("/auth/me").json()
    assert me["data"]["verification_status"] == "verified"


def test_register_without_invite_code_is_unverified(client):
    """不填邀请码注册 → unverified（可登录看帖，但不能发帖）。"""
    register(client, "user_006", "未认证用户", invite_code=None)
    me = client.get("/auth/me").json()
    assert me["data"]["verification_status"] == "unverified"


def test_login_with_password(client):
    """密码登录成功 + 颁发 token。"""
    register(client, "user_007", "登录员", password="Pwd@2026")
    client.post("/auth/logout")
    resp = client.post(
        "/auth/login", json={"username": "user_007", "password": "Pwd@2026"}
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["user_id"] > 0
    assert "access_token" in client.cookies


def test_login_rejects_wrong_password(client):
    """错误密码登录返回 -103 LOGIN_FAILED。"""
    register(client, "user_008", "密码错用户")
    client.post("/auth/logout")
    resp = client.post(
        "/auth/login", json={"username": "user_008", "password": "WrongPwd"}
    ).json()
    assert resp["code"] == -103


def test_login_rejects_nonexistent_user(client):
    """不存在的用户名登录返回 -103。"""
    resp = client.post(
        "/auth/login", json={"username": "nobody_999", "password": "Pwd@2026"}
    ).json()
    assert resp["code"] == -103


def test_auth_me_validates_session(client):
    """登录态下 /auth/me 返回当前用户信息。"""
    info = register(client, "user_009", "Me 校验员")
    me = client.get("/auth/me").json()
    assert me["code"] == 0
    assert me["data"]["user_id"] == info["user_id"]
    assert me["data"]["nickname"] == "Me 校验员"


def test_auth_me_rejects_unauthenticated(client):
    """未登录访问 /auth/me 返回 -100 NOT_LOGGED_IN。"""
    me = client.get("/auth/me").json()
    assert me["code"] == -100


def test_logout_clears_session(client):
    """登出后 /auth/me 返回 -100，refresh_token 已 revoked。"""
    register(client, "user_010", "登出员")
    resp = client.post("/auth/logout").json()
    assert resp["code"] == 0
    me = client.get("/auth/me").json()
    assert me["code"] == -100
    refresh_resp = client.post("/auth/refresh").json()
    assert refresh_resp["code"] == -101


def test_refresh_token_rotation(client):
    """refresh_token 轮转：用后旧的失效，新的可用。"""
    register(client, "user_011", "刷新员")
    old_refresh = client.cookies["refresh_token"]
    resp = client.post("/auth/refresh").json()
    assert resp["code"] == 0
    new_refresh = client.cookies["refresh_token"]
    assert new_refresh != old_refresh, "refresh_token 应轮转"
    client.cookies.clear()
    client.cookies.set("refresh_token", old_refresh, domain="testserver")
    resp2 = client.post("/auth/refresh").json()
    assert resp2["code"] == -101


def test_login_failure_lockout_persists(client, monkeypatch):
    """T7-8：连续 10 次失败后锁定（持久化）。"""
    from app.services import rate_limit_service
    monkeypatch.setattr(rate_limit_service, "LOGIN_FAIL_THRESHOLD", 10)
    monkeypatch.setattr(rate_limit_service, "LOGIN_LOCK_MINUTES", 30)

    register(client, "user_012", "锁定测试员")
    client.post("/auth/logout")
    for i in range(10):
        resp = client.post(
            "/auth/login", json={"username": "user_012", "password": "WrongPwd"}
        ).json()
        assert resp["code"] == -103, f"第 {i+1} 次应返回 -103, 实际 {resp['code']}"
    resp = client.post(
        "/auth/login", json={"username": "user_012", "password": "WrongPwd"}
    ).json()
    assert resp["code"] == -104, f"第 11 次应被锁定 -104, 实际 {resp['code']}"


def test_change_password(client):
    """修改密码后旧密码登录失败，新密码登录成功。"""
    register(client, "user_013", "改密员", password="OldPwd@2026")
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "OldPwd@2026",
            "new_password": "NewPwd@2026",
            "confirm_password": "NewPwd@2026",
        },
    ).json()
    assert resp["code"] == 0
    client.post("/auth/logout")
    r1 = client.post(
        "/auth/login", json={"username": "user_013", "password": "OldPwd@2026"}
    ).json()
    assert r1["code"] == -103
    r2 = client.post(
        "/auth/login", json={"username": "user_013", "password": "NewPwd@2026"}
    ).json()
    assert r2["code"] == 0


def test_change_password_rejects_wrong_old(client):
    """旧密码错误时修改密码失败。"""
    register(client, "user_014", "改密错旧")
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "WrongOldPwd",
            "new_password": "NewPwd@2026",
            "confirm_password": "NewPwd@2026",
        },
    ).json()
    assert resp["code"] == -103
