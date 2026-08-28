"""徽章自动发放规则回归测试。

覆盖：
- 后台创建「审核通过帖子数」规则 → 帖子审核通过后自动发放徽章
- 头像上传不进入人工审核（audit_status=approved）
- 普通图片上传仍进入人工审核（pending）
"""
import io

from PIL import Image as PILImage

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, Badge
from tests.conftest import register

ADMIN_USER = "badge_rule_admin"
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


def _badge_id(client, code: str) -> int:
    badges = client.get("/admin/badges").json()["data"]
    return next(b for b in badges if b["code"] == code)["id"]


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (64, 64), (0, 122, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_auto_grant_badge_on_post_approved(client):
    """审核通过帖子数达到阈值自动发放徽章。"""
    _admin_login(client)
    info = register(client, "13711000001", "自动徽章员", invite_code="__seed__")
    # 创建规则：审核通过 1 帖 → 发放「创作大师」
    badge_id = _badge_id(client, "creator")
    rule = client.post(
        "/admin/badge-rules",
        json={"action": "approved_posts", "badge_id": badge_id, "threshold": 1, "description": "发布 1 篇通过审核的帖子"},
    ).json()
    assert rule["code"] == 0, rule
    client.post("/admin/logout")

    # 用户发帖（AI 关闭 → 人工审核）
    post = client.post(
        "/posts",
        json={
            "content": "这是一段用于测试自动徽章的帖子内容",
            "school_id": info["school_id"],
            "category": "default",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert post["code"] == 0, post
    assert post["data"]["ai_status"] == "manual_review"

    # 管理员审核通过 → 自动发徽章
    _admin_login(client)
    client.patch(f"/admin/posts/{post['data']['id']}/audit", json={"ai_status": "approved"})
    client.post("/admin/logout")

    mine = client.get("/badges/mine").json()["data"]
    assert any(b["id"] == badge_id for b in mine["owned"]), "审核通过后应自动获得徽章"
    notifs = client.get("/notifications", params={"type": "system"}).json()["data"]
    assert any("自动获得新徽章" in n["title"] for n in notifs["items"])


def test_avatar_upload_skips_audit(client):
    """头像上传不进入人工审核；普通图片上传进入人工审核。"""
    register(client, "13711000002", "头像员", invite_code="__seed__")
    files = {"file": ("a.png", _png_bytes(), "image/png")}

    avatar = client.post("/images?purpose=avatar", files=files).json()
    assert avatar["code"] == 0, avatar
    assert avatar["data"]["audit_status"] == "approved"

    normal = client.post("/images", files=files).json()
    assert normal["code"] == 0, normal
    assert normal["data"]["audit_status"] == "pending"
    assert normal["data"]["audit_note"] == "图片内容需人工审核"
