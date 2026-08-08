"""T9-1 互动模块回归测试。

覆盖：
- 帖子点赞 / 取消点赞
- 评论点赞 / 取消点赞
- 帖子收藏 / 取消收藏
- 举报（带具体理由）
- like_count 一致性（T3-4 重复点赞不重复 +1）
- favorite 幂等
- 「我的收藏」列表
- 「我的点赞」列表
"""
import pytest

from tests.conftest import create_post, register


def test_like_post_success(client):
    """点赞帖子成功 + like_count=1。"""
    info = register(client, "13703000001", "点赞员")
    post = create_post(client, info["school_id"], "点赞测试帖")
    resp = client.post(f"/likes/post/{post['id']}").json()
    assert resp["code"] == 0
    assert resp["data"]["like_count"] == 1


def test_unlike_post_success(client):
    """取消点赞成功 + like_count=0。"""
    info = register(client, "13703000002", "取消赞员")
    post = create_post(client, info["school_id"], "取消赞测试帖")
    client.post(f"/likes/post/{post['id']}")
    resp = client.delete(f"/likes/post/{post['id']}").json()
    assert resp["code"] == 0
    assert resp["data"]["like_count"] == 0


def test_like_count_consistency_on_duplicate(client):
    """T3-4：重复点赞后 like_count 不变。"""
    info = register(client, "13703000003", "重复赞员")
    post = create_post(client, info["school_id"], "重复赞测试帖")
    r1 = client.post(f"/likes/post/{post['id']}").json()
    r2 = client.post(f"/likes/post/{post['id']}").json()
    assert r1["data"]["like_count"] == r2["data"]["like_count"] == 1


def test_unlike_idempotent(client):
    """重复取消点赞不会变成负数。"""
    info = register(client, "13703000004", "重复取消员")
    post = create_post(client, info["school_id"], "重复取消测试帖")
    client.post(f"/likes/post/{post['id']}")
    client.delete(f"/likes/post/{post['id']}")
    r = client.delete(f"/likes/post/{post['id']}").json()
    assert r["code"] == 0
    assert r["data"]["like_count"] == 0


def test_like_comment_success(client):
    """评论点赞成功。"""
    info = register(client, "13703000005", "评赞员")
    post = create_post(client, info["school_id"], "评赞测试帖")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "评论"}).json()
    cid = c["data"]["id"]
    resp = client.post(f"/likes/comment/{cid}").json()
    assert resp["code"] == 0
    assert resp["data"]["like_count"] == 1


def test_unlike_comment_success(client):
    """取消评论点赞。"""
    info = register(client, "13703000006", "取消评赞员")
    post = create_post(client, info["school_id"], "取消评赞测试帖")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "评论"}).json()
    cid = c["data"]["id"]
    client.post(f"/likes/comment/{cid}")
    resp = client.delete(f"/likes/comment/{cid}").json()
    assert resp["code"] == 0
    assert resp["data"]["like_count"] == 0


def test_favorite_post_success(client):
    """收藏帖子成功。"""
    info = register(client, "13703000007", "收藏员")
    post = create_post(client, info["school_id"], "收藏测试帖")
    resp = client.post(f"/favorites/{post['id']}").json()
    assert resp["code"] == 0


def test_unfavorite_post_success(client):
    """取消收藏成功。"""
    info = register(client, "13703000008", "取消收藏员")
    post = create_post(client, info["school_id"], "取消收藏测试帖")
    client.post(f"/favorites/{post['id']}")
    resp = client.delete(f"/favorites/{post['id']}").json()
    assert resp["code"] == 0


def test_favorite_idempotent(client):
    """重复收藏应幂等（不报错，不重复 +1）。"""
    info = register(client, "13703000009", "重复收藏员")
    post = create_post(client, info["school_id"], "重复收藏测试帖")
    r1 = client.post(f"/favorites/{post['id']}").json()
    r2 = client.post(f"/favorites/{post['id']}").json()
    assert r1["code"] == 0
    assert r2["code"] == 0


def test_my_favorites_list(client):
    """「我的收藏」列表含已收藏的帖子。"""
    info = register(client, "13703000010", "我的收藏员")
    post = create_post(client, info["school_id"], "我的收藏测试帖")
    client.post(f"/favorites/{post['id']}")
    # /users/me/favorites 返回 {post_ids: [...]}（active 态回填用）
    # /users/me/favorites/posts 返回完整帖子列表（T5-4 我的收藏页用）
    resp = client.get("/users/me/favorites/posts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]["items"]]
    assert post["id"] in ids


def test_my_favorites_excludes_unfavorited(client):
    """取消收藏后从「我的收藏」列表消失。"""
    info = register(client, "13703000011", "取消后列表员")
    post = create_post(client, info["school_id"], "取消后列表测试帖")
    client.post(f"/favorites/{post['id']}")
    client.delete(f"/favorites/{post['id']}")
    resp = client.get("/users/me/favorites/posts").json()
    ids = [p["id"] for p in resp["data"]["items"]]
    assert post["id"] not in ids


def test_my_liked_posts_list(client):
    """「我的点赞」列表含已点赞的帖子。"""
    info = register(client, "13703000012", "我的点赞员")
    post = create_post(client, info["school_id"], "我的点赞测试帖")
    client.post(f"/likes/post/{post['id']}")
    # /users/me/likes/posts 返回完整帖子列表（T5-1 点赞 Tab 用）
    resp = client.get("/users/me/likes/posts").json()
    assert resp["code"] == 0
    ids = [p["id"] for p in resp["data"]["items"]]
    assert post["id"] in ids


def test_report_with_reason(client):
    """举报带具体理由。"""
    info = register(client, "13703000013", "举报员")
    post = create_post(client, info["school_id"], "举报测试帖")
    resp = client.post(
        "/reports",
        json={
            "target_type": "post",
            "target_id": post["id"],
            "reason": "[垃圾广告] T9-1 测试举报理由",
        },
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["status"] == "pending"


def test_report_rejects_empty_reason(client):
    """举报理由为空时失败。"""
    info = register(client, "13703000014", "空举报员")
    post = create_post(client, info["school_id"], "空举报测试帖")
    resp = client.post(
        "/reports",
        json={"target_type": "post", "target_id": post["id"], "reason": ""},
    ).json()
    assert resp["code"] != 0


def test_like_post_rejects_unauthenticated(client):
    """未登录点赞返回 -100。"""
    schools = client.get("/schools").json()["data"]
    # 直接尝试点赞不存在的帖子，应先返回 -100
    resp = client.post("/likes/post/99999").json()
    assert resp["code"] == -100


def test_favorite_post_rejects_unauthenticated(client):
    """未登录收藏返回 -100。"""
    resp = client.post("/favorites/99999").json()
    assert resp["code"] == -100
