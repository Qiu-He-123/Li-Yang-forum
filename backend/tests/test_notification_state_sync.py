"""消息列表「有什么显示什么」状态同步回归测试。

背景（用户反馈修正）：消息页不是去重合并，而是实时反映真实互动状态：
- 对方点赞了 → 列表出现一条「收到点赞」；对方取消点赞 → 这条立即消失
- 对方评论了 → 列表出现一条「收到评论」；评论被删除 → 这条立即消失
- 再次点赞/评论 → 重新生成一条（已读未读不影响「取消即消失」）
- 收藏同理

配套能力：
- 懒清理：历史遗留的重复「收到点赞」脏数据（旧版取消不删通知产生）
  在读取列表时按「一条互动状态 = 一条通知」修复，避免重复展示
"""
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Notification
from tests.conftest import approve_comment, create_post, register


def _login(client, username: str) -> None:
    resp = client.post("/auth/login", json={"username": username, "password": "Pwd@2026"}).json()
    assert resp["code"] == 0, resp


def _logout(client) -> None:
    client.post("/auth/logout")


def _like_notifications(client) -> list[dict]:
    resp = client.get("/notifications", params={"type": "like"}).json()
    assert resp["code"] == 0, resp
    return resp["data"]["items"]


def test_like_then_unlike_removes_notification(client):
    """点赞 → 作者看到 1 条；取消点赞 → 这条立即消失。"""
    author = register(client, "ns00000001", "状态作者A")
    post = create_post(client, author["school_id"], "点赞状态同步测试帖")

    _logout(client)
    register(client, "ns00000002", "点赞者B")
    like = client.post(f"/likes/post/{post['id']}").json()
    assert like["code"] == 0, like

    _logout(client)
    _login(client, "ns00000001")
    items = _like_notifications(client)
    assert len(items) == 1, "点赞后作者应看到 1 条点赞通知"
    assert items[0]["is_read"] is False

    # B 取消点赞 → 通知立即消失
    _logout(client)
    _login(client, "ns00000002")
    unlike = client.delete(f"/likes/post/{post['id']}").json()
    assert unlike["code"] == 0, unlike

    _logout(client)
    _login(client, "ns00000001")
    assert _like_notifications(client) == [], "取消点赞后通知应消失"


def test_relike_recreates_notification(client):
    """取消后再点赞 → 重新生成一条（不多不少）。"""
    author = register(client, "ns00000003", "状态作者C")
    post = create_post(client, author["school_id"], "重新点赞状态同步测试帖")

    _logout(client)
    register(client, "ns00000004", "点赞者D")
    client.post(f"/likes/post/{post['id']}").json()
    client.delete(f"/likes/post/{post['id']}").json()
    client.post(f"/likes/post/{post['id']}").json()

    _logout(client)
    _login(client, "ns00000003")
    items = _like_notifications(client)
    assert len(items) == 1, "再次点赞应恰好 1 条通知，无重复"


def test_unlike_removes_even_read_notification(client):
    """已读后再取消点赞：通知同样消失（互动状态没了，消息就没有了）。"""
    author = register(client, "ns00000005", "状态作者E")
    post = create_post(client, author["school_id"], "已读后取消状态同步测试帖")

    _logout(client)
    register(client, "ns00000006", "点赞者F")
    client.post(f"/likes/post/{post['id']}").json()

    # 作者已读这条点赞
    _logout(client)
    _login(client, "ns00000005")
    items = _like_notifications(client)
    assert len(items) == 1
    read = client.patch(f"/notifications/{items[0]['id']}/read").json()
    assert read["code"] == 0, read

    # F 取消点赞 → 已读的这条通知也删除
    _logout(client)
    _login(client, "ns00000006")
    client.delete(f"/likes/post/{post['id']}").json()

    _logout(client)
    _login(client, "ns00000005")
    assert _like_notifications(client) == [], "已读通知在互动消失后也应删除"


