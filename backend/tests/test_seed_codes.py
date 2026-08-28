"""种子邀请码后台优化回归测试。

覆盖：
- 复制 N 个未使用种子并标记「待使用」（记录管理员 + 时间）
- 待使用种子不再进入「未使用」池，其他管理员复制时会跳过
- 释放待使用种子回到未使用池
- 仅未使用种子可删除；待使用/已使用不可删除
- 用户消耗种子码后状态变为 used
"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Admin, SeedInviteCode
from tests.conftest import register

ADMIN_USER = "seed_admin"
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


def _generate(client, count: int = 5) -> list[str]:
    resp = client.post("/admin/seed-codes/generate", json={"count": count, "note": "测试批次"}).json()
    assert resp["code"] == 0, resp
    return resp["data"]["codes"]


def test_reserve_marks_pending_with_admin(client):
    """复制并标记待使用：状态/预留管理员/时间正确，且不进入未使用池。"""
    _admin_login(client)
    _generate(client, 5)

    reserve = client.post(
        "/admin/seed-codes/reserve",
        json={"count": 2, "note": "发给班长"},
    ).json()
    assert reserve["code"] == 0
    reserved = reserve["data"]["codes"]
    assert len(reserved) == 2

    # 列表状态与管理员信息
    lst = client.get("/admin/seed-codes", params={"status": "reserved"}).json()["data"]
    reserved_items = [item for item in lst["items"] if item["code"] in reserved]
    assert len(reserved_items) == 2
    assert lst["counts"]["reserved"] >= 2
    for item in reserved_items:
        assert item["status"] == "reserved"
        assert item["reserved_by_username"] == ADMIN_USER
        assert item["reserved_at"]
        assert "待使用：发给班长" in (item["note"] or "")

    # 再复制 2 个：应跳过已标记的，只取剩余未使用
    reserve2 = client.post("/admin/seed-codes/reserve", json={"count": 2}).json()
    assert reserve2["code"] == 0
    assert not (set(reserve2["data"]["codes"]) & set(reserved))


def test_reserve_fails_when_unused_insufficient(client):
    """未使用种子不足时复制失败，提示数量。"""
    _admin_login(client)
    _generate(client, 2)
    # 先复制当前全部未使用种子，确保剩余为 0
    unused_count = client.get("/admin/seed-codes", params={"status": "unused"}).json()["data"]["counts"]["unused"]
    assert unused_count >= 2
    reserve_all = client.post("/admin/seed-codes/reserve", json={"count": unused_count}).json()
    assert reserve_all["code"] == 0
    resp = client.post("/admin/seed-codes/reserve", json={"count": 1}).json()
    assert resp["code"] != 0
    assert ("不足" in resp["msg"]) or ("暂无" in resp["msg"])
    # 恢复测试库：补回未使用种子，避免影响后续测试注册
    _generate(client, 5)


def test_release_returns_to_unused_pool(client):
    """释放待使用种子：状态回到未使用，清除管理员信息。"""
    _admin_login(client)
    _generate(client, 3)
    reserve = client.post("/admin/seed-codes/reserve", json={"count": 1, "note": "误选"}).json()["data"]
    code_id = None
    lst = client.get("/admin/seed-codes", params={"status": "reserved"}).json()["data"]
    for item in lst["items"]:
        if item["code"] == reserve["codes"][0]:
            code_id = item["id"]
    assert code_id is not None

    release = client.post(f"/admin/seed-codes/{code_id}/release").json()
    assert release["code"] == 0
    assert release["data"]["status"] == "unused"

    unused = client.get("/admin/seed-codes", params={"status": "unused"}).json()["data"]
    assert any(item["code"] == reserve["codes"][0] for item in unused["items"])
    # 备注中的「待使用」前缀被移除
    released_item = next(item for item in unused["items"] if item["code"] == reserve["codes"][0])
    assert "待使用：" not in (released_item["note"] or "")


def test_delete_restrictions(client):
    """仅未使用种子可删除；待使用不可删除。"""
    _admin_login(client)
    _generate(client, 2)
    reserve = client.post("/admin/seed-codes/reserve", json={"count": 1}).json()["data"]
    lst = client.get("/admin/seed-codes", params={"status": "reserved"}).json()["data"]
    reserved_id = next(item["id"] for item in lst["items"] if item["code"] == reserve["codes"][0])

    deny = client.delete(f"/admin/seed-codes/{reserved_id}").json()
    assert deny["code"] != 0

    unused = client.get("/admin/seed-codes", params={"status": "unused"}).json()["data"]
    unused_id = unused["items"][0]["id"]
    ok = client.delete(f"/admin/seed-codes/{unused_id}").json()
    assert ok["code"] == 0


def test_seed_code_consumed_becomes_used(client):
    """用户注册消耗种子码后状态变为 used。"""
    _admin_login(client)
    codes = _generate(client, 2)
    reserve = client.post("/admin/seed-codes/reserve", json={"count": 1, "note": "线下分发"}).json()["data"]
    code = reserve["codes"][0]
    client.post("/admin/logout")

    # 用户使用待使用种子注册（种子码可正常消耗）
    info = register(client, "13708000001", "种子消耗员", invite_code=code)
    assert info["user_id"] > 0

    # 重新登录管理员查看列表
    _admin_login(client)
    lst = client.get("/admin/seed-codes", params={"status": "used"}).json()["data"]
    assert any(item["code"] == code for item in lst["items"])
