"""通知生命周期回归测试。

背景（用户反馈）：评论被删除（或帖子被删除）后，
被评论人/被回复人的消息列表里仍能看到该评论的通知。

修复：
1. "收到评论"通知改为关联评论（reference_type=comment, reference_id=comment.id）
2. 删除评论时同步清理关联通知（含级联删除的子回复）
3. 删除帖子时同步清理帖子及其评论的关联通知
4. 消息列表/未读数读取前懒清理指向已删除内容的旧通知
"""
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Comment, Notification
from tests.conftest import approve_comment, create_post, register


def test_comment_delete_cleans_notifications(client):
    """删除评论后，关联该评论的通知（收到评论/审核通知）全部清理。"""
    author = register(client, "nf00000001", "通知作者A")
    post = create_post(client, author["school_id"], "评论通知清理测试帖")

    # 评论者 B 发评论（测试环境 AI 关闭 → 评论转人工审核）
    client.post("/auth/logout")
    register(client, "nf00000002", "评论者B")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "待清理的评论内容"}).json()
    assert c["code"] == 0
    cid = c["data"]["id"]
    approve_comment(client, cid)

    with SessionLocal() as db:
        before = db.scalars(
            select(Notification).where(
                Notification.reference_type == "comment",
                Notification.reference_id == cid,
            )
        ).all()
        assert before, "审核通过后应存在关联该评论的通知"

    # B 删除自己的评论
    resp = client.delete(f"/posts/{post['id']}/comments/{cid}").json()
    assert resp["code"] == 0

    with SessionLocal() as db:
        after = db.scalars(
            select(Notification).where(
                Notification.reference_type == "comment",
                Notification.reference_id == cid,
            )
        ).all()
        assert not after, "删除评论后关联通知应被清理"


def test_comment_delete_cleans_reply_notifications(client):
    """级联删除子回复时，子回复的通知也一并清理。"""
    author = register(client, "nf00000003", "回复通知作者A")
    post = create_post(client, author["school_id"], "回复通知清理测试帖")

    client.post("/auth/logout")
    register(client, "nf00000004", "回复者B")
    root = client.post(f"/posts/{post['id']}/comments", json={"content": "一级评论"}).json()
    root_id = root["data"]["id"]
    reply = client.post(
        f"/posts/{post['id']}/comments",
        json={"content": "二级回复", "parent_id": root_id},
    ).json()
    reply_id = reply["data"]["id"]
    approve_comment(client, root_id)
    approve_comment(client, reply_id)

    with SessionLocal() as db:
        before = db.scalars(
            select(Notification).where(
                Notification.reference_type == "comment",
                Notification.reference_id.in_([root_id, reply_id]),
            )
        ).all()
        assert before, "一级评论和二级回复都应有关联通知"

    # 删除一级评论 → 级联删除二级回复
    resp = client.delete(f"/posts/{post['id']}/comments/{root_id}").json()
    assert resp["code"] == 0

    with SessionLocal() as db:
        after = db.scalars(
            select(Notification).where(
                Notification.reference_type == "comment",
                Notification.reference_id.in_([root_id, reply_id]),
            )
        ).all()
        assert not after, "级联删除后一级评论与子回复的通知都应被清理"


def test_post_delete_cleans_comment_notifications(client):
    """删除帖子后，帖子及其评论的关联通知全部清理。"""
    author = register(client, "nf00000005", "删帖作者A")
    post = create_post(client, author["school_id"], "删帖清理测试帖")

    client.post("/auth/logout")
    register(client, "nf00000006", "删帖评论者B")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "要清理的评论"}).json()
    cid = c["data"]["id"]
    approve_comment(client, cid)

    with SessionLocal() as db:
        comment_ids = list(db.scalars(select(Comment.id).where(Comment.post_id == post["id"])).all())
        assert comment_ids
        notif_count = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.reference_type == "comment",
                Notification.reference_id.in_(comment_ids),
            )
        ) or 0
        assert notif_count > 0

    # 作者登录删帖
    client.post("/auth/logout")
    resp = client.post("/auth/login", json={"username": "nf00000005", "password": "Pwd@2026"}).json()
    assert resp["code"] == 0
    resp = client.delete(f"/posts/{post['id']}").json()
    assert resp["code"] == 0

    with SessionLocal() as db:
        remaining = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.reference_type == "comment",
                Notification.reference_id.in_(comment_ids),
            )
        ) or 0
        assert remaining == 0, "删除帖子后评论关联通知应被清理"
        stale_post = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.reference_type == "post",
                Notification.reference_id == post["id"],
                Notification.type != "system",
            )
        ) or 0
        assert stale_post == 0, "删除帖子后非系统关联通知应被清理"


def test_list_notifications_cleans_stale_refs(client):
    """消息列表读取前懒清理指向已删除内容的旧通知。"""
    info = register(client, "nf00000007", "脏数据清理员")
    with SessionLocal() as db:
        stale = Notification(
            user_id=info["user_id"],
            title="已删帖子的点赞",
            content="有人赞了你的帖子",
            type="like",
            reference_type="post",
            reference_id=999999,
        )
        db.add(stale)
        db.commit()
        stale_id = stale.id

    resp = client.get("/notifications").json()
    assert resp["code"] == 0
    ids = [item["id"] for item in resp["data"]["items"]]
    assert stale_id not in ids, "指向已删除帖子的旧通知不应再出现在消息列表"

    with SessionLocal() as db:
        assert db.get(Notification, stale_id) is None, "懒清理应删除脏通知记录"
