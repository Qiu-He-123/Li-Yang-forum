"""后台增强：网站访问统计、待处理红点计数、帖子热度排行、用户管理账号列。"""

import time

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, Post, VisitLog
from tests.conftest import create_post, register

ADMIN_USER = "t9_enhance_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == ADMIN_USER).first():
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _admin_login(client) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, resp


def _clear_visits() -> None:
    with SessionLocal() as db:
        db.query(VisitLog).delete()
        db.commit()


def test_record_visit_and_admin_stats(client):
    _clear_visits()
    resp = client.post(
        "/stats/visit",
        headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"},
        json={},
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["recorded"] is True

    _admin_login(client)
    stats = client.get("/admin/stats").json()["data"]
    assert stats["visits"]["total"] >= 1
    assert stats["visits"]["unique_ips"] >= 1
    assert stats["visits"]["today"] >= 1
    assert stats["visits"]["today_unique_ips"] >= 1
    assert len(stats["visits"]["trend_7d"]) == 7
    assert stats["visits"]["trend_7d"][-1]["visits"] >= 1
    assert "hot_posts" in stats


def test_visit_skips_script_ua(client):
    resp = client.post("/stats/visit", headers={"User-Agent": "python-requests/2.31.0"}, json={}).json()
    assert resp["code"] == 0
    assert resp["data"]["recorded"] is False


def test_pending_counts_reflect_unreviewed_content(client):
    _admin_login(client)
    u = register(client, f"pe_{int(time.time())}")
    post = create_post(client, u["school_id"], "待审核内容", category="普通")
    with SessionLocal() as db:
        p = db.get(Post, post["id"])
        p.ai_status = "pending"
        db.commit()
    counts = client.get("/admin/pending-counts").json()["data"]
    assert counts["posts"] >= 1
    assert set(counts) >= {
        "posts", "comments", "reports", "images", "bottles", "appeals", "feedback", "verifications",
    }


def test_hot_posts_ranking(client):
    _admin_login(client)
    u = register(client, f"hp_{int(time.time())}")
    post = create_post(client, u["school_id"], "热度测试帖子内容", category="普通")
    with SessionLocal() as db:
        p = db.get(Post, post["id"])
        p.ai_status = "approved"
        p.like_count = 100
        p.comment_count = 5
        p.view_count = 200
        db.commit()
    stats = client.get("/admin/stats").json()["data"]
    top = stats["hot_posts"][0]
    assert top["id"] == post["id"]
    assert top["heat"] >= 100 + 5 * 3 + 200
    assert top["title"]
    assert top["rank"] == 1


def test_admin_users_include_username(client):
    _admin_login(client)
    username = f"pu_{int(time.time())}"
    u = register(client, username, nickname="账号列测试")
    users = client.get("/admin/users").json()["data"]["items"]
    row = next(x for x in users if x["id"] == u["user_id"])
    assert row["username"] == username
