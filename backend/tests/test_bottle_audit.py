"""漂流瓶 AI 审核回归测试。

覆盖：
- AI 不可用（测试环境）时投放的瓶子转人工审核，不直接放行
- 未审核通过的瓶子不会进入拾取池
- 管理员通过后瓶子可被拾取
- 管理员驳回后瓶子不可拾取
"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin
from tests.conftest import register

ADMIN_USER = "bottle_audit_admin"
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


def _drop_bottle(client, school_id: int, content: str = "这是一条漂流瓶测试内容") -> dict:
    resp = client.post(
        "/bottles",
        json={"content": content, "school_id": school_id, "tags": ["音乐"]},
    ).json()
    assert resp["code"] == 0, resp
    return resp["data"]


def test_bottle_goes_manual_review_when_ai_unavailable(client):
    """AI 不可用时投放的瓶子转人工审核，不直接放行。"""
    info = register(client, "13710000001", "瓶子作者A", invite_code="__seed__")
    bottle = _drop_bottle(client, info["school_id"])
    assert bottle["audit_status"] == "manual_review"
    assert "人工审核" in (bottle["reject_reason"] or "")
    # 作者收到系统通知
    notifs = client.get("/notifications", params={"type": "system"}).json()["data"]
    assert any("人工审核" in n["title"] for n in notifs["items"])


def test_unapproved_bottle_not_pickable(client):
    """未审核通过的瓶子不进入拾取池（拾取返回空）。"""
    info_a = register(client, "13710000002", "瓶子作者B", invite_code="__seed__")
    _drop_bottle(client, info_a["school_id"])
    # 登出 A，注册拾取者 B
    client.post("/auth/logout")
    info_b = register(client, "13710000003", "拾取者B", invite_code="__seed__")
    resp = client.post(
        "/bottles/pick",
        json={"school_ids": [info_a["school_id"]], "tags": [], "target_gender": "any"},
    ).json()
    assert resp["code"] != 0  # 404 海里暂时没有瓶子


def test_admin_approve_makes_bottle_pickable(client):
    """管理员通过后瓶子进入拾取池。"""
    _admin_login(client)
    info_a = register(client, "13710000004", "瓶子作者C", invite_code="__seed__")
    bottle = _drop_bottle(client, info_a["school_id"])

    bottles = client.get("/admin/bottles", params={"status": "manual_review"}).json()["data"]
    assert any(b["id"] == bottle["id"] for b in bottles["items"])
    rev = client.post(f"/admin/bottles/{bottle['id']}/review", json={"action": "approve"}).json()
    assert rev["code"] == 0
    assert rev["data"]["audit_status"] == "approved"
    client.post("/admin/logout")

    client.post("/auth/logout")
    register(client, "13710000005", "拾取者C", invite_code="__seed__")
    resp = client.post(
        "/bottles/pick",
        json={"school_ids": [info_a["school_id"]], "tags": [], "target_gender": "any"},
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["id"] == bottle["id"]


def test_admin_reject_hides_bottle(client):
    """管理员驳回后瓶子不可拾取，作者收到未通过通知。"""
    _admin_login(client)
    info_a = register(client, "13710000006", "瓶子作者D", invite_code="__seed__")
    bottle = _drop_bottle(client, info_a["school_id"], content="瓶子被驳回的内容")
    rev = client.post(
        f"/admin/bottles/{bottle['id']}/review",
        json={"action": "reject", "reject_reason": "内容不适宜"},
    ).json()
    assert rev["code"] == 0
    assert rev["data"]["audit_status"] == "rejected"
    client.post("/admin/logout")

    # 作者收到驳回通知
    notifs = client.get("/notifications", params={"type": "system"}).json()["data"]
    assert any("未通过" in n["title"] for n in notifs["items"])

    # 拾取者 B 拾取：即使拾取池里还有其他瓶子，被驳回的瓶子也绝不能被拾取
    client.post("/auth/logout")
    register(client, "13710000007", "拾取者D", invite_code="__seed__")
    resp = client.post(
        "/bottles/pick",
        json={"school_ids": [info_a["school_id"]], "tags": [], "target_gender": "any"},
    ).json()
    if resp["code"] == 0:
        assert resp["data"]["id"] != bottle["id"], "被驳回的瓶子不应进入拾取池"
    else:
        assert True  # 无其他可拾取瓶子时返回空也可接受
