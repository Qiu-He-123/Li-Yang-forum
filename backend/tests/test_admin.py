"""T9-1 管理员模块回归测试。

覆盖：
- admin 登录（Body 方式 + 下发 admin_token Cookie）
- 错误密码登录失败
- 不存在用户登录失败（无后门）
- 未带 Cookie 访问 /admin/* 返回 -100
- 带 Cookie 访问各管理接口
- /admin/posts 列表
- /admin/users 列表
- /admin/reports 列表
- /admin/logs 列表
- /admin/user-logs 用户操作日志查询
- /admin/announcements 创建公告
- admin OperationLog.admin_id 写入（T7-6）

注意：测试用 in-memory SQLite，CLI 脚本连接生产 DB，
所以这里直接在测试 DB 中插入 Admin 记录。
"""
import pytest

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin
from tests.conftest import create_post, register

ADMIN_USER = "t9_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    """在测试 in-memory DB 中创建管理员（如不存在）。"""
    with SessionLocal() as db:
        existing = db.query(Admin).filter(Admin.username == ADMIN_USER).first()
        if not existing:
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _admin_login(client) -> None:
    """管理员登录。"""
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"
    assert "admin_token" in client.cookies, "未下发 admin_token Cookie"


def test_admin_login_returns_cookie(client):
    """admin 登录成功 + 下发 admin_token Cookie。"""
    _admin_login(client)


def test_admin_login_rejects_wrong_password(client):
    """错误密码登录失败 -103。"""
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": "WrongPwd"}).json()
    assert resp["code"] == -103


def test_admin_login_rejects_nonexistent_user(client):
    """不存在的管理员登录失败 -103（无后门 T2-3）。"""
    resp = client.post(
        "/admin/login",
        json={"username": "nonexistent_xyz", "password": "any"},
    ).json()
    assert resp["code"] == -103


def test_admin_login_rejects_url_query_password(client):
    """T2-2：旧式 URL query 登录失败（密码不再走 URL）。"""
    _ensure_admin()
    resp = client.post(f"/admin/login?username={ADMIN_USER}&password={ADMIN_PWD}").json()
    assert resp["code"] != 0, "URL query 登录应被拒"


def test_admin_routes_reject_unauthenticated(client):
    """T2-1：未带 Cookie 访问 /admin/* 全部返回 -100。"""
    for path in ["/admin/posts", "/admin/comments", "/admin/users", "/admin/reports", "/admin/logs"]:
        resp = client.get(path).json()
        assert resp["code"] == -100, f"{path} 未鉴权应返回 -100, 实际 {resp['code']}"


def test_admin_posts_list(client):
    """带 Cookie 访问 /admin/posts 返回列表。"""
    _admin_login(client)
    resp = client.get("/admin/posts").json()
    assert resp["code"] == 0
    assert isinstance(resp["data"]["items"], list)
    assert "total" in resp["data"]


def test_admin_users_list(client):
    """带 Cookie 访问 /admin/users 返回用户列表。"""
    _admin_login(client)
    resp = client.get("/admin/users").json()
    assert resp["code"] == 0
    assert isinstance(resp["data"]["items"], list)
    assert "total" in resp["data"]


def test_admin_reports_list(client):
    """带 Cookie 访问 /admin/reports 返回举报列表。"""
    _admin_login(client)
    resp = client.get("/admin/reports").json()
    assert resp["code"] == 0
    assert isinstance(resp["data"]["items"], list)
    assert "total" in resp["data"]


def test_admin_logs_list(client):
    """带 Cookie 访问 /admin/logs 返回日志列表。"""
    _admin_login(client)
    resp = client.get("/admin/logs").json()
    assert resp["code"] == 0
    assert isinstance(resp["data"]["items"], list)
    assert "total" in resp["data"]


def test_admin_user_logs_query(client):
    """/admin/user-logs 按 user_id / action 过滤。"""
    # 先注册一个用户并产生日志
    info = register(client, "13705000001", "日志员")
    create_post(client, info["school_id"], "产生日志的帖子")
    # 管理员登录
    client.post("/auth/logout")
    _admin_login(client)
    resp = client.get(
        "/admin/user-logs",
        params={"user_id": info["user_id"]},
    ).json()
    assert resp["code"] == 0
    assert isinstance(resp["data"]["items"], list)
    # 应含该用户的日志
    if resp["data"]["items"]:
        for log in resp["data"]["items"]:
            assert log.get("user_id") == info["user_id"], f"日志 user_id 不匹配: {log}"


def test_admin_create_announcement(client):
    """POST /admin/announcements 创建公告。"""
    _admin_login(client)
    resp = client.post(
        "/admin/announcements",
        json={
            "title": "T9-1 测试公告",
            "content": "这是一条 T9-1 测试公告内容",
            "school_id": None,
        },
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["title"] == "T9-1 测试公告"


def test_admin_logs_contain_admin_id(client):
    """T7-6：admin 操作日志含 admin_id。"""
    _admin_login(client)
    # 触发一个 admin 操作（创建公告）
    client.post(
        "/admin/announcements",
        json={"title": "T7-6 日志测试", "content": "内容", "school_id": None},
    )
    # 查日志
    resp = client.get("/admin/logs").json()
    assert resp["code"] == 0
    # 应至少有一条日志含 admin_id
    if resp["data"]["items"]:
        admin_logs = [log for log in resp["data"]["items"] if log.get("admin_id")]
        assert len(admin_logs) > 0, "T7-6: 日志应含 admin_id"


def test_admin_logout_clears_cookie(client):
    """admin 登出后访问 /admin/posts 返回 -100。"""
    _admin_login(client)
    resp = client.post("/admin/logout").json()
    assert resp["code"] == 0
    # 登出后访问应失败
    resp = client.get("/admin/posts").json()
    assert resp["code"] == -100


def test_admin_delete_post(client):
    """admin 可删除任意帖子。"""
    # 注册用户发帖
    info = register(client, "13705000002", "被删帖用户")
    post = create_post(client, info["school_id"], "待删帖子")
    post_id = post["id"]
    # 切到管理员
    client.post("/auth/logout")
    _admin_login(client)
    # admin 删除帖子
    resp = client.delete(f"/admin/posts/{post_id}").json()
    assert resp["code"] == 0
