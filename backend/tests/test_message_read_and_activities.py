"""私聊已读回执、私聊图片消息、活动板块回归测试。"""

from app.core.database import SessionLocal
from app.models import Activity
from tests.conftest import register


def _make_mutual(client, a_name: str, b_name: str, b_id: int, a_id: int) -> None:
    """让 a、b 互相关注，建立可自由私聊的关系。"""
    client.post("/auth/login", json={"username": a_name, "password": "Pwd@2026"})
    client.post(f"/users/{b_id}/follow")
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": b_name, "password": "Pwd@2026"})
    client.post(f"/users/{a_id}/follow")
    client.post("/auth/logout")


def test_message_read_receipt(client):
    """A 发消息 → B 拉取聊天记录后消息 is_read=True 且 read_at 写入。"""
    a = register(client, "mrr_user_a", "已读测试A")
    b = register(client, "mrr_user_b", "已读测试B")
    _make_mutual(client, "mrr_user_a", "mrr_user_b", b["user_id"], a["user_id"])

    # A 登录发消息给 B
    client.post("/auth/login", json={"username": "mrr_user_a", "password": "Pwd@2026"})
    r = client.post(
        "/messages",
        params={"receiver_id": b["user_id"]},
        json={"content": "你好，这是一条已读测试消息", "msg_type": "text"},
    ).json()
    assert r["code"] == 0, r
    msg_id = r["data"]["id"]
    assert r["data"]["is_read"] is False

    # B 拉取聊天记录 → 消息自动标记已读
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "mrr_user_b", "password": "Pwd@2026"})
    r = client.get(f"/messages/{a['user_id']}").json()
    assert r["code"] == 0, r
    items = r["data"]["items"]
    assert items, "应能拉到消息"
    target = next(m for m in items if m["id"] == msg_id)
    assert target["is_read"] is True
    assert target["read_at"], "已读消息应带 read_at 时间"

    # A 再拉取记录，能看到对方已读
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "mrr_user_a", "password": "Pwd@2026"})
    r = client.get(f"/messages/{b['user_id']}").json()
    target = next(m for m in r["data"]["items"] if m["id"] == msg_id)
    assert target["is_read"] is True
    assert target["read_at"]


def test_send_image_message(client):
    """私聊支持 msg_type=image，内容为图片 URL。"""
    a = register(client, "mim_user_a", "图片测试A")
    b = register(client, "mim_user_b", "图片测试B")
    _make_mutual(client, "mim_user_a", "mim_user_b", b["user_id"], a["user_id"])

    client.post("/auth/login", json={"username": "mim_user_a", "password": "Pwd@2026"})
    r = client.post(
        "/messages",
        params={"receiver_id": b["user_id"]},
        json={"content": "/uploads/test-chat-image.png", "msg_type": "image"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["msg_type"] == "image"
    assert r["data"]["content"] == "/uploads/test-chat-image.png"


def test_send_voice_message_and_upload_audio(client):
    """私聊支持 msg_type=voice；/images/audio 接受音频文件并返回 URL。"""
    a = register(client, "mvm_user_a", "语音测试A")
    b = register(client, "mvm_user_b", "语音测试B")
    _make_mutual(client, "mvm_user_a", "mvm_user_b", b["user_id"], a["user_id"])

    # 上传音频（模拟 MediaRecorder 的 webm）
    client.post("/auth/login", json={"username": "mvm_user_a", "password": "Pwd@2026"})
    fake_webm = b"\x1a\x45\xdf\xa3" + b"0" * 200  # EBML 头 + 填充，服务端不校验魔数
    r = client.post(
        "/images/audio",
        files={"file": ("voice.webm", fake_webm, "audio/webm")},
    ).json()
    assert r["code"] == 0, r
    audio_url = r["data"]["url"]
    assert audio_url.startswith("/uploads/")

    # 发送语音消息
    r = client.post(
        "/messages",
        params={"receiver_id": b["user_id"]},
        json={"content": audio_url, "msg_type": "voice"},
    ).json()
    assert r["code"] == 0, r
    assert r["data"]["msg_type"] == "voice"
    assert r["data"]["content"] == audio_url


def test_activity_public_and_join_flow(client):
    """活动列表/详情/报名/重复报名/取消报名。"""
    from app.core.database import SessionLocal
    from app.models import Activity

    with SessionLocal() as db:
        db.add(Activity(title="校园篮球赛", description="周五下午篮球场", location="篮球场",
                        organizer="学生会", max_participants=10, is_active=True))
        db.commit()

    u = register(client, "act_user_a", "活动用户A")

    # 列表（未登录也能看）
    r = client.get("/activities").json()
    assert r["code"] == 0
    assert r["data"]["total"] == 1
    aid = r["data"]["items"][0]["id"]
    assert r["data"]["items"][0]["joined"] is False

    # 详情
    r = client.get(f"/activities/{aid}").json()
    assert r["code"] == 0
    assert r["data"]["title"] == "校园篮球赛"

    # 报名
    r = client.post(f"/activities/{aid}/join", json={"action": "join"}).json()
    assert r["code"] == 0, r
    assert r["data"]["joined"] is True
    assert r["data"]["participant_count"] == 1

    # 重复报名被拒
    r = client.post(f"/activities/{aid}/join", json={"action": "join"}).json()
    assert r["code"] != 0

    # 列表里 joined 状态正确
    r = client.get("/activities").json()
    assert r["data"]["items"][0]["joined"] is True

    # 取消报名
    r = client.post(f"/activities/{aid}/join", json={"action": "cancel"}).json()
    assert r["code"] == 0, r
    assert r["data"]["joined"] is False
    assert r["data"]["participant_count"] == 0


def test_admin_activity_crud(client):
    """后台活动管理：创建/更新/停用/删除/报名名单。"""
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models import Admin

    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == "t9_activity_admin").first():
            db.add(Admin(username="t9_activity_admin", password_hash=hash_password("Admin@2026Pwd"), role="admin"))
            db.commit()
    r = client.post("/admin/login", json={"username": "t9_activity_admin", "password": "Admin@2026Pwd"}).json()
    assert r["code"] == 0

    # 创建
    r = client.post("/admin/activities", json={
        "title": "社团招新",
        "description": "招新活动详情",
        "location": "操场",
        "start_at": "2026-09-10T09:00:00+08:00",
        "organizer": "社团联合会",
        "max_participants": 50,
    }).json()
    assert r["code"] == 0, r
    aid = r["data"]["id"]
    assert r["data"]["participant_count"] == 0

    # 更新
    r = client.patch(f"/admin/activities/{aid}", json={"title": "社团招新（改）", "is_active": False}).json()
    assert r["code"] == 0
    assert r["data"]["title"] == "社团招新（改）"
    assert r["data"]["is_active"] is False

    # 停用后普通用户不可见
    client.post("/admin/logout")
    register(client, "act_admin_u", "活动后台用户")
    r = client.get(f"/activities/{aid}").json()
    assert r["code"] != 0

    # 管理员报名名单接口
    client.post("/admin/login", json={"username": "t9_activity_admin", "password": "Admin@2026Pwd"})
    r = client.get(f"/admin/activities/{aid}/participants").json()
    assert r["code"] == 0
    assert r["data"]["total"] == 0

    # 删除
    r = client.delete(f"/admin/activities/{aid}").json()
    assert r["code"] == 0
    with SessionLocal() as db:
        assert db.get(Activity, aid) is None