def test_comment_then_delete_removes_notification(client):
    """评论 → 作者看到 1 条；评论被删除 → 这条立即消失。"""
    author = register(client, "ns00000007", "状态作者G")
    post = create_post(client, author["school_id"], "评论状态同步测试帖")

    _logout(client)
    register(client, "ns00000008", "评论者H")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "状态同步评论内容"}).json()
    assert c["code"] == 0, c
    cid = c["data"]["id"]
    approve_comment(client, cid)

    _logout(client)
    _login(client, "ns00000007")
    items = client.get("/notifications", params={"type": "comment"}).json()["data"]["items"]
    assert len(items) == 1, "评论审核通过后作者应看到 1 条评论通知"

    # 评论者删除评论 → 通知消失
    _logout(client)
    _login(client, "ns00000008")
    resp = client.delete(f"/posts/{post['id']}/comments/{cid}").json()
    assert resp["code"] == 0, resp

    _logout(client)
    _login(client, "ns00000007")
    items = client.get("/notifications", params={"type": "comment"}).json()["data"]["items"]
    assert items == [], "评论删除后通知应消失"


def test_unfavorite_removes_notification(client):
    """收藏 → 作者看到 1 条；取消收藏 → 这条立即消失。"""
    author = register(client, "ns00000009", "状态作者I")
    post = create_post(client, author["school_id"], "收藏状态同步测试帖")

    _logout(client)
    register(client, "ns00000010", "收藏者J")
    fav = client.post(f"/favorites/{post['id']}").json()
    assert fav["code"] == 0, fav

    _logout(client)
    _login(client, "ns00000009")
    items = client.get("/notifications", params={"type": "interaction"}).json()["data"]["items"]
    assert len(items) == 1, "收藏后作者应看到 1 条收藏通知"

    _logout(client)
    _login(client, "ns00000010")
    unfav = client.delete(f"/favorites/{post['id']}").json()
    assert unfav["code"] == 0, unfav

    _logout(client)
    _login(client, "ns00000009")
    items = client.get("/notifications", params={"type": "interaction"}).json()["data"]["items"]
    assert items == [], "取消收藏后通知应消失"


def test_legacy_duplicates_cleaned_on_list(client):
    """懒清理：历史遗留的重复「收到点赞」脏数据读取列表时修复为一条。"""
    info = register(client, "ns00000011", "脏数据清理员K")
    post = create_post(client, info["school_id"], "历史脏数据修复测试帖")
    with SessionLocal() as db:
        for i in range(2):
            db.add(Notification(
                user_id=info["user_id"],
                title="收到点赞",
                content=f"有人赞了你的帖子（第{i}次）",
                type="like",
                sender_id=info["user_id"] + 1,
                reference_type="post",
                reference_id=post["id"],
            ))
        db.commit()

    items = _like_notifications(client)
    assert len(items) == 1, "同一条点赞状态只应显示一条通知"

    with SessionLocal() as db:
        cnt = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == info["user_id"],
                Notification.type == "like",
            )
        ) or 0
        assert cnt == 1, "数据库中的重复通知应被清理"


def test_unread_count_tracks_like_state(client):
    """未读数跟随互动状态：点赞 +1，取消 -1，再点赞 +1。"""
    author = register(client, "ns00000012", "状态作者L")
    post = create_post(client, author["school_id"], "未读状态同步测试帖")

    _logout(client)
    register(client, "ns00000013", "点赞者M")
    client.post(f"/likes/post/{post['id']}").json()

    _logout(client)
    _login(client, "ns00000012")
    data = client.get("/notifications/unread-count").json()["data"]
    assert data["by_type"]["like"] == 1, "点赞后未读点赞数为 1"

    _logout(client)
    _login(client, "ns00000013")
    client.delete(f"/likes/post/{post['id']}").json()

    _logout(client)
    _login(client, "ns00000012")
    data = client.get("/notifications/unread-count").json()["data"]
    assert data["by_type"]["like"] == 0, "取消点赞后未读点赞数为 0"
