"""首页滚动字幕：后台可配置，公开接口返回，留空关闭。"""

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin
from app.services import settings_service

ADMIN_USER = "t9_marquee_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == ADMIN_USER).first():
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _set_marquee(client, text: str) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"
    resp = client.put("/admin/settings", json={"settings": {"home_marquee": text}}).json()
    assert resp["code"] == 0, resp


def _reset_marquee() -> None:
    with SessionLocal() as db:
        settings_service.set_setting(db, "home_marquee", "")


def test_marquee_public_empty_by_default(client):
    resp = client.get("/settings/public").json()
    assert resp["code"] == 0
    assert resp["data"]["marquee_items"] == []


def test_marquee_returns_configured_lines(client):
    try:
        _set_marquee(client, "欢迎来到立洋社区\n社区公约：友善发言\n")
        resp = client.get("/settings/public").json()
        assert resp["code"] == 0
        assert resp["data"]["marquee_items"] == ["欢迎来到立洋社区", "社区公约：友善发言"]
    finally:
        _reset_marquee()


def test_marquee_blank_after_cleared(client):
    try:
        _set_marquee(client, "测试滚动\n")
        assert client.get("/settings/public").json()["data"]["marquee_items"] == ["测试滚动"]
        _set_marquee(client, "  \n")
        assert client.get("/settings/public").json()["data"]["marquee_items"] == []
    finally:
        _reset_marquee()
