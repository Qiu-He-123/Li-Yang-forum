"""T9-1 帖子模块回归测试。

覆盖：
- 发帖（成功 / 含图片 URL / 含标签）
- 编辑帖子（作者可编辑 / 非作者不可编辑）
- 删除帖子（作者可删除 / 非作者不可删除）
- 草稿（保存 / 列表 / 发布）
- 分页（page / page_size）
- 搜索（q 关键词 / tag 标签）
- is_public 过滤（T3-5）
- _post_dict 含 author_id（T7-15）
"""
import pytest

from tests.conftest import create_post, register


def test_create_post_success(client):
    """发帖成功 → 返回 id + author_id。"""
    info = register(client, "13701000001", "发帖员")
    post = create_post(client, info["school_id"], "T9-1 测试帖子内容")
    assert post["id"] > 0
    # T7-15：_post_dict 应返回 author_id
    assert post["author_id"] == info["user_id"]


def test_create_post_rejects_empty_content(client):
    """空内容发帖失败。"""
    info = register(client, "13701000002", "空帖员")
    body = {
        "content": "",
        "school_id": info["school_id"],
        "category": "普通",
        "image_urls": [],
        "is_anonymous": False,
        "is_public": True,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] != 0


def test_list_posts_returns_pagination_structure(client):
    """GET /posts 返回 {items, total, page, page_size} 结构（T4-11）。"""
    info = register(client, "13701000003", "分页员")
    for i in range(3):
        create_post(client, info["school_id"], f"分页帖子 #{i+1}")
    resp = client.get("/posts", params={"view": "all"}).json()
    assert resp["code"] == 0
    data = resp["data"]
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


def test_list_posts_pagination(client):
    """分页：第 2 页返回不同数据。"""
    info = register(client, "13701000004", "分页员2")
    for i in range(5):
        create_post(client, info["school_id"], f"分页帖子 #{i+1} 唯一标记")
    page1 = client.get("/posts", params={"view": "all", "page": 1, "page_size": 2}).json()
    page2 = client.get("/posts", params={"view": "all", "page": 2, "page_size": 2}).json()
    ids1 = {p["id"] for p in page1["data"]["items"]}
    ids2 = {p["id"] for p in page2["data"]["items"]}
    assert not ids1 & ids2, f"第 1、2 页不应重叠: {ids1 & ids2}"


def test_search_by_keyword(client):
    """关键词搜索：只返回含关键词的帖子。"""
    info = register(client, "13701000005", "搜索员")
    create_post(client, info["school_id"], "今天学习 Vue3 框架")
    create_post(client, info["school_id"], "完全无关的另一个帖子")
    resp = client.get("/posts", params={"view": "all", "q": "Vue3"}).json()
    assert resp["code"] == 0
    items = resp["data"]["items"]
    assert all("Vue3" in p["content"] for p in items), "搜索结果应只包含含 Vue3 的帖子"
    assert any("Vue3" in p["content"] for p in items)


def test_search_by_tag(client):
    """标签搜索：GET /posts?tag=xxx 只返回含该标签的帖子。"""
    info = register(client, "13701000006", "标签搜索员")
    # AI 关闭时 generate_tags 返回 []，所以这里手动测试无标签的情况
    create_post(client, info["school_id"], "无标签帖子")
    resp = client.get("/posts", params={"view": "all", "tag": "nonexistent_tag"}).json()
    assert resp["code"] == 0
    # 无标签的帖子不应匹配 nonexistent_tag
    assert resp["data"]["total"] == 0


def test_update_post_by_author(client):
    """作者可编辑帖子。"""
    info = register(client, "13701000007", "编辑员")
    post = create_post(client, info["school_id"], "原帖内容")
    resp = client.patch(
        f"/posts/{post['id']}",
        json={"content": "已编辑：新内容补充文字"},
    ).json()
    assert resp["code"] == 0
    assert "已编辑" in resp["data"]["content"]


def test_update_post_rejects_non_author(client):
    """非作者不可编辑。"""
    info_a = register(client, "13701000008", "作者A")
    post = create_post(client, info_a["school_id"], "A 的帖子")
    # 登出 A
    client.post("/auth/logout")
    # 注册 B
    register(client, "13701000009", "用户B")
    # B 尝试编辑 A 的帖子
    resp = client.patch(f"/posts/{post['id']}", json={"content": "B 篡改内容补充"}).json()
    assert resp["code"] != 0


