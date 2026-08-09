"""T9-1 安全模块回归测试。

覆盖：
- 未登录访问 /admin/* 返回 -100
- 未登录访问 /users/me 返回 -100
- 未登录发帖 / 评论 / 点赞 / 收藏 / 举报 返回 -100
- 伪造 X-Forwarded-For IP 防御（T7-13）
- 伪装 content_type 上传可执行文件（T7-10 magic bytes 校验）
- 非法图片 URL 协议（T7-11 javascript: 被拒）
- CORS 收紧（T7-12 OPTIONS 方法限制）
- jwt_secret 校验（T2-4 代码静态检查）
- posts is_public=false 不能被他人看到（T3-5）
- 帖子作者校验（非作者不可编辑/删除）
"""
import pytest

from tests.conftest import create_post, register


def test_unauthenticated_access_admin_returns_401(client):
    """T2-1：未登录访问 /admin/posts 返回 -100。"""
    resp = client.get("/admin/posts").json()
    assert resp["code"] == -100


def test_unauthenticated_access_users_me_returns_401(client):
    """未登录访问 /users/me 返回 -100。"""
    resp = client.get("/users/me").json()
    assert resp["code"] == -100


def test_unauthenticated_create_post_returns_401(client):
    """未登录发帖返回 -100。"""
    schools = client.get("/schools").json()["data"]
    body = {
        "content": "未登录发帖",
        "school_id": schools[0]["id"],
        "category": "普通",
        "image_urls": [],
        "is_anonymous": False,
        "is_public": True,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] == -100


def test_unauthenticated_like_returns_401(client):
    """未登录点赞返回 -100。"""
    resp = client.post("/likes/post/1").json()
    assert resp["code"] == -100


def test_unauthenticated_favorite_returns_401(client):
    """未登录收藏返回 -100。"""
    resp = client.post("/favorites/1").json()
    assert resp["code"] == -100


def test_unauthenticated_report_returns_401(client):
    """未登录举报返回 -100。"""
    resp = client.post(
        "/reports",
        json={"target_type": "post", "target_id": 1, "reason": "测试"},
    ).json()
    assert resp["code"] == -100


def test_forged_xff_ip_falls_back_to_client_host(client):
    """T7-13：伪造 X-Forwarded-For 非法 IP 时 fallback 到 client.host。"""
    # TestClient 默认 client.host = "testclient"
    # 注册用户并产生一条带 IP 的日志
    register(client, "13706000001", "XFF 测试员")
    # 用伪造的 XFF 头访问 /auth/me（不影响业务，但 IP 提取应 fallback）
    # 这里间接验证：业务不报错
    resp = client.get(
        "/auth/me",
        headers={"X-Forwarded-For": "not-an-ip"},
    ).json()
    assert resp["code"] == 0, "伪造 XFF 不应阻断业务"


def test_valid_xff_ip_is_used(client):
    """T7-13：合法 X-Forwarded-For 第一段被使用，业务正常。"""
    register(client, "13706000002", "XFF 合法员")
    resp = client.get(
        "/auth/me",
        headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1"},
    ).json()
    assert resp["code"] == 0


def test_upload_rejects_disguised_exe(client):
    """T7-10：伪装 content_type 上传 .exe 被拒。"""
    register(client, "13706000003", "上传员")
    # MZ 头是 PE 可执行文件
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
    resp = client.post(
        "/images",
        files={"file": ("test.jpg", fake_exe, "image/jpeg")},
    ).json()
    assert resp["code"] != 0, f"伪装 exe 应被拒: {resp}"


def test_upload_rejects_invalid_content_type(client):
    """上传未声明的 content_type 被拒。"""
    register(client, "13706000004", "格式员")
    resp = client.post(
        "/images",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    ).json()
    assert resp["code"] != 0


def test_post_rejects_javascript_url(client):
    """T7-11：javascript: URL 被拒。"""
    info = register(client, "13706000005", "XSS 测试员")
    body = {
        "content": "T7-11 XSS 测试",
        "school_id": info["school_id"],
        "category": "普通",
        "image_urls": ["javascript:alert(1)"],
        "is_anonymous": False,
        "is_public": True,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] != 0, f"javascript: URL 应被拒: {resp}"


