"""AI 审核降级与发帖规则回归测试。

覆盖：
- AI 不可用时（未配置/无余额/调用失败）不再直接放行，帖子转人工审核
- 含图片的帖子默认进入人工审核（图片不走 AI 审核）
- 发帖最少字数：短内容（如"12"、"......"）被拦截
"""
from tests.conftest import register


def test_post_goes_manual_review_when_ai_unavailable(client):
    """AI 不可用 → 帖子转人工审核并通知作者，而不是直接放行。"""
    info = register(client, "13709000001", "降级审核员")
    resp = client.post(
        "/posts",
        json={
            "content": "这是一段完全正常的校园分享内容",
            "school_id": info["school_id"],
            "category": "普通",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert resp["code"] == 0
    post = resp["data"]
    # 测试环境 AI 关闭 → 必须进入人工审核，不能 approved
    assert post["ai_status"] == "manual_review"
    assert "人工审核" in (post["reject_reason"] or "")

    # 作者收到系统通知
    notifs = client.get("/notifications", params={"type": "system"}).json()["data"]
    assert any("人工审核" in n["title"] for n in notifs["items"])


def test_post_with_image_goes_manual_review(client):
    """含图片的帖子默认进入人工审核（图片不走 AI 审核）。"""
    info = register(client, "13709000002", "图片审核员")
    resp = client.post(
        "/posts",
        json={
            "content": "这是一条带图片的校园动态分享内容",
            "school_id": info["school_id"],
            "category": "普通",
            "image_urls": ["/uploads/fake-test.png"],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert resp["code"] == 0
    assert resp["data"]["ai_status"] == "manual_review"
    assert "图片" in (resp["data"]["reject_reason"] or "")


def test_short_post_rejected(client):
    """发帖最少字数：短内容被拦截。"""
    info = register(client, "13709000003", "短内容员")
    resp = client.post(
        "/posts",
        json={
            "content": "12",
            "school_id": info["school_id"],
            "category": "普通",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert resp["code"] != 0
    assert "至少" in resp["msg"]


def test_punctuation_only_post_rejected(client):
    """纯标点（......）等灌水内容被最少字数拦截。"""
    info = register(client, "13709000004", "标点员")
    resp = client.post(
        "/posts",
        json={
            "content": "......",
            "school_id": info["school_id"],
            "category": "普通",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert resp["code"] != 0


def test_title_and_content_both_count_for_min_length(client):
    """标题 + 正文合计达到最少字数即可发布。"""
    info = register(client, "13709000005", "标题补字员")
    resp = client.post(
        "/posts",
        json={
            "title": "校园通知",
            "content": "今天下午三点在操场集合",
            "school_id": info["school_id"],
            "category": "普通",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": True,
        },
    ).json()
    assert resp["code"] == 0
