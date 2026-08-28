import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_TIMEOUT_SECONDS"] = "1"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_register_login_and_create_post():
    with client:
        schools = client.get("/schools").json()["data"]
        assert len(schools) == 4

        register = client.post(
            "/auth/register",
            json={
                "nickname": "立洋同学",
                "phone": "13800000000",
                "code": "123456",
                "password": "password123",
                "confirm_password": "password123",
                "school_id": schools[0]["id"],
                "agreed": True,
            },
        ).json()
        assert register["code"] == 0

        post = client.post(
            "/posts",
            json={
                "content": "今天社团活动报名开始了。",
                "school_id": schools[0]["id"],
                "category": "活动",
                "image_urls": [],
                "is_anonymous": False,
                "is_public": True,
            },
        ).json()
        assert post["code"] == 0
        assert post["data"]["category"] == "活动"

        listing = client.get("/posts", params={"view": "school"}).json()
        assert listing["code"] == 0
        # T4-11：list_posts 返回 {items, total, page, page_size}，不再是裸数组
        # 注意：in-memory SQLite 在同一 pytest session 中共享，前面测试可能已写入帖子。
        # 只断言当前用户的帖子在列表中，不断言唯一性。
        listing_ids = [p["id"] for p in listing["data"]["items"]]
        assert post["data"]["id"] in listing_ids

        post_id = post["data"]["id"]
        comment = client.post(f"/posts/{post_id}/comments", json={"content": "我也报名。"}).json()
        assert comment["code"] == 0
        assert comment["data"]["content"] == "我也报名。"

        liked = client.post(f"/likes/post/{post_id}").json()
        assert liked["code"] == 0
        assert liked["data"]["like_count"] == 1

        assert client.post(f"/favorites/{post_id}").json()["code"] == 0
        assert client.post("/reports", json={"target_type": "post", "target_id": post_id, "reason": "测试举报"}).json()["code"] == 0

        profile = client.get("/users/me").json()
        assert profile["code"] == 0
        assert profile["data"]["uid"].startswith("LY")


def test_register_rejects_duplicate_phone():
    with client:
        schools = client.get("/schools").json()["data"]
        payload = {
            "nickname": "重复用户",
            "phone": "13900000000",
            "code": "123456",
            "password": "password123",
            "confirm_password": "password123",
            "school_id": schools[0]["id"],
            "agreed": True,
        }
        assert client.post("/auth/register", json=payload).json()["code"] == 0
        # 重复手机号现在返回具体错误码 -202 (PHONE_REGISTERED) 而非通用 1
        second = client.post("/auth/register", json=payload).json()
        assert second["code"] == -202
        assert second["msg"] == "手机号已注册"


def test_validation_error_codes():
    """校验 pydantic 错误能否被映射为具体错误码 + 中文消息。"""
    fresh = TestClient(app)
    with fresh:
        # 缺手机号（LoginIn 要求 phone 必填）
        r = fresh.post("/auth/login", json={"password": "x"}).json()
        assert r["code"] == -1
        assert r["msg"] == "手机号未填写"

        # 注册：缺密码（RegisterIn 要求 password 必填）
        schools = fresh.get("/schools").json()["data"]
        r = fresh.post(
            "/auth/register",
            json={
                "nickname": "测试用户",
                "phone": "13700000000",
                "code": "123456",
                "confirm_password": "password123",
                "school_id": schools[0]["id"],
                "agreed": True,
            },
        ).json()
        assert r["code"] == -3
        assert r["msg"] == "密码未填写"

        # 注册：未勾选协议 -> RegisterIn.agreed 必填，触发 AGREED_NOT_CHECKED
        r = fresh.post(
            "/auth/register",
            json={
                "nickname": "测试用户",
                "phone": "13700000001",
                "code": "123456",
                "password": "password123",
                "confirm_password": "password123",
                "school_id": schools[0]["id"],
            },
        ).json()
        assert r["code"] == -13
        assert r["msg"] == "请先阅读并同意协议"

        # 帖子内容为空 -> CONTENT_EMPTY
        register = fresh.post(
            "/auth/register",
            json={
                "nickname": "测试用户",
                "phone": "13799990002",
                "code": "123456",
                "password": "password123",
                "confirm_password": "password123",
                "school_id": schools[0]["id"],
                "agreed": True,
            },
        ).json()
        assert register["code"] == 0

        # content 是必填字段，pydantic 缺失校验 -> CONTENT_EMPTY
        r = fresh.post("/posts", json={"school_id": schools[0]["id"], "category": "普通"}).json()
        assert r["code"] == -9
        assert r["msg"] == "内容不能为空"


def test_auth_me_endpoint():
    """刷新页面后 /auth/me 用于校验 Cookie 是否仍有效。"""
    fresh = TestClient(app)
    with fresh:
        # 未登录访问 /auth/me 应返回 -100 (NOT_LOGGED_IN)
        r = fresh.get("/auth/me").json()
        assert r["code"] == -100
        assert r["msg"] == "未登录，请先登录"

        # 登录后再访问应返回 user_id
        schools = fresh.get("/schools").json()["data"]
        fresh.post(
            "/auth/register",
            json={
                "nickname": "Me测试",
                "phone": "13600000000",
                "code": "123456",
                "password": "password123",
                "confirm_password": "password123",
                "school_id": schools[0]["id"],
                "agreed": True,
            },
        )
        r = fresh.get("/auth/me").json()
        assert r["code"] == 0
        assert r["data"]["user_id"] > 0
        assert r["data"]["nickname"] == "Me测试"
