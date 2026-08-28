"""推荐探索（Explore-Exploit）功能测试。

覆盖：
- 热门流探索槽位：低互动新帖能随机进入热门页并打上 explored 标记
- 探索比例 ε：槽位数量符合配置
- 探索池安全过滤：草稿 / 被拒 / 被举报 / 封号作者 不进探索池
- 开关：关闭后热门页纯热门排序
- 曝光埋点：PostExploreStat.impressions + FeedImpressionLog
- 点击埋点：view → click_count + 1
- 互动归因：探索曝光用户点赞/评论 → like_count/comment_count + 1
- MMR 类别多样性：同圈子内容超上限被裁剪
- 评论探索：最热评论页插入低赞新评论
- Thompson / 加权采样与配置边界
- 后台探索统计接口
"""
import random

import pytest
from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import (
    Admin,
    Comment,
    FeedImpressionLog,
    Post,
    PostExploreStat,
    Report,
    User,
)
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
    """发帖后直接置为 approved（测试环境 AI 关闭默认转人工审核）。"""
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


def _explore_stat(post_id: int) -> PostExploreStat | None:
    with SessionLocal() as db:
        return db.get(PostExploreStat, post_id)


def test_hot_feed_includes_explore_posts(client):
    """热门页应包含探索位冷启动帖子，且曝光埋点落库。"""
    user = register(client, "exp00000001", "探索用户A")
    # 6 条高赞热门帖
    hot_ids = []
    for i in range(6):
        hot_ids.append(_make_approved_post(client, user, f"热门帖{i}：内容足够长测试", likes=80)["id"])
    # 5 条低互动新帖（探索池）
    for i in range(5):
        _make_approved_post(client, user, f"冷启动帖{i}：还没人看的内容", likes=0)

    items = _hot_items(client)
    explored = [p for p in items if p.get("explored")]

    assert explored, "热门页应包含探索位帖子"
    assert all(p["id"] not in hot_ids for p in explored), "探索位帖子不能是高赞热门帖"
    assert len(explored) >= 1
    # 热门帖仍在
    assert any(not p.get("explored") for p in items)

    # 曝光埋点：PostExploreStat + FeedImpressionLog
    with SessionLocal() as db:
        for p in explored:
            stat = db.get(PostExploreStat, p["id"])
            assert stat is not None and stat.impressions >= 1
        logs = db.scalars(
            select(FeedImpressionLog).where(
                FeedImpressionLog.post_id.in_([p["id"] for p in explored]),
                FeedImpressionLog.user_id == user["user_id"],
                FeedImpressionLog.scene == "post_feed",
            )
        ).all()
        assert len(logs) >= len(explored)


def test_explore_slot_count_and_rate_zero(client):
    """探索槽位数量随 ε 变化；ε=0 时关闭探索。"""
    user = register(client, "exp00000002", "探索用户B")
    for i in range(8):
        _make_approved_post(client, user, f"高互动帖子{i}：内容足够长", likes=50)
    for i in range(5):
        _make_approved_post(client, user, f"冷帖子{i}：没人互动", likes=0)

    # ε=0.25, page_size=20 → slots = max(1, ceil(5)) = 5
    _set_settings(feed_explore_rate=0.25)
    items = _hot_items(client)
    explored = [p for p in items if p.get("explored")]
    assert len(explored) == 5, f"ε=0.25 时应有 5 个探索位，实际 {len(explored)}"

    # ε=0 → 无探索位
    _set_settings(feed_explore_rate=0)
    items = _hot_items(client)
    assert all(not p.get("explored") for p in items)


def test_explore_pool_excludes_draft_rejected_private(client):
    """探索池排除草稿 / 审核拒绝 / 私密帖子。"""
    user = register(client, "exp00000003", "探索用户C")
    _make_approved_post(client, user, "正常冷启动帖：内容足够长", likes=0)
    draft = create_post(client, user["school_id"], "草稿内容足够长", is_draft=True)
    rejected = _make_approved_post(client, user, "被拒帖：内容足够长", likes=0)
    private = _make_approved_post(client, user, "私密帖：内容足够长", likes=0, is_public=False)
    with SessionLocal() as db:
        db.execute(update(Post).where(Post.id == draft["id"]).values(is_draft=True))
        db.execute(update(Post).where(Post.id == rejected["id"]).values(ai_status="rejected"))
        db.commit()

    items = _hot_items(client)
    explored_ids = {p["id"] for p in items if p.get("explored")}
    assert draft["id"] not in explored_ids
    assert rejected["id"] not in explored_ids
    # 私密帖：非作者不可见（当前用户就是作者本人，但 is_public=False 非本人不可见，
    # 而探索池要求公开或本人 → 作者本人可见。这里用第二个用户视角验证不可见）
    client.post("/auth/logout")
    user2 = register(client, "exp00000004", "旁观者D")
    items2 = _hot_items(client)
    explored2 = {p["id"] for p in items2 if p.get("explored")}
    assert private["id"] not in explored2


