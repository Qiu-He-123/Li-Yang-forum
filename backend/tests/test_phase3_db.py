"""阶段 3 数据库整改验证脚本。

T3-4: like_count 一致性 - 重复点赞后 count 不变
T3-5: is_public=false 过滤 - A 的私密帖子 B 看不到
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_TIMEOUT_SECONDS"] = "1"

from fastapi.testclient import TestClient

from app.main import app


def _register(client: TestClient, phone: str, nickname: str) -> dict:
    schools = client.get("/schools").json()["data"]
    school_id = schools[0]["id"]
    body = {
        "nickname": nickname,
        "phone": phone,
        "code": "123456",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": school_id,
        "agreed": True,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == 0, f"register failed: {resp}"
    return {"school_id": school_id, "user_id": resp["data"]["user_id"]}


def _create_post(client: TestClient, school_id: int, content: str, is_public: bool) -> dict:
    body = {
        "content": content,
        "school_id": school_id,
        "category": "普通",
        "image_urls": [],
        "is_anonymous": False,
        "is_public": is_public,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] == 0, f"create post failed: {resp}"
    return resp["data"]


def test_t3_4_like_count_consistency():
    """T3-4：连续点赞同一帖子 2 次，第二次返回的 like_count 与第一次相同。"""
    with TestClient(app) as client:
        info = _register(client, "13700110001", "T34点赞员")
        post = _create_post(client, info["school_id"], "T3-4 测试帖子", is_public=True)
        post_id = post["id"]

        # 第一次点赞
        r1 = client.post(f"/likes/post/{post_id}").json()
        assert r1["code"] == 0, f"first like failed: {r1}"
        count1 = r1["data"]["like_count"]
        assert count1 == 1, f"first like count should be 1, got {count1}"

        # 第二次点赞（重复）应返回相同 count
        r2 = client.post(f"/likes/post/{post_id}").json()
        assert r2["code"] == 0, f"second like failed: {r2}"
        count2 = r2["data"]["like_count"]
        assert count2 == count1, f"repeat like count changed: {count1} -> {count2}"

        # 取消点赞后 count -1
        r3 = client.delete(f"/likes/post/{post_id}").json()
        assert r3["code"] == 0, f"unlike failed: {r3}"
        count3 = r3["data"]["like_count"]
        assert count3 == 0, f"after unlike count should be 0, got {count3}"

        # 再次取消点赞（重复取消）count 不变
        r4 = client.delete(f"/likes/post/{post_id}").json()
        assert r4["code"] == 0, f"repeat unlike failed: {r4}"
        count4 = r4["data"]["like_count"]
        assert count4 == 0, f"repeat unlike count changed: 0 -> {count4}"

        print(f"✅ T3-4 like_count 一致性：first={count1}, repeat={count2}, unlike={count3}, repeat_unlike={count4}")


def test_t3_5_is_public_filter():
    """T3-5：A 的私密帖子 B 看不到，A 自己能看到。"""
    with TestClient(app) as client:
        # 注册 A 并发私密帖子
        info_a = _register(client, "13700110002", "T35用户A")
        post_a = _create_post(client, info_a["school_id"], "A 的私密帖子内容", is_public=False)
        private_post_id = post_a["id"]

        # A 自己能看到自己的私密帖子
        list_as_a = client.get("/posts", params={"view": "all"}).json()
        assert list_as_a["code"] == 0
        # T4-11：list_posts 返回 {items, total, page, page_size}，不再是裸数组
        ids_a = [p["id"] for p in list_as_a["data"]["items"]]
        assert private_post_id in ids_a, f"A 看不到自己的私密帖子: {ids_a}"

        # 登出 A
        client.post("/auth/logout")

        # 注册 B
        info_b = _register(client, "13700110003", "T35用户B")
        # 注意 B 注册后系统会自动登录 B（同一 session）

        # B 看不到 A 的私密帖子
        list_as_b = client.get("/posts", params={"view": "all"}).json()
        assert list_as_b["code"] == 0
        ids_b = [p["id"] for p in list_as_b["data"]["items"]]
        assert private_post_id not in ids_b, f"B 不应该看到 A 的私密帖子，但看到了: {ids_b}"

        # B 发公开帖子，A 重新登录后能看到
        post_b = _create_post(client, info_b["school_id"], "B 的公开帖子", is_public=True)
        public_post_id = post_b["id"]

        # B 登出
        client.post("/auth/logout")

        # A 重新登录
        login_a = client.post("/auth/login", json={"phone": "13700110002", "password": "Pwd@2026"}).json()
        assert login_a["code"] == 0, f"A login failed: {login_a}"

        list_as_a_again = client.get("/posts", params={"view": "all"}).json()
        ids_a_again = [p["id"] for p in list_as_a_again["data"]["items"]]
        assert public_post_id in ids_a_again, f"A 看不到 B 的公开帖子: {ids_a_again}"
        assert private_post_id in ids_a_again, f"A 看不到自己的私密帖子: {ids_a_again}"

        print(f"✅ T3-5 is_public 过滤：A 私密帖子={private_post_id} (A可见, B不可见), B 公开帖子={public_post_id} (A可见)")


if __name__ == "__main__":
    test_t3_4_like_count_consistency()
    test_t3_5_is_public_filter()
    print("\n🎉 阶段 3 数据库整改验证全部通过")
