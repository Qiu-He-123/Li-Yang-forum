"""管理端默认好友：所有用户默认与该用户互相关注，且不可取关。"""

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, Follow, User
from app.services import follow_service, message_service, settings_service
from tests.conftest import register

ADMIN_USER = "t9_default_friend_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == ADMIN_USER).first():
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _set_default_friend(client, user_id: int) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"
    resp = client.put("/admin/settings", json={"settings": {"default_friend_user_id": str(user_id)}}).json()
    assert resp["code"] == 0, resp


def test_default_friend_mutual_and_locked(client):
    a = register(client, "df_user_a")
    b = register(client, "df_user_b")
    _set_default_friend(client, b["user_id"])
    try:
        with SessionLocal() as db:
            ua = db.get(User, a["user_id"])
            ub = db.get(User, b["user_id"])

            # 双方视角都是互相关注（无需真实 Follow 记录）
            status_a = follow_service.is_following(db, ua, ub.id)
            assert status_a["is_following"] and status_a["is_mutual"]
            status_b = follow_service.is_following(db, ub, ua.id)
            assert status_b["is_following"] and status_b["is_mutual"]
            assert follow_service.is_mutual_follow(db, ua.id, ub.id)

            # 关注默认好友是幂等空操作，不落库
            follow_service.follow_user(db, ua, ub.id)
            row_count = db.scalar(
                select(func.count(Follow.id)).where(
                    Follow.follower_id == ua.id, Follow.followee_id == ub.id
                )
            ) or 0
            assert row_count == 0

            # 不可取关默认好友
            with pytest.raises(HTTPException) as exc:
                follow_service.unfollow_user(db, ua, ub.id)
            assert exc.value.status_code == 400
            assert "默认好友" in exc.value.detail

            # 好友列表 / 消息栏置顶显示默认好友（无需真实好友或消息记录）
            friends = message_service.list_friends(db, ua)
            assert friends and friends[0]["user"]["id"] == ub.id
            convs = message_service.list_conversations(db, ua)
            assert convs and convs[0]["user"]["id"] == ub.id
    finally:
        with SessionLocal() as db:
            settings_service.set_setting(db, "default_friend_user_id", "")

    # 关闭配置后不再出现（后续修改即时生效）
    with SessionLocal() as db:
        ua = db.get(User, a["user_id"])
        assert message_service.list_friends(db, ua) == []
        assert message_service.list_conversations(db, ua) == []
