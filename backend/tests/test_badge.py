"""徽章（勋章）系统回归测试。

覆盖：
- 徽章目录：至少 20 个种子徽章，包含管理员徽章 / 集团成员徽章
- 激活码领取：无效码失败、有效码成功、重复领取失败、重复使用激活码失败
- 佩戴/卸下：未拥有不能佩戴、佩戴后 profile/帖子展示 author_badge
- 后台管理：创建徽章、生成激活码、激活码列表、删除激活码、直接发放、
  系统徽章不可删除
"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, BadgeCode, UserBadge
from tests.conftest import create_post, register

ADMIN_USER = "badge_admin"
ADMIN_PWD = "Admin@2026Pwd"


def _ensure_admin() -> None:
    with SessionLocal() as db:
        existing = db.query(Admin).filter(Admin.username == ADMIN_USER).first()
        if not existing:
            db.add(Admin(username=ADMIN_USER, password_hash=hash_password(ADMIN_PWD), role="admin"))
            db.commit()


def _admin_login(client) -> None:
    _ensure_admin()
    resp = client.post("/admin/login", json={"username": ADMIN_USER, "password": ADMIN_PWD}).json()
    assert resp["code"] == 0, f"admin login failed: {resp}"


def test_badge_catalog_has_at_least_20_and_required_badges(client):
    """徽章目录 >= 20 个，且包含管理员徽章和集团成员徽章。"""
    register(client, "13707000001", "徽章目录员")
    resp = client.get("/badges").json()
    assert resp["code"] == 0
    badges = resp["data"]
    assert len(badges) >= 20
    codes = {b["code"] for b in badges}
    assert "admin" in codes
    assert "group_member" in codes


def test_claim_badge_with_invalid_code(client):
    """无效激活码领取失败 -213。"""
    register(client, "13707000002", "无效码员")
    resp = client.post("/badges/claim", json={"code": "BADCODE00"}).json()
    assert resp["code"] == -213


def test_claim_badge_success_and_repeat_fails(client):
    """有效激活码领取成功；重复领取/重复使用激活码失败。"""
    info = register(client, "13707000003", "领取员")
    _ensure_admin()
    _admin_login(client)
    # 管理员为「新人报到」徽章生成激活码
    badges = client.get("/admin/badges").json()["data"]
    newcomer = next(b for b in badges if b["code"] == "newcomer")
    gen = client.post(
        f"/admin/badges/{newcomer['id']}/codes",
        json={"count": 1, "note": "测试码"},
    ).json()
    assert gen["code"] == 0
    code = gen["data"]["codes"][0]
    # 登出管理员，用普通用户领取
    client.post("/admin/logout")

    resp = client.post("/badges/claim", json={"code": code}).json()
    assert resp["code"] == 0
    assert resp["data"]["name"] == "新人报到"

    # 我的徽章包含新徽章
    mine = client.get("/badges/mine").json()["data"]
    assert any(b["code"] == "newcomer" for b in mine["owned"])
    assert mine["wearing_badge"] is not None  # 首次领取自动佩戴

    # 重复领取：激活码已被使用
    resp2 = client.post("/badges/claim", json={"code": code}).json()
    assert resp2["code"] == -213

    # 已拥有后再次领取（使用另一个码）报 -214
    _admin_login(client)
    gen2 = client.post(
        f"/admin/badges/{newcomer['id']}/codes",
        json={"count": 1},
    ).json()
    code2 = gen2["data"]["codes"][0]
    client.post("/admin/logout")
    resp3 = client.post("/badges/claim", json={"code": code2}).json()
    assert resp3["code"] == -214


def test_wear_badge_and_profile_post_display(client):
    """佩戴徽章后 profile / 帖子 author_badge 正确展示；未拥有不能佩戴。"""
    info = register(client, "13707000004", "佩戴员")
    # 未拥有：佩戴失败
    resp = client.post("/badges/wear", json={"badge_id": 1}).json()
    assert resp["code"] in (-212, -215)

    # 管理员直接发放「管理员」徽章
    _ensure_admin()
    _admin_login(client)
    badges = client.get("/admin/badges").json()["data"]
    admin_badge = next(b for b in badges if b["code"] == "admin")
    grant = client.post(
        "/admin/badges/grant",
        json={"user_id": info["user_id"], "badge_id": admin_badge["id"]},
    ).json()
    assert grant["code"] == 0
    client.post("/admin/logout")

    # 佩戴管理员徽章
    wear = client.post("/badges/wear", json={"badge_id": admin_badge["id"]}).json()
    assert wear["code"] == 0
    assert wear["data"]["code"] == "admin"

    # profile 展示 wearing_badge
    me = client.get("/users/me").json()["data"]
    assert me["wearing_badge"] is not None
    assert me["wearing_badge"]["code"] == "admin"
    assert me["badge_count"] >= 1

    # 帖子 author_badge 展示
    post = create_post(client, info["school_id"], "佩戴徽章发帖")
    detail = client.get(f"/posts/{post['id']}").json()["data"]
    assert detail["author_badge"] is not None
    assert detail["author_badge"]["code"] == "admin"

    # 卸下后 profile 不再展示
    client.delete("/badges/wear")
    me2 = client.get("/users/me").json()["data"]
    assert me2["wearing_badge"] is None


def test_admin_badge_management(client):
    """后台徽章管理：创建/更新/生成激活码/列表/删除码。"""
    info = register(client, "13707000005", "管理测试员")
    _admin_login(client)

    # 创建徽章
    create = client.post(
        "/admin/badges",
        json={
            "name": "测试徽章",
            "code": "test_badge_x",
            "icon": "🧪",
            "description": "测试用",
            "sort_order": 99,
        },
    ).json()
    assert create["code"] == 0
    badge_id = create["data"]["id"]

    # 更新徽章
    upd = client.patch(
        f"/admin/badges/{badge_id}",
        json={"description": "更新后的描述", "sort_order": 100},
    ).json()
    assert upd["code"] == 0
    assert upd["data"]["sort_order"] == 100

    # 生成激活码
    gen = client.post(
        f"/admin/badges/{badge_id}/codes",
        json={"count": 2, "note": "批量", "batch_no": "TEST001"},
    ).json()
    assert gen["code"] == 0
    assert len(gen["data"]["codes"]) == 2

    # 激活码列表
    codes = client.get("/admin/badge-codes", params={"badge_id": badge_id}).json()
    assert codes["code"] == 0
    assert codes["data"]["total"] == 2

    # 删除未使用激活码
    code_id = codes["data"]["items"][0]["id"]
    delete_code = client.delete(f"/admin/badge-codes/{code_id}").json()
    assert delete_code["code"] == 0
    codes2 = client.get("/admin/badge-codes", params={"badge_id": badge_id}).json()
    assert codes2["data"]["total"] == 1

    # 删除非系统徽章成功
    del_badge = client.delete(f"/admin/badges/{badge_id}").json()
    assert del_badge["code"] == 0

    # 系统徽章（管理员）不可删除
    badges = client.get("/admin/badges").json()["data"]
    admin_badge = next(b for b in badges if b["code"] == "admin")
    deny = client.delete(f"/admin/badges/{admin_badge['id']}").json()
    assert deny["code"] != 0


def test_admin_grant_badge_notifies_and_marks_owned(client):
    """管理员直接发放徽章后，用户拥有该徽章且收到系统通知。"""
    info = register(client, "13707000006", "发放员")
    _admin_login(client)
    badges = client.get("/admin/badges").json()["data"]
    star = next(b for b in badges if b["code"] == "community_star")
    grant = client.post(
        "/admin/badges/grant",
        json={"user_id": info["user_id"], "badge_id": star["id"]},
    ).json()
    assert grant["code"] == 0
    client.post("/admin/logout")

    with SessionLocal() as db:
        assert db.query(UserBadge).filter(
            UserBadge.user_id == info["user_id"], UserBadge.badge_id == star["id"]
        ).first() is not None

    notifs = client.get("/notifications", params={"type": "system"}).json()["data"]
    assert any("徽章" in n["title"] for n in notifs["items"])