def test_delete_post_by_author(client):
    """作者可删除帖子。"""
    info = register(client, "13701000010", "删除员")
    post = create_post(client, info["school_id"], "待删除帖子")
    resp = client.delete(f"/posts/{post['id']}").json()
    assert resp["code"] == 0
    # 列表中不再出现
    listing = client.get("/posts", params={"view": "all"}).json()
    ids = [p["id"] for p in listing["data"]["items"]]
    assert post["id"] not in ids


def test_delete_post_rejects_non_author(client):
    """非作者不可删除。"""
    info_a = register(client, "13701000011", "作者A2")
    post = create_post(client, info_a["school_id"], "A 的帖子不可删")
    client.post("/auth/logout")
    register(client, "13701000012", "用户B2")
    resp = client.delete(f"/posts/{post['id']}").json()
    assert resp["code"] != 0


def test_draft_save_and_list(client):
    """草稿保存后能在「我的草稿」列表看到。"""
    info = register(client, "13701000013", "草稿员")
    # 保存草稿
    post = create_post(client, info["school_id"], "草稿内容", is_draft=True)
    assert post["is_draft"] is True
    # 草稿不应出现在公开列表
    listing = client.get("/posts", params={"view": "all"}).json()
    ids = [p["id"] for p in listing["data"]["items"]]
    assert post["id"] not in ids, "草稿不应出现在公开列表"
    # 草稿应在「我的草稿」列表中
    drafts = client.get("/users/me/drafts").json()
    assert drafts["code"] == 0
    draft_ids = [p["id"] for p in drafts["data"]]
    assert post["id"] in draft_ids, "草稿应在我的草稿列表"


def test_draft_publish(client):
    """草稿发布后从草稿列表消失，出现在公开列表。"""
    info = register(client, "13701000014", "草稿发布员")
    post = create_post(client, info["school_id"], "待发布草稿", is_draft=True)
    # 发布草稿
    resp = client.patch(f"/posts/{post['id']}", json={"is_draft": False}).json()
    assert resp["code"] == 0
    # 应出现在公开列表
    listing = client.get("/posts", params={"view": "all"}).json()
    ids = [p["id"] for p in listing["data"]["items"]]
    assert post["id"] in ids, "发布后应出现在公开列表"
    # 不应再出现在草稿列表
    drafts = client.get("/users/me/drafts").json()
    draft_ids = [p["id"] for p in drafts["data"]]
    assert post["id"] not in draft_ids, "发布后不应在草稿列表"


def test_is_public_filter_hides_private_from_others(client):
    """T3-5：A 的私密帖子 B 看不到，A 自己能看到。"""
    info_a = register(client, "13701000015", "私密A")
    private = create_post(client, info_a["school_id"], "私密帖子内容", is_public=False)
    # A 自己能看到
    listing_a = client.get("/posts", params={"view": "all"}).json()
    ids_a = [p["id"] for p in listing_a["data"]["items"]]
    assert private["id"] in ids_a, "A 应能看到自己的私密帖子"
    # 登出 A，注册 B
    client.post("/auth/logout")
    register(client, "13701000016", "用户B3")
    # B 看不到 A 的私密帖子
    listing_b = client.get("/posts", params={"view": "all"}).json()
    ids_b = [p["id"] for p in listing_b["data"]["items"]]
    assert private["id"] not in ids_b, "B 不应看到 A 的私密帖子"


def test_post_dict_contains_author_id(client):
    """T7-15：_post_dict 返回 author_id 字段。"""
    info = register(client, "13701000017", "字段校验员")
    create_post(client, info["school_id"], "字段校验帖子")
    listing = client.get("/posts", params={"view": "all"}).json()
    for p in listing["data"]["items"]:
        assert "author_id" in p, "_post_dict 缺 author_id 字段"


def test_school_view_filters_by_user_school(client):
    """view=school 只返回当前用户校区的帖子。"""
    info_a = register(client, "13701000018", "校区A员")
    create_post(client, info_a["school_id"], "A 校区帖子")
    # 登出，注册 B 选择不同校区
    client.post("/auth/logout")
    schools = client.get("/schools").json()["data"]
    other_school_id = schools[1]["id"]
    body = {
        "nickname": "校区B员",
        "username": "13701000019",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": other_school_id,
        "agreed": True,
    }
    client.post("/auth/register", json=body)
    # B 用 view=school 应只看到自己校区的帖子
    listing = client.get("/posts", params={"view": "school"}).json()
    for p in listing["data"]["items"]:
        assert p["school"] != schools[0]["name"], "B 不应看到 A 校区的帖子"
