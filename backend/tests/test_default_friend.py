"""管理端默认好友：所有用户默认与这些用户互相关注，且不可取关（支持多人）。"""

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


def _set_default_friends(client, *user_ids: int) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"
    value = ",".join(str(uid) for uid in user_ids)
    resp = client.put("/admin/settings", json={"settings": {"default_friend_user_ids": value}}).json()
    assert resp["code"] == 0, resp


def _reset_default_friends() -> None:
    with SessionLocal() as db:
        settings_service.set_setting(db, "default_friend_user_ids", "")
        settings_service.set_setting(db, "default_friend_user_id", "")


def test_default_friend_mutual_and_locked(client):
    a = register(client, "df_user_a")
    b = register(client, "df_user_b")
    _set_default_friends(client, b["user_id"])
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
            assert friends[0]["last_message"] == "默认好友（官方账号）"
            convs = message_service.list_conversations(db, ua)
            assert convs and convs[0]["user"]["id"] == ub.id
            assert convs[0]["last_message"] == "默认好友（官方账号）"
    finally:
        _reset_default_friends()

    # 关闭配置后不再出现（后续修改即时生效）
    with SessionLocal() as db:
        ua = db.get(User, a["user_id"])
        assert message_service.list_friends(db, ua) == []
        assert message_service.list_conversations(db, ua) == []


def test_multiple_default_friends_pinned_in_order(client):
    """配置多个默认好友：全部置顶、顺序保持配置顺序、互关且不可取关。"""
    a = register(client, "df_multi_a")
    b = register(client, "df_multi_b")
    c = register(client, "df_multi_c")
    _set_default_friends(client, b["user_id"], c["user_id"])
    try:
        with SessionLocal() as db:
            ua = db.get(User, a["user_id"])
            ub = db.get(User, b["user_id"])
            uc = db.get(User, c["user_id"])

            # 与每个默认好友都隐式互关
            for df in (ub, uc):
                assert follow_service.is_mutual_follow(db, ua.id, df.id)
                assert follow_service.is_following(db, ua, df.id)["is_mutual"]

            # 好友列表 / 会话列表按配置顺序置顶
            friends = message_service.list_friends(db, ua)
            assert [f["user"]["id"] for f in friends[:2]] == [ub.id, uc.id]
            assert all(f["last_message"] == "默认好友（官方账号）" for f in friends[:2])
            convs = message_service.list_conversations(db, ua)
            assert [c_["user"]["id"] for c_ in convs[:2]] == [ub.id, uc.id]
            assert all(c_["is_mutual"] for c_ in convs[:2])

            # 关注任一默认好友是幂等空操作，不落库
            follow_service.follow_user(db, ua, ub.id)
            row_count = db.scalar(
                select(func.count(Follow.id)).where(
                    Follow.follower_id == ua.id, Follow.followee_id == ub.id
                )
            ) or 0
            assert row_count == 0

            # 不可取关任一默认好友
            for df in (ub, uc):
                with pytest.raises(HTTPException) as exc:
                    follow_service.unfollow_user(db, ua, df.id)
                assert exc.value.status_code == 400
                assert "默认好友" in exc.value.detail
    finally:
        _reset_default_friends()


def test_legacy_single_default_friend_still_works(client):
    """旧配置 default_friend_user_id（单个 ID）仍兼容。"""
    a = register(client, "df_legacy_a")
    b = register(client, "df_legacy_b")
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0
    resp = client.put("/admin/settings", json={"settings": {"default_friend_user_id": str(b["user_id"])}}).json()
    assert resp["code"] == 0, resp
    try:
        with SessionLocal() as db:
            ua = db.get(User, a["user_id"])
            ub = db.get(User, b["user_id"])
            assert follow_service.is_mutual_follow(db, ua.id, ub.id)
            friends = message_service.list_friends(db, ua)
            assert friends and friends[0]["user"]["id"] == ub.id
            payload = message_service.get_messages(db, ua, ub.id)
            assert payload["is_default_friend"] is True
    finally:
        _reset_default_friends()


def test_default_friend_conversation_shows_real_message(client):
    """默认好友发来真实消息后：消息列表显示最后一条消息与未读数，而非占位文案。"""
    from app.services import user_service

    a = register(client, "df_msg_a")
    b = register(client, "df_msg_b")
    _set_default_friends(client, b["user_id"])
    try:
        with SessionLocal() as db:
            ua = db.get(User, a["user_id"])
            ub = db.get(User, b["user_id"])
            # 官号 B 给 A 发一条真实消息
            message_service.send_message(db, ub, ua.id, "你好呀，这是官方消息")

            convs = message_service.list_conversations(db, ua)
            assert convs and convs[0]["user"]["id"] == ub.id
            assert convs[0]["last_message"] == "你好呀，这是官方消息"
            assert convs[0]["unread_count"] == 1

            friends = message_service.list_friends(db, ua)
            assert friends and friends[0]["user"]["id"] == ub.id
            assert friends[0]["last_message"] == "你好呀，这是官方消息"

            # 聊天记录与资料接口都标记为默认好友（官方账号）
            payload = message_service.get_messages(db, ua, ub.id)
            assert payload["is_default_friend"] is True
            profile = user_service.get_user(ub.id, db, viewer=ua)
            assert profile["is_default_friend"] is True
    finally:
        _reset_default_friends()
