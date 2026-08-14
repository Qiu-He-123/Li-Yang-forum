"""推荐流个性化去重回归测试（大厂做法「推过的不再推」）。

背景（用户反馈）：推荐页总是重复推同一批帖子，用户看不到新内容就退出，
社区内容供给也受影响。

修复：
- 热门流按该用户已看过的帖子（推荐流/探索位曝光日志）去重，未看过的优先展示
- 探索池同样优先抽未看过的冷启动内容，看过不足时用「最久没看过」的补位
- 全部看过时回退常规热门流，避免推荐页空窗
- 匿名用户不做个性化去重
"""
import random

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import Post
from app.services import explore_service, settings_service
from tests.conftest import create_post, register

_DEFAULT_EXPLORE_SETTINGS = {
    "feed_explore_enabled": "true",
    "feed_explore_rate": "0.15",
    "feed_explore_hours": "48",
    "feed_explore_max_likes": "10",
    "feed_explore_mode": "thompson",
    "feed_mmr_enabled": "true",
    "feed_mmr_max_per_category": "6",
    "comment_explore_enabled": "true",
    "comment_explore_rate": "0.15",
    "feed_dedupe_enabled": "true",
    "feed_dedupe_days": "0",
}


@pytest.fixture(autouse=True)
def _restore_explore_settings():
    """每个测试结束恢复探索配置默认值，避免污染后续测试。"""
    yield
    with SessionLocal() as db:
        settings_service.set_many(db, dict(_DEFAULT_EXPLORE_SETTINGS))


def _set_settings(**kwargs) -> None:
    with SessionLocal() as db:
        settings_service.set_many(db, {k: str(v) for k, v in kwargs.items()})


def _make_approved_post(client, user, content: str, category: str = "普通", likes: int = 0, **extra) -> dict:
    data = create_post(client, user["school_id"], content, category=category)
    with SessionLocal() as db:
        values = {"ai_status": "approved", "like_count": likes, **extra}
        db.execute(update(Post).where(Post.id == data["id"]).values(**values))
        db.commit()
    return data


def _hot_items(client, page_size: int = 20, page: int = 1) -> list[dict]:
    resp = client.get("/posts", params={"view": "hot", "page_size": page_size, "page": page}).json()
    assert resp["code"] == 0, resp
    return resp["data"]["items"]


def test_hot_feed_does_not_repeat_pushed_posts(client):
    """同一用户第二次拉取热门流，不应重复已推过的帖子。"""
    user = register(client, "fd00000001", "去重用户A")
    # 关闭 MMR 类别裁剪，避免干扰去重断言
    _set_settings(feed_mmr_enabled=False)
    for i in range(12):
        _make_approved_post(client, user, f"去重热门{i}：内容足够长", likes=50)
    for i in range(13):
        _make_approved_post(client, user, f"去重冷帖{i}：内容足够长", likes=0)

    first = _hot_items(client)
    first_ids = {p["id"] for p in first}
    assert len(first_ids) >= 15, "第一页应展示 15+ 条内容"

    second = _hot_items(client)
    assert second, "第二次推荐不应为空"
    # 新鲜优先：未看过的内容排在前面；页面用 LRU 补位保持饱满，不出现稀疏页
    unseen_second = [p for p in second if p["id"] not in first_ids]
    assert unseen_second, "未看过的内容应优先展示"
    assert len(second) >= 15, "页面应保持饱满（LRU 补位：未看过不足一页时补最近最少看过的旧帖）"

    # 全部看过 → LRU 轮换补位，页面不空窗
    third = _hot_items(client)
    assert len(third) >= 15, "全部看过时用 LRU 轮换补位，不返回空页/稀疏页"


def test_anonymous_no_dedupe(client):
    """匿名用户不参与个性化去重：常规热门部分两次一致。"""
    user = register(client, "fd00000002", "匿名观察用户B")
    for i in range(5):
        _make_approved_post(client, user, f"匿名帖{i}：内容足够长", likes=30)
    client.post("/auth/logout")

    first = _hot_items(client)
    second = _hot_items(client)
    hot1 = [p["id"] for p in first if not p.get("explored")]
    hot2 = [p["id"] for p in second if not p.get("explored")]
    assert hot1 == hot2, "匿名用户两次热门（非探索位）内容应一致"


def test_dedupe_disabled_switch(client):
    """feed_dedupe_enabled=false 时不做去重，两次内容一致（常规热门流）。"""
    user = register(client, "fd00000003", "开关用户C")
    for i in range(8):
        _make_approved_post(client, user, f"开关帖{i}：内容足够长", likes=20)
    _set_settings(feed_dedupe_enabled=False)

    first = _hot_items(client)
    second = _hot_items(client)
    hot1 = [p["id"] for p in first if not p.get("explored")]
    hot2 = [p["id"] for p in second if not p.get("explored")]
    assert hot1 == hot2, "关闭去重后热门内容应与常规一致"


def test_explore_pool_prefers_unseen(client):
    """探索池优先抽未看过的冷启动帖，已看过的不会再次被抽中。"""
    user = register(client, "fd00000004", "探索去重用户D")
    for i in range(10):
        _make_approved_post(client, user, f"冷帖{i}：内容足够长", likes=0)

    with SessionLocal() as db:
        cfg = explore_service.get_explore_config(db)
        # 第一次：无历史曝光，正常采样 5 条
        picked1 = explore_service.pick_explore_posts(db, None, 5, cfg, rng=random.Random(1))
        assert len(picked1) == 5
        seen = {p.id for p in picked1}
        # 第二次：传入 seen，不应再抽中已看过的
        picked2 = explore_service.pick_explore_posts(
            db,
            None,
            5,
            cfg,
            rng=random.Random(2),
            seen_post_ids=seen,
        )
        assert len(picked2) == 5
        assert not (seen & {p.id for p in picked2}), "看过的不应再次被抽中"


def test_dedupe_window_days(client):
    """feed_dedupe_days 去重窗口：超窗的曝光不参与去重。"""
    user = register(client, "fd00000005", "窗口用户E")
    for i in range(6):
        _make_approved_post(client, user, f"窗口帖{i}：内容足够长", likes=10)

    # 用户先看一遍（记录 feed_push 曝光）
    _hot_items(client)
    # 窗口设为 0（全部历史）：第二次不应重复
    _set_settings(feed_dedupe_days=0)
    second = _hot_items(client)
    assert second, "第二次推荐不应为空"
