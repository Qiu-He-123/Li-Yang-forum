"""微信朋友圈同步 + 金币系统回归测试。

覆盖：
- 设备上报好友快照 → 用户绑定（微信号匹配）
- 绑定奖励金币、自动同步开关、历史分界线
- 设备上报朋友圈：命中自动同步发帖 / 未命中只入库
- 微信朋友圈频道 feed（置顶优先、按朋友圈时间倒序）
- 手动导入（含置顶按天收费）、金币流水、徽章购买
- 手动刷新限流、新手引导完成标记
"""

from datetime import datetime, timezone

import secrets

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import Badge, CaptchaTicket, Post, User, WechatMoment
from app.services import settings_service, wechat_sync_service


def _register(client, username: str, nickname: str = "测试员") -> dict:
    """注册（测试环境直接插入已知答案的验证码票据）。"""
    from app.models import SeedInviteCode

    ticket_id = secrets.token_urlsafe(16)
    with SessionLocal() as db:
        db.add(CaptchaTicket(ticket_id=ticket_id, answer="test", ip="testclient"))
        seed = db.scalar(
            select(SeedInviteCode).where(
                SeedInviteCode.used_by.is_(None),
                SeedInviteCode.status == "unused",
            )
        )
        invite_code = seed.code if seed else None
        db.commit()
    schools = client.get("/schools").json()["data"]
    body = {
        "nickname": nickname,
        "username": username,
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": schools[0]["id"],
        "agreed": True,
        "invite_code": invite_code,
        "captcha_id": ticket_id,
        "captcha_text": "test",
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == 0, resp
    return {"school_id": schools[0]["id"], "user_id": resp["data"]["user_id"]}


def _device_token() -> str:
    with SessionLocal() as db:
        return wechat_sync_service.get_device_token(db)


def _auth_headers(token: str) -> dict:
    return {"X-Device-Token": token}


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _disable_audit_scope() -> None:
    """测试环境关闭 AI/图片审核，让同步帖直接 approved 可见。"""
    with SessionLocal() as db:
        settings_service.set_setting(db, "audit_scope", "")
        settings_service.invalidate_cache()


def _ingest(
    client,
    token: str,
    tid: str,
    wxid: str,
    content: str,
    create_time: int,
    with_image: bool = False,
) -> dict:
    data = {
        "tid": tid,
        "wxid": wxid,
        "author_name": "测试好友",
        "content": content,
        "create_time": str(create_time),
    }
    files = []
    if with_image:
        # 最小合法 JPEG magic bytes，storage 本地落盘即可
        jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        files.append(("files", ("pic.jpg", jpg, "image/jpeg")))
    resp = client.post(
        "/wechat-sync/ingest",
        data=data,
        files=files,
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]


def test_wechat_sync_full_flow(client):
    _disable_audit_scope()
    token = _device_token()
    _register(client, "wx_user_a", "用户A")
    _register(client, "wx_user_b", "用户B")

    # 1. 设备上报好友快照
    resp = client.post(
        "/wechat-sync/friends",
        json={
            "friends": [
                {"wxid": "wxid_a_001", "wechat_id": "wechat_a", "nickname": "好友A"},
                {"wxid": "wxid_b_001", "wechat_id": "wechat_b", "nickname": "好友B"},
            ]
        },
        headers=_auth_headers(token),
    )
    assert resp.json()["data"]["added"] == 2

    # 2. 用户A 分步绑定第 1 步：查好友 + 生成消息验证码（待验证）
    resp = client.post("/wechat/bind", json={"query": "wechat_a"}).json()
    assert resp["code"] == 0, resp
    assert resp["data"]["step"] == "code"
    verify_code = resp["data"]["verify_code"]
    status = client.get("/wechat/status").json()["data"]
    assert status["bound"] is False
    assert status["status"] == "pending"

    # 3. 设备上报"收到的消息"（用户把验证码发给社区微信号）→ 校验通过即绑定成功
    r = client.post(
        "/wechat-sync/messages/recent",
        json={"items": [{"peer": "wxid_a_001", "text": verify_code, "last_time": _now_ts()}]},
        headers=_auth_headers(token),
    ).json()
    assert r["code"] == 0
    vr = client.post("/wechat/bind/verify-code", json={"code": verify_code.lower()}).json()
    assert vr["code"] == 0, vr
    assert vr["data"]["matched"] is True
    status = client.get("/wechat/status").json()["data"]
    assert status["bound"] is True
    assert status["coins"] == 10  # 绑定成功才送金币
    assert status["onboarding_done"] is False

    # 4. 开启自动同步（记录历史分界线）
    status = client.patch("/wechat/sync-config", json={"enabled": True}).json()["data"]
    assert status["sync_enabled"] is True
    assert status["sync_enabled_at"]

    # 设备侧可拿到自动同步分界线（客户端据此只上传开启之后的新动态）
    cutoffs = client.get("/wechat-sync/cutoffs", headers=_auth_headers(token)).json()["data"]["items"]
    assert any(it["wxid"] == "wxid_a_001" and it["sync_enabled_at"] > 0 for it in cutoffs)

    # 5. 上报朋友圈：绑定后发布的 → 自动发帖；分界线之前的 → 只入库
    now = _now_ts()
    r1 = _ingest(client, token, "tid_1001", "wxid_a_001", "自动同步的内容", now + 10, with_image=True)
    assert r1["posted"] is True
    r2 = _ingest(client, token, "tid_1002", "wxid_a_001", "分界线之前的历史内容", now - 100)
    assert r2["posted"] is False
    # 未绑定用户的朋友圈：只入库不发帖
    r3 = _ingest(client, token, "tid_1003", "wxid_b_001", "未绑定用户的内容", now + 10)
    assert r3["posted"] is False

    with SessionLocal() as db:
        assert db.scalar(select(WechatMoment).where(WechatMoment.tid == "tid_1001")) is not None
        auto_posts = db.scalars(
            select(Post).where(Post.source == "wechat_auto")
        ).all()
        assert len(auto_posts) == 1

    # 5. 微信朋友圈频道：只有审核通过的自动帖，按朋友圈时间排序
    feed = client.get("/wechat/feed").json()["data"]
    assert feed["total"] == 1
    item = feed["items"][0]
    assert item["source"] == "wechat_auto"
    assert item["wechat_created_at"]
    assert len(item["image_urls"]) == 1

    # 6. 同步帖也出现在普通最新流
    latest = client.get("/posts", params={"view": "latest", "page_size": 20}).json()["data"]
    assert any(p["id"] == item["id"] for p in latest["items"])

    # 7. 手动导入：选分界线之前那条 + 置顶 1 天 → 扣 1 金币
    moments = client.get("/wechat/moments", params={"page_size": 50}).json()["data"]
    assert moments["total"] == 2
    by_tid = {m["tid"]: m for m in moments["items"]}
    assert by_tid["tid_1001"]["imported"] is True
    assert by_tid["tid_1002"]["imported"] is False

    resp = client.post(
        "/wechat/import",
        json={
            "tids": ["tid_1002"],
            "pinned_tids": ["tid_1002"],
            "pin_days": 1,
        },
    ).json()
    assert resp["code"] == 0, resp
    assert resp["data"]["cost"] == 1

    coins = client.get("/coins/me").json()["data"]
    assert coins["coins"] == 9

    # 8. feed：手动帖置顶在最前
    feed = client.get("/wechat/feed").json()["data"]
    assert feed["total"] == 2
    assert feed["items"][0]["is_pinned"] is True
    assert feed["items"][0]["source"] == "wechat_manual"

    # 9. 重复导入被拦截
    resp = client.post(
        "/wechat/import",
        json={"tids": ["tid_1002"], "pinned_tids": [], "pin_days": 1},
    ).json()
    assert resp["code"] != 0

    # 10. 手动刷新：只标记该用户，客户端心跳领取后即清除；30 秒窗口内第二次被拒
    r = client.post("/wechat/refresh").json()
    assert r["code"] == 0 and r["data"]["wxid"] == "wxid_a_001"
    ping1 = client.get("/wechat-sync/ping", headers=_auth_headers(token)).json()["data"]
    assert ping1["force_wxid"] == "wxid_a_001"
    ping2 = client.get("/wechat-sync/ping", headers=_auth_headers(token)).json()["data"]
    assert ping2["force_wxid"] == ""
    assert client.post("/wechat/refresh").json()["code"] != 0  # 限流

    # 11. 徽章购买
    with SessionLocal() as db:
        badge = Badge(name="金币徽章", code="coin_badge", icon="🪙", price=5, is_active=True)
        db.add(badge)
        db.commit()
        badge_id = badge.id
    resp = client.post(f"/coins/badges/{badge_id}/purchase").json()
    assert resp["code"] == 0, resp
    assert resp["data"]["coins"] == 4
    resp = client.post(f"/coins/badges/{badge_id}/purchase").json()
    assert resp["code"] != 0  # 已拥有

    # 12. 新手引导
    resp = client.post("/onboarding/complete").json()
    assert resp["data"]["onboarding_done"] is True
    assert client.get("/onboarding/status").json()["data"]["onboarding_done"] is True


def test_auto_synced_violation_no_penalty(client):
    """自动同步帖被 AI 判违规：不扣警告分、不累计违规次数，但仍发审核未通过通知。"""
    from app.core.database import SessionLocal
    from app.models import Notification, Post, User
    from app.services import audit_service

    info = _register(client, "wx_violation_a", "违规测试A")
    with SessionLocal() as db:
        user = db.get(User, info["user_id"])
        post = Post(
            author_id=user.id,
            school_id=user.school_id,
            category="朋友圈",
            content="自动同步的测试内容",
            image_urls="[]",
            ai_status="pending",
            source="wechat_auto",
            is_hidden_by_unverify=False,
        )
        db.add(post)
        db.commit()

        audit_service._handle_violation(
            db, user.id, "post", post.id, "测试违规", "自动同步的测试内容", severity="high"
        )
        db.commit()
        db.refresh(user)
        assert user.warning_score == 0
        assert (user.violation_count or 0) == 0
        notif_count = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id,
                Notification.reference_type == "post",
                Notification.reference_id == post.id,
            )
        )
        assert notif_count == 1

        # 对照：普通发帖被 AI 判违规仍正常扣分
        post2 = Post(
            author_id=user.id,
            school_id=user.school_id,
            category="普通",
            content="普通帖子的测试内容",
            image_urls="[]",
            ai_status="pending",
            source="normal",
            is_hidden_by_unverify=False,
        )
        db.add(post2)
        db.commit()
        audit_service._handle_violation(
            db, user.id, "post", post2.id, "测试违规", "普通帖子的测试内容", severity="high"
        )
        db.commit()
        db.refresh(user)
        assert user.warning_score > 0
        assert (user.violation_count or 0) == 1