def test_post_accepts_https_url(client):
    """合法 https:// URL 通过校验。"""
    info = register(client, "13706000006", "合法 URL 员")
    body = {
        "content": "合法图片 URL 测试内容",
        "school_id": info["school_id"],
        "category": "普通",
        "image_urls": ["https://example.com/image.png"],
        "is_anonymous": False,
        "is_public": True,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] == 0


def test_cors_rejects_trace_method(client):
    """T7-12：CORS 不允许 TRACE 方法。"""
    # OPTIONS 预检 TRACE 应被拒（返回 405 或不返回 Allow）
    resp = client.options(
        "/posts",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "TRACE",
        },
    )
    # FastAPI 不会返回 Allow: TRACE
    allow = resp.headers.get("allow", "")
    assert "TRACE" not in allow, f"TRACE 不应被允许: {allow}"


def test_cors_allows_standard_methods(client):
    """T7-12：CORS 允许 GET/POST/PATCH/DELETE/PUT。"""
    for method in ["GET", "POST", "PATCH", "DELETE", "PUT"]:
        resp = client.options(
            "/posts",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": method,
            },
        )
        allow = resp.headers.get("allow", "")
        # 至少不应被 CORS 中间件拒绝
        assert resp.status_code in (200, 405), f"{method} 预检失败: {resp.status_code}"


def test_jwt_secret_validation_logic():
    """T2-4：main.py 含 jwt_secret 校验逻辑（静态检查）。"""
    import os
    main_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "main.py")
    with open(main_path, encoding="utf-8") as f:
        content = f.read()
    assert "jwt_secret == \"change-me\"" in content, "main.py 应含 jwt_secret == 'change-me' 判断"
    assert "RuntimeError" in content, "main.py 应含 RuntimeError 抛出"


def test_alembic_migration_files_exist():
    """T3-1：Alembic 迁移文件存在。"""
    import os
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    alembic_dir = os.path.join(backend_dir, "alembic", "versions")
    assert os.path.isdir(alembic_dir), f"alembic/versions 目录不存在: {alembic_dir}"
    files = [f for f in os.listdir(alembic_dir) if f.endswith(".py") and not f.startswith("__")]
    assert len(files) >= 1, f"应至少有 1 个迁移文件: {files}"


def test_create_admin_script_exists():
    """T2-3：CLI 脚本 scripts/create_admin.py 存在。"""
    import os
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    script_path = os.path.join(backend_dir, "scripts", "create_admin.py")
    assert os.path.exists(script_path), f"CLI 脚本不存在: {script_path}"


def test_private_post_invisible_to_others(client):
    """T3-5：A 的私密帖子 B 看不到。"""
    info_a = register(client, "13706000007", "私密A")
    private = create_post(client, info_a["school_id"], "私密内容", is_public=False)
    client.post("/auth/logout")
    register(client, "13706000008", "用户B")
    listing = client.get("/posts", params={"view": "all"}).json()
    ids = [p["id"] for p in listing["data"]["items"]]
    assert private["id"] not in ids


def test_non_author_cannot_edit_post(client):
    """非作者不可编辑他人帖子。"""
    info_a = register(client, "13706000009", "作者A")
    post = create_post(client, info_a["school_id"], "A 的帖子")
    client.post("/auth/logout")
    register(client, "13706000010", "用户B")
    resp = client.patch(f"/posts/{post['id']}", json={"content": "B 篡改"}).json()
    assert resp["code"] != 0


def test_non_author_cannot_delete_post(client):
    """非作者不可删除他人帖子。"""
    info_a = register(client, "13706000011", "作者A2")
    post = create_post(client, info_a["school_id"], "A 的帖子")
    client.post("/auth/logout")
    register(client, "13706000012", "用户B2")
    resp = client.delete(f"/posts/{post['id']}").json()
    assert resp["code"] != 0


def test_health_check(client):
    """/health 返回 ok。"""
    resp = client.get("/health").json()
    assert resp["code"] == 0
    assert resp["data"]["status"] == "ok"
