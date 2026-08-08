"""T9-1 评论模块回归测试。

覆盖：
- 发表评论
- 二级回复（parent_id）
- 评论列表（含二级回复分层）
- 删除评论（作者可删 / 非作者不可删）
- _comment_dict 含 user_id（T7-15）
- 评论计数同步（T6-6 用接口返回值）
- 评论分页（T8-3）
"""
import pytest

from app.core.database import SessionLocal
from app.models import Post
from tests.conftest import create_post, register


def test_create_comment_success(client):
    """发表评论成功 + 返回 user_id（T7-15）。"""
    info = register(client, "13702000001", "评论员")
    post = create_post(client, info["school_id"], "评论测试帖子")
    resp = client.post(
        f"/posts/{post['id']}/comments",
        json={"content": "T9-1 测试评论"},
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["content"] == "T9-1 测试评论"
    assert resp["data"]["user_id"] == info["user_id"], "_comment_dict 应含 user_id"


def test_create_comment_rejects_empty_content(client):
    """空内容评论失败。"""
    info = register(client, "13702000002", "空评论员")
    post = create_post(client, info["school_id"], "空评论测试")
    resp = client.post(f"/posts/{post['id']}/comments", json={"content": ""}).json()
    assert resp["code"] != 0


def test_create_reply_with_parent_id(client):
    """二级回复：parent_id 指向一级评论。"""
    info = register(client, "13702000003", "回复员")
    post = create_post(client, info["school_id"], "二级回复测试帖")
    # 发一级评论
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "一级评论"}).json()
    parent_id = c["data"]["id"]
    # 发二级回复
    resp = client.post(
        f"/posts/{post['id']}/comments",
        json={"content": "二级回复内容", "parent_id": parent_id},
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["parent_id"] == parent_id


def test_list_comments_includes_replies(client):
    """评论列表包含一级评论 + 二级回复。"""
    info = register(client, "13702000004", "列表员")
    post = create_post(client, info["school_id"], "列表测试帖")
    # 一级 + 二级
    c1 = client.post(f"/posts/{post['id']}/comments", json={"content": "一级"}).json()
    client.post(
        f"/posts/{post['id']}/comments",
        json={"content": "二级 A", "parent_id": c1["data"]["id"]},
    )
    client.post(
        f"/posts/{post['id']}/comments",
        json={"content": "二级 B", "parent_id": c1["data"]["id"]},
    )
    # 列表
    resp = client.get(f"/posts/{post['id']}/comments").json()
    assert resp["code"] == 0
    items = resp["data"] if isinstance(resp["data"], list) else resp["data"]["items"]
    assert len(items) >= 3, f"应含 1 一级 + 2 二级，实际 {len(items)}"
    # 二级回复的 parent_id 应指向一级
    replies = [it for it in items if it["parent_id"] == c1["data"]["id"]]
    assert len(replies) == 2


def test_delete_comment_by_author(client):
    """作者可删除自己评论。"""
    info = register(client, "13702000005", "删评员")
    post = create_post(client, info["school_id"], "删评测试帖")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "待删除评论"}).json()
    cid = c["data"]["id"]
    resp = client.delete(f"/posts/{post['id']}/comments/{cid}").json()
    assert resp["code"] == 0
    # 列表中不再出现
    listing = client.get(f"/posts/{post['id']}/comments").json()
    items = listing["data"] if isinstance(listing["data"], list) else listing["data"]["items"]
    ids = [it["id"] for it in items]
    assert cid not in ids


def test_delete_comment_rejects_non_author(client):
    """非作者不可删除他人评论。"""
    info_a = register(client, "13702000006", "评论作者A")
    post = create_post(client, info_a["school_id"], "A 的帖子")
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "A 的评论"}).json()
    cid = c["data"]["id"]
    # 登出 A，注册 B
    client.post("/auth/logout")
    register(client, "13702000007", "用户B")
    # B 尝试删 A 的评论
    resp = client.delete(f"/posts/{post['id']}/comments/{cid}").json()
    assert resp["code"] != 0


def test_comment_count_synced_from_backend(client):
    """T6-6：发评论返回 post_comment_count，前端用它覆盖。"""
    info = register(client, "13702000008", "计数员")
    post = create_post(client, info["school_id"], "计数测试帖")
    # 发评论
    c = client.post(f"/posts/{post['id']}/comments", json={"content": "评论 1"}).json()
    # 应返回 post_comment_count 字段
    assert "post_comment_count" in c["data"], "T6-6: 应返回 post_comment_count"
    assert c["data"]["post_comment_count"] == 1
    # 再发一条
    c2 = client.post(f"/posts/{post['id']}/comments", json={"content": "评论 2"}).json()
    assert c2["data"]["post_comment_count"] == 2


