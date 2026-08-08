"""T9-1 用户模块回归测试。

覆盖：
- /users/me 个人主页（profile）
- PATCH /users/me 编辑资料（昵称 / 头像 / 背景 / 简介）
- GET /users/{id} 他人主页
- GET /users/{id}/posts 他人帖子列表
- GET /users/me/drafts 我的草稿
- GET /users/me/favorites 我的收藏
- GET /users/me/likes 我的点赞
- profile 字段完整（uid / nickname / school / post_count / like_count）
"""
import pytest

from tests.conftest import create_post, register


def test_users_me_returns_profile(client):
    """/users/me 返回完整 profile 字段。"""
    info = register(client, "13704000001", "个人主页员")
    resp = client.get("/users/me").json()
    assert resp["code"] == 0
    p = resp["data"]
    assert p["id"] == info["user_id"]
    assert p["nickname"] == "个人主页员"
    assert "uid" in p
    assert "school" in p
    assert "post_count" in p
    assert "like_count" in p
    assert p["uid"].startswith("LY")


def test_update_me_nickname(client):
    """PATCH /users/me 修改昵称。"""
    register(client, "13704000002", "原名")
    resp = client.patch("/users/me", json={"nickname": "新昵称"}).json()
    assert resp["code"] == 0
    assert resp["data"]["nickname"] == "新昵称"
    # 二次校验
    me = client.get("/users/me").json()
    assert me["data"]["nickname"] == "新昵称"


def test_update_me_avatar_and_bio(client):
    """PATCH /users/me 修改头像 URL 和简介。"""
    register(client, "13704000003", "头像员")
    resp = client.patch(
        "/users/me",
        json={
            "avatar_url": "https://example.com/avatar.png",
            "bio": "T9-1 测试简介",
        },
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["avatar_url"] == "https://example.com/avatar.png"
    assert resp["data"]["bio"] == "T9-1 测试简介"


def test_get_user_by_id(client):
    """GET /users/{id} 返回该用户公开资料。"""
    info = register(client, "13704000004", "被查看员")
    resp = client.get(f"/users/{info['user_id']}").json()
    assert resp["code"] == 0
    assert resp["data"]["id"] == info["user_id"]
    assert resp["data"]["nickname"] == "被查看员"


def test_get_user_posts(client):
    """GET /users/{id}/posts 返回该用户的帖子列表。"""
    info = register(client, "13704000005", "帖子员")
    p1 = create_post(client, info["school_id"], "帖子 1")
    p2 = create_post(client, info["school_id"], "帖子 2")
    resp = client.get(f"/users/{info['user_id']}/posts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]["items"]]
    assert p1["id"] in ids
    assert p2["id"] in ids


def test_my_drafts_list(client):
    """GET /users/me/drafts 返回当前用户的草稿。"""
    info = register(client, "13704000006", "草稿员")
    d1 = create_post(client, info["school_id"], "草稿 1", is_draft=True)
    d2 = create_post(client, info["school_id"], "草稿 2", is_draft=True)
    create_post(client, info["school_id"], "公开帖子")  # 不应在草稿列表
    resp = client.get("/users/me/drafts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]]
    assert d1["id"] in ids
    assert d2["id"] in ids
    assert len(ids) == 2


def test_my_favorites_list(client):
    """GET /users/me/favorites/posts 返回当前用户的收藏（完整帖子列表）。"""
    info = register(client, "13704000007", "收藏员")
    post = create_post(client, info["school_id"], "收藏测试帖")
    client.post(f"/favorites/{post['id']}")
    # /users/me/favorites 仅返回 {post_ids: [...]}（active 态回填）
    # /users/me/favorites/posts 返回完整帖子列表（T5-4 我的收藏页用）
    resp = client.get("/users/me/favorites/posts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]["items"]]
    assert post["id"] in ids


def test_my_likes_list(client):
    """GET /users/me/likes/posts 返回当前用户点赞的帖子（完整列表）。"""
    info = register(client, "13704000008", "点赞员")
    post = create_post(client, info["school_id"], "点赞测试帖")
    client.post(f"/likes/post/{post['id']}")
    resp = client.get("/users/me/likes/posts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]["items"]]
    assert post["id"] in ids


def test_users_me_rejects_unauthenticated(client):
    """未登录访问 /users/me 返回 -100。"""
    resp = client.get("/users/me").json()
    assert resp["code"] == -100


def test_profile_post_count_increments(client):
    """发帖后 post_count +1。"""
    info = register(client, "13704000009", "计数员")
    before = client.get("/users/me").json()["data"]["post_count"]
    create_post(client, info["school_id"], "新帖子")
    after = client.get("/users/me").json()["data"]["post_count"]
    assert after == before + 1


def test_profile_like_count_aggregates(client):
    """like_count 是该用户所有帖子获赞总数。"""
    info_a = register(client, "13704000010", "作者A")
    post = create_post(client, info_a["school_id"], "获赞帖")
    # 登出 A，注册 B，B 点赞 A 的帖子
    client.post("/auth/logout")
    register(client, "13704000011", "点赞B")
    client.post(f"/likes/post/{post['id']}")
    # 登出 B，A 重新登录
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "13704000010", "password": "Pwd@2026"})
    me = client.get("/users/me").json()["data"]
    assert me["like_count"] >= 1, f"A 应至少有 1 个获赞，实际 {me['like_count']}"
