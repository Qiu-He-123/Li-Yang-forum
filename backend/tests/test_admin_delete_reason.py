"""人工删除帖子：必须填写删除理由，并向作者发送系统消息。"""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, Notification, Post
from tests.conftest import create_post, register

ADMIN_USER = "t9_delete_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == ADMIN_USER).first():
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _admin_login(client) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"


def test_admin_delete_post_requires_reason_and_notifies_author(client):
    info = register(client, "del_reason_user")
    post = create_post(client, info["school_id"], "这是一条会被管理员删除的测试帖子，内容足够长")
    post_id = post["id"]
    _admin_login(client)

    # 空理由被拒绝
    resp = client.post(f"/admin/posts/{post_id}/delete", json={"reason": "  "}).json()
    assert resp["code"] != 0
    assert "理由" in resp["msg"]

    # 带理由删除成功
    resp = client.post(f"/admin/posts/{post_id}/delete", json={"reason": "广告推广"}).json()
    assert resp["code"] == 0, resp

    # 帖子已删除
    detail = client.get(f"/posts/{post_id}").json()
    assert detail["code"] != 0

    # 作者收到系统通知，且包含删除理由
    with SessionLocal() as db:
        notif = db.scalar(
            select(Notification).where(
                Notification.user_id == info["user_id"],
                Notification.type == "system",
                Notification.title == "帖子已被删除",
            )
        )
        assert notif is not None, "作者未收到删除通知"
        assert "广告推广" in notif.content
        assert db.get(Post, post_id) is None