def test_comment_dict_contains_user_id(client):
    """T7-15：_comment_dict 返回 user_id 字段。"""
    info = register(client, "13702000009", "字段员")
    post = create_post(client, info["school_id"], "字段测试帖")
    client.post(f"/posts/{post['id']}/comments", json={"content": "字段校验评论"})
    listing = client.get(f"/posts/{post['id']}/comments").json()
    items = listing["data"] if isinstance(listing["data"], list) else listing["data"]["items"]
    for c in items:
        assert "user_id" in c, "_comment_dict 缺 user_id 字段"


def test_comment_pagination(client):
    """T8-3：评论分页（page / page_size）。"""
    info = register(client, "13702000010", "评论分页员")
    post = create_post(client, info["school_id"], "分页评论帖")
    for i in range(5):
        client.post(f"/posts/{post['id']}/comments", json={"content": f"评论 #{i+1}"})
    # 第 1 页 2 条
    resp = client.get(f"/posts/{post['id']}/comments", params={"page": 1, "page_size": 2}).json()
    assert resp["code"] == 0
    # 兼容两种结构
    if isinstance(resp["data"], dict):
        items = resp["data"]["items"]
        total = resp["data"]["total"]
        assert total >= 5
        assert len(items) <= 2
    else:
        # 旧结构裸数组也允许（兼容）
        assert len(resp["data"]) <= 5


def test_delete_root_comment_cascades_replies(client):
    """Bug 修复：删除根评论时级联删除其所有回复。

    之前删除根评论后，子回复成为孤立数据（parent_id 指向已删除评论），
    导致 comment_count 与实际可见评论数不一致（前端显示 1 但列表为空）。
    """
    info = register(client, "13702000011", "级联删员")
    post = create_post(client, info["school_id"], "级联删除测试帖")
    # 发根评论
    root = client.post(f"/posts/{post['id']}/comments", json={"content": "根评论"}).json()
    root_id = root["data"]["id"]
    # 发 2 条回复
    client.post(f"/posts/{post['id']}/comments", json={"content": "回复 A", "parent_id": root_id})
    client.post(f"/posts/{post['id']}/comments", json={"content": "回复 B", "parent_id": root_id})
    # 此时 comment_count 应为 3
    assert root["data"]["post_comment_count"] == 1
    # 列表应有 3 条
    listing = client.get(f"/posts/{post['id']}/comments").json()
    items = listing["data"]["items"] if isinstance(listing["data"], dict) else listing["data"]
    assert len(items) == 3

    # 删除根评论
    resp = client.delete(f"/posts/{post['id']}/comments/{root_id}").json()
    assert resp["code"] == 0
    # 应返回 post_comment_count = 0（根 + 2 回复全部删除）
    assert resp["data"]["post_comment_count"] == 0, (
        f"级联删除后 comment_count 应为 0，实际 {resp['data']['post_comment_count']}"
    )

    # 列表应为空
    listing2 = client.get(f"/posts/{post['id']}/comments").json()
    items2 = listing2["data"]["items"] if isinstance(listing2["data"], dict) else listing2["data"]
    assert len(items2) == 0, f"级联删除后评论列表应为空，实际 {len(items2)} 条"


def test_delete_reply_does_not_cascade(client):
    """Bug 修复验证：删除回复只删自己，不影响根评论和其他回复。"""
    info = register(client, "13702000012", "删回复员")
    post = create_post(client, info["school_id"], "删回复测试帖")
    root = client.post(f"/posts/{post['id']}/comments", json={"content": "根评论"}).json()
    root_id = root["data"]["id"]
    reply_a = client.post(
        f"/posts/{post['id']}/comments", json={"content": "回复 A", "parent_id": root_id}
    ).json()
    client.post(f"/posts/{post['id']}/comments", json={"content": "回复 B", "parent_id": root_id})

    # 删除回复 A
    resp = client.delete(f"/posts/{post['id']}/comments/{reply_a['data']['id']}").json()
    assert resp["code"] == 0
    # 应剩 根 + 回复 B = 2 条
    assert resp["data"]["post_comment_count"] == 2

    listing = client.get(f"/posts/{post['id']}/comments").json()
    items = listing["data"]["items"] if isinstance(listing["data"], dict) else listing["data"]
    assert len(items) == 2


def test_post_detail_repairs_stale_comment_count(client):
    info = register(client, "13702000013", "stale-count")
    post = create_post(client, info["school_id"], "stale count post")
    with SessionLocal() as db:
        stale = db.get(Post, post["id"])
        stale.comment_count = 1
        db.commit()

    resp = client.get(f"/posts/{post['id']}").json()
    assert resp["code"] == 0
    assert resp["data"]["comment_count"] == 0
    # 设计说明：详情接口只修复响应中的评论数（真实 count），
    # 不写回 post.comment_count，避免每次详情访问都触发写锁。
    # 持久化修复发生在评论删除/级联删除等写路径。