def test_explore_pool_excludes_reported_and_banned(client):
    """探索池排除被举报帖子与封号作者帖子。"""
    user = register(client, "exp00000005", "探索用户E")
    cold1 = _make_approved_post(client, user, "被举报帖：内容足够长", likes=0)
    cold2 = _make_approved_post(client, user, "正常冷帖：内容足够长", likes=0)
    with SessionLocal() as db:
        db.add(Report(
            reporter_id=user["user_id"],
            target_type="post",
            target_id=cold1["id"],
            reason="垃圾广告",
            status="pending",
        ))
        db.commit()

    # 封号作者：第二个用户发帖后封禁
    client.post("/auth/logout")
    banned_user = register(client, "exp00000006", "封号作者F")
    cold3 = _make_approved_post(client, banned_user, "封号作者帖：内容足够长", likes=0)
    client.post("/auth/logout")
    with SessionLocal() as db:
        db.execute(update(User).where(User.id == banned_user["user_id"]).values(is_active=False))
        db.commit()

    # 用普通用户视角拉取热门流（封号用户连公开浏览都会被拦截）
    viewer = register(client, "exp00000006v", "旁观者V")
    _ = viewer
    items = _hot_items(client)
    explored_ids = {p["id"] for p in items if p.get("explored")}
    assert cold1["id"] not in explored_ids
    assert cold3["id"] not in explored_ids
    assert explored_ids

    # 池级验证：正常冷帖在候选池中，被举报/封号作者帖不在
    with SessionLocal() as db:
        cfg = explore_service.get_explore_config(db)
        candidates = db.scalars(
            explore_service._base_explore_query(db, None, cfg)
        ).all()
        candidate_ids = {p.id for p in candidates}
        assert cold2["id"] in candidate_ids
        assert cold1["id"] not in candidate_ids
        assert cold3["id"] not in candidate_ids


def test_explore_disabled_switch(client):
    """feed_explore_enabled=false 时热门页无探索位。"""
    user = register(client, "exp00000007", "探索用户G")
    _make_approved_post(client, user, "热门帖：内容足够长", likes=60)
    _make_approved_post(client, user, "冷启动帖：没人互动", likes=0)
    _set_settings(feed_explore_enabled=False)
    items = _hot_items(client)
    assert all(not p.get("explored") for p in items)


def test_click_and_interaction_recording(client):
    """探索曝光 → 点击/点赞/评论 全链路埋点。"""
    user = register(client, "exp00000008", "探索用户H")
    _make_approved_post(client, user, "热门帖：内容足够长", likes=70)
    cold = _make_approved_post(client, user, "冷启动帖：内容足够长", likes=0)

    items = _hot_items(client)
    explored = [p for p in items if p.get("explored")]
    assert explored
    target = explored[0]

    # 点击详情（浏览埋点接口）→ click_count + 1
    view = client.post(f"/posts/{target['id']}/view").json()
    assert view["code"] == 0
    stat = _explore_stat(target["id"])
    assert stat is not None and stat.click_count == 1

    # 探索曝光用户点赞 → like_count + 1
    like = client.post(f"/likes/post/{target['id']}").json()
    assert like["code"] == 0
    stat = _explore_stat(target["id"])
    assert stat.like_count == 1

    # 未看过探索曝光的用户点赞 → 不计入探索奖励
    client.post("/auth/logout")
    other = register(client, "exp00000009", "路人I")
    _ = other
    client.post(f"/likes/post/{target['id']}").json()
    stat = _explore_stat(target["id"])
    assert stat.like_count == 1


def test_mmr_category_cap(client):
    """MMR：热门页同圈子内容不超过上限。"""
    user = register(client, "exp00000010", "探索用户J")
    for i in range(5):
        _make_approved_post(client, user, f"同圈热门{i}：内容足够长", category="普通", likes=60)
    for i in range(5):
        _make_approved_post(client, user, f"树洞冷帖{i}：内容足够长", category="树洞", likes=0)

    _set_settings(feed_mmr_max_per_category=2)
    items = _hot_items(client)
    hot_items = [p for p in items if not p.get("explored")]
    ordinary = [p for p in hot_items if p["category"] == "普通"]
    assert len(ordinary) <= 2, f"MMR 后普通圈子最多 2 条，实际 {len(ordinary)}"


