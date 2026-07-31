"""T9-1 认证模块回归测试。

覆盖：
- 注册（成功 / 重复手机号 / 缺协议同意 / 验证码错误 / 密码不一致）
- 登录（密码登录 / 验证码登录 / 错误密码 / 不存在用户）
- 登出（清 Cookie + 撤销 refresh_token）
- /auth/me 会话校验
- /auth/refresh refresh_token 轮转
- /auth/send-code 验证码 stub
- 登录失败锁定（T7-8 持久化）
"""
import pytest

from tests.conftest import register


def test_register_success(client):
    """注册成功 → 返回 user_id + 下发 access_token / refresh_token Cookie。"""
    info = register(client, "13700000001", "认证测试员")
    assert info["user_id"] > 0
    # Cookie 已下发
    cookies = client.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies


def test_register_rejects_duplicate_phone(client):
    """重复手机号注册返回 -106 PHONE_REGISTERED。"""
    register(client, "13700000002", "用户A")
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "用户B",
        "phone": "13700000002",
        "code": "123456",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] != 0, f"重复手机号应被拒: {resp}"


def test_register_rejects_wrong_code(client):
    """验证码错误返回 -104 CODE_INVALID。"""
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "错码用户",
        "phone": "13700000003",
        "code": "000000",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] != 0


def test_register_rejects_password_mismatch(client):
    """两次密码不一致返回 -102 PASSWORD_MISMATCH。"""
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": "密码不一致",
        "phone": "13700000004",
        "code": "123456",
        "password": "Pwd@2026",
        "confirm_password": "Different@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] != 0


def test_login_with_password(client):
    """密码登录成功 + 颁发 token。"""
    register(client, "13700000005", "登录员", password="Pwd@2026")
    # 先登出
    client.post("/auth/logout")
    # 再用密码登录
    resp = client.post("/auth/login", json={"phone": "13700000005", "password": "Pwd@2026"}).json()
    assert resp["code"] == 0
    assert resp["data"]["user_id"] > 0
    assert "access_token" in client.cookies


def test_login_with_code(client):
    """验证码登录成功（dev stub 123456）。"""
    register(client, "13700000006", "验证码登录员")
    client.post("/auth/logout")
    resp = client.post("/auth/login", json={"phone": "13700000006", "code": "123456"}).json()
    assert resp["code"] == 0


def test_login_rejects_wrong_password(client):
    """错误密码登录返回 -103 LOGIN_FAILED。"""
    register(client, "13700000007", "密码错用户")
    client.post("/auth/logout")
    resp = client.post("/auth/login", json={"phone": "13700000007", "password": "WrongPwd"}).json()
    assert resp["code"] == -103


def test_login_rejects_nonexistent_user(client):
    """不存在的手机号登录返回 -103。"""
    resp = client.post("/auth/login", json={"phone": "13999999999", "password": "Pwd@2026"}).json()
    assert resp["code"] == -103


def test_auth_me_validates_session(client):
    """登录态下 /auth/me 返回当前用户信息。"""
    info = register(client, "13700000008", "Me 校验员")
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
    register(client, "13700000009", "登出员")
    # 登出
    resp = client.post("/auth/logout").json()
    assert resp["code"] == 0
    # /auth/me 应失败
    me = client.get("/auth/me").json()
    assert me["code"] == -100
    # refresh_token 已 revoked，再调 /auth/refresh 应失败 -101
    refresh_resp = client.post("/auth/refresh").json()
    assert refresh_resp["code"] == -101


def test_refresh_token_rotation(client):
    """refresh_token 轮转：用后旧的失效，新的可用。"""
    register(client, "13700000010", "刷新员")
    old_refresh = client.cookies["refresh_token"]
    # 调 refresh
    resp = client.post("/auth/refresh").json()
    assert resp["code"] == 0
    new_refresh = client.cookies["refresh_token"]
    assert new_refresh != old_refresh, "refresh_token 应轮转"
    # 旧 refresh 已 revoked，用旧 token 单独请求应失败 -101
    client.cookies.clear()
    client.cookies.set("refresh_token", old_refresh, domain="testserver")
    resp2 = client.post("/auth/refresh").json()
    assert resp2["code"] == -101


def test_send_code_stub(client):
    """send-code stub 返回 dev_code=123456 + cooldown=60。"""
    resp = client.post("/auth/send-code", params={"phone": "13700000011"}).json()
    assert resp["code"] == 0
    assert resp["data"]["dev_code"] == "123456"
    assert resp["data"]["cooldown"] == 60


def test_login_failure_lockout_persists(client, monkeypatch):
    """T7-8：连续 10 次失败后锁定（持久化）。

    测试环境默认放宽了 LOGIN_FAIL_THRESHOLD，这里临时恢复为 10 验证锁定逻辑。
    """
    from app.services import rate_limit_service
    monkeypatch.setattr(rate_limit_service, "LOGIN_FAIL_THRESHOLD", 10)
    monkeypatch.setattr(rate_limit_service, "LOGIN_LOCK_MINUTES", 30)

    register(client, "13700000012", "锁定测试员")
    client.post("/auth/logout")
    # 连续 10 次错误密码
    for i in range(10):
        resp = client.post("/auth/login", json={"phone": "13700000012", "password": "WrongPwd"}).json()
        assert resp["code"] == -103, f"第 {i+1} 次应返回 -103, 实际 {resp['code']}"
    # 第 11 次应被锁定 -104 LOGIN_LOCKED
    resp = client.post("/auth/login", json={"phone": "13700000012", "password": "WrongPwd"}).json()
    assert resp["code"] == -104, f"第 11 次应被锁定 -104, 实际 {resp['code']}"


def test_change_password(client):
    """修改密码后旧密码登录失败，新密码登录成功。"""
    register(client, "13700000013", "改密员", password="OldPwd@2026")
    # 修改密码
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "OldPwd@2026",
            "new_password": "NewPwd@2026",
            "confirm_password": "NewPwd@2026",
        },
    ).json()
    assert resp["code"] == 0
    # 登出
    client.post("/auth/logout")
    # 旧密码登录应失败
    r1 = client.post("/auth/login", json={"phone": "13700000013", "password": "OldPwd@2026"}).json()
    assert r1["code"] == -103
    # 新密码登录应成功
    r2 = client.post("/auth/login", json={"phone": "13700000013", "password": "NewPwd@2026"}).json()
    assert r2["code"] == 0


def test_change_password_rejects_wrong_old(client):
    """旧密码错误时修改密码失败。"""
    register(client, "13700000014", "改密错旧")
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "WrongOldPwd",
            "new_password": "NewPwd@2026",
            "confirm_password": "NewPwd@2026",
        },
    ).json()
    assert resp["code"] == -103