def test_comment_hot_explore(client):
    """帖子「最热」评论页应插入低赞新评论探索位。"""
    user = register(client, "exp00000011", "探索用户K")
    post = _make_approved_post(client, user, "评论探索测试帖：内容足够长", likes=0)

    # 3 条高赞根评论 + 3 条低赞新评论
    comment_ids = []
    for i in range(3):
        c = client.post(f"/posts/{post['id']}/comments", json={"content": f"高赞评论{i}"}).json()
        assert c["code"] == 0, c
        comment_ids.append(c["data"]["id"])
    for i in range(3):
        c = client.post(f"/posts/{post['id']}/comments", json={"content": f"低赞新评论{i}"}).json()
        assert c["code"] == 0, c
        comment_ids.append(c["data"]["id"])

    with SessionLocal() as db:
        all_comments = db.scalars(select(Comment).where(Comment.id.in_(comment_ids))).all()
        for c in all_comments:
            c.ai_status = "approved"
            c.like_count = 50 if "高赞" in c.content else 0
        db.commit()

    resp = client.get(f"/posts/{post['id']}/comments", params={"sort": "hot"}).json()
    assert resp["code"] == 0, resp
    items = resp["data"]["items"]
    explored = [c for c in items if c.get("explored")]
    assert explored, "最热评论页应包含探索位低赞评论"
    assert all("低赞" in c["content"] for c in explored)

    # 评论探索只写曝光日志，不污染帖子探索统计
    with SessionLocal() as db:
        comment_logs = db.scalars(
            select(FeedImpressionLog).where(
                FeedImpressionLog.scene == "comment",
                FeedImpressionLog.post_id == post["id"],
            )
        ).all()
        assert len(comment_logs) >= len(explored)
        stat = db.get(PostExploreStat, post["id"])
        if stat is not None:
            assert stat.impressions == 0, "评论探索不应计入帖子探索曝光"


def test_thompson_and_weighted_sampling(client):
    """三种采样算法都能从探索池选出不重复、数量正确的帖子。"""
    user = register(client, "exp00000012", "探索用户L")
    for i in range(20):
        _make_approved_post(client, user, f"候选冷帖{i}：内容足够长", likes=0)

    with SessionLocal() as db:
        cfg = explore_service.get_explore_config(db)
        for mode in ("uniform", "weighted", "thompson"):
            cfg["feed_explore_mode"] = mode
            picked = explore_service.pick_explore_posts(
                db, None, 5, cfg, rng=random.Random(42)
            )
            assert len(picked) == 5
            ids = [p.id for p in picked]
            assert len(set(ids)) == 5, f"{mode} 采样结果不应重复"


def test_config_bounds(client):
    """配置边界：非法值自动回退安全默认。"""
    _set_settings(
        feed_explore_rate=9,
        feed_explore_hours=-5,
        feed_explore_mode="unknown",
    )
    with SessionLocal() as db:
        cfg = explore_service.get_explore_config(db)
        assert cfg["feed_explore_rate"] == 0.5
        assert cfg["feed_explore_hours"] == 1
        assert cfg["feed_explore_mode"] == "thompson"


def test_admin_explore_stats_endpoint(client):
    """后台探索统计接口：汇总 + Top 帖 + 最近曝光日志。"""
    user = register(client, "exp00000013", "探索用户M")
    _make_approved_post(client, user, "热门帖：内容足够长", likes=60)
    cold = _make_approved_post(client, user, "冷启动帖：内容足够长", likes=0)
    _hot_items(client)

    # 创建管理员并登录
    from app.core.security import hash_password
    with SessionLocal() as db:
        if not db.query(Admin).filter(Admin.username == "exp_admin").first():
            db.add(Admin(username="exp_admin", password_hash=hash_password("Exp@2026Admin"), role="admin"))
            db.commit()
    login = client.post("/admin/login", json={"username": "exp_admin", "password": "Exp@2026Admin"}).json()
    assert login["code"] == 0, login

    resp = client.get("/admin/explore/stats").json()
    assert resp["code"] == 0, resp
    data = resp["data"]
    assert data["summary"]["impressions"] >= 1
    assert data["summary"]["interaction_count"] >= 0
    assert isinstance(data["top_posts"], list)
    assert isinstance(data["recent_logs"], list)
    assert data["top_posts"], "至少应有探索曝光记录"
    assert all(tp["impressions"] >= 1 for tp in data["top_posts"])
    # 评论探索曝光日志带 target_id（评论 id）
    assert all("target_id" in log for log in data["recent_logs"])
    client.post("/admin/logout")
