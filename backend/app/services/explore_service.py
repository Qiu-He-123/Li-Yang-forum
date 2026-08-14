"""推荐探索（Explore-Exploit）业务逻辑层。

大厂推荐系统通用的「探索-利用」闭环，本模块实现三层能力：

1. ε-Greedy 探索槽位
   热门流每页按 ε 比例插入「探索池」冷启动内容（低互动 + 新鲜 + 已过审），
   打破「热门永远霸榜」的马太效应，给低权重内容随机曝光机会。

2. 采样算法（后台可切换）
   - uniform   均匀随机：最朴素的探索
   - weighted  加权随机：新鲜度 + 低互动权重，越冷越容易被抽中
   - thompson  Thompson 采样：用 Beta 分布建模每个帖子的「好坏后验」，
               曝光无互动会自动降低权重，互动好会自动提高（反馈闭环，推荐）

3. MMR 类别多样性
   热门页同一圈子的内容超过上限时自动裁剪，防止首页被单一圈子刷屏。

配套闭环：
- 探索曝光 → post_explore_stats.impressions + 1 + feed_impression_logs 落日志
- 点击详情 → click_count + 1（CTR 指标）
- 点赞 / 评论 → like_count / comment_count + 1（奖励信号，带 7 天归因窗口）
- 后台「推荐探索」页实时展示曝光 / 点击 / CTR / 互动，并支持动态调参
"""
import math
import random
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.time_utils import now_utc
from app.models import (
    Comment,
    FeedImpressionLog,
    Post,
    PostExploreStat,
    Report,
    User,
)
from app.services import settings_service

# 探索池单次最大候选数（性能保护，避免全表扫描拖慢热门流）
_MAX_POOL_CANDIDATES = 300
# 互动归因窗口：探索曝光后 N 天内发生的互动算作该帖子的探索奖励
_INTERACTION_ATTRIBUTION_DAYS = 7
# 被举报帖子保护：近 30 天累计举报 >= 3 次，或存在 pending 举报，禁止进入探索池
_REPORT_BLOCK_TOTAL = 3
_REPORT_BLOCK_DAYS = 30

# 探索场景常量
SCENE_POST_FEED = "post_feed"
SCENE_COMMENT = "comment"
# 推荐流（热门页常规内容）曝光：作为「推过的不再推」个性化去重的数据来源。
# 与 SCENE_POST_FEED（探索位曝光）分开，避免把推荐流常规曝光计入探索统计。
SCENE_FEED_PUSH = "feed_push"

# 去重统计涉及的曝光场景（帖子场景）
_DEDUPE_SCENES = (SCENE_POST_FEED, SCENE_FEED_PUSH)


def _clamp_rate(raw: str, default: float = 0.15) -> float:
    """解析并限制探索比例 ε ∈ [0, 0.5]。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(0.0, min(0.5, value))


def _clamp_mode(raw: str) -> str:
    mode = (raw or "thompson").strip().lower()
    return mode if mode in {"uniform", "weighted", "thompson"} else "thompson"


def get_explore_config(db: Session) -> dict:
    """读取全部探索推荐配置（含边界保护，非法值自动回退默认）。"""
    return {
        "feed_explore_enabled": settings_service.get_bool(db, "feed_explore_enabled", True),
        "feed_explore_rate": _clamp_rate(settings_service.get_setting(db, "feed_explore_rate", "0.15")),
        "feed_explore_hours": max(1, settings_service.get_int(db, "feed_explore_hours", 48)),
        "feed_explore_max_likes": max(0, settings_service.get_int(db, "feed_explore_max_likes", 10)),
        "feed_explore_mode": _clamp_mode(settings_service.get_setting(db, "feed_explore_mode", "thompson")),
        "feed_mmr_enabled": settings_service.get_bool(db, "feed_mmr_enabled", True),
        "feed_mmr_max_per_category": max(1, settings_service.get_int(db, "feed_mmr_max_per_category", 6)),
        "comment_explore_enabled": settings_service.get_bool(db, "comment_explore_enabled", True),
        "comment_explore_rate": _clamp_rate(settings_service.get_setting(db, "comment_explore_rate", "0.15")),
        # 个性化去重（大厂做法「推过的不再推」）：
        # - feed_dedupe_enabled: 推荐流已推给该用户的帖子不再重复推荐，未看过的优先曝光
        # - feed_dedupe_days: 去重窗口（天，0=全部历史）；超过窗口后可再次推荐
        "feed_dedupe_enabled": settings_service.get_bool(db, "feed_dedupe_enabled", True),
        "feed_dedupe_days": max(0, settings_service.get_int(db, "feed_dedupe_days", 0)),
    }


def explore_slot_count(page_size: int, rate: float) -> int:
    """计算一页里应分配几个探索槽位。

    规则：
    - rate=0 或 page_size<=1 → 0
    - 最多占半页（避免探索内容喧宾夺主）
    - 至少 1 个（探索开关打开时保证低权重内容有机会出现）
    """
    if rate <= 0 or page_size <= 1:
        return 0
    slots = max(1, math.ceil(page_size * rate))
    return min(slots, page_size // 2)


def _exclude_reported_query(db: Session) -> list[select]:
    """构造排除被举报帖子的两个标量子查询。

    - 存在 pending（待处理）举报的帖子
    - 近 30 天累计举报 >= 3 次的帖子
    """
    pending_ids = (
        select(Report.target_id)
        .where(Report.target_type == "post", Report.status == "pending")
    )
    cutoff = now_utc() - timedelta(days=_REPORT_BLOCK_DAYS)
    repeated_ids = (
        select(Report.target_id)
        .where(Report.target_type == "post", Report.created_at >= cutoff)
        .group_by(Report.target_id)
        .having(func.count(Report.id) >= _REPORT_BLOCK_TOTAL)
    )
    return [pending_ids, repeated_ids]


def _base_explore_query(
    db: Session,
    user: User | None,
    config: dict,
    exclude_ids: set[int] | None = None,
):
    """探索池基础查询：与帖子流可见性一致，另加冷启动/安全过滤。

    可见性：非草稿、非隐藏、公开或本人、AI 必须已过审（探索是「对外推广」，
    被拒/审核中的帖子即使作者本人可见，也绝不进入探索池）。
    安全：作者未被封禁；被举报帖子不进探索池。
    冷启动：最近 feed_explore_hours 小时内发布，like_count <= 上限。
    """
    query = (
        select(Post)
        .join(User, User.id == Post.author_id)
        .where(Post.is_draft.is_(False))
        .where(Post.is_hidden_by_unverify.is_(False))
    )
    if user is not None:
        query = query.where(or_(Post.is_public.is_(True), Post.author_id == user.id))
    else:
        query = query.where(Post.is_public.is_(True))
    # 探索池只推广已过审内容
    query = query.where(Post.ai_status == "approved")

    # 作者封禁过滤（ban_until 未过期或 is_active=False 均排除）
    query = query.where(User.is_active.is_(True)).where(
        or_(User.ban_until.is_(None), User.ban_until <= now_utc())
    )

    # 冷启动窗口 + 低互动门槛
    since = now_utc() - timedelta(hours=config["feed_explore_hours"])
    query = query.where(Post.created_at >= since)
    query = query.where(Post.like_count <= config["feed_explore_max_likes"])

    # 被举报保护
    for sub in _exclude_reported_query(db):
        query = query.where(Post.id.not_in(sub))

    if exclude_ids:
        query = query.where(Post.id.not_in(exclude_ids))
    return query


def _thompson_sample(alpha: int, beta: int, rng: random.Random) -> float:
    """Thompson 采样：Beta(1+α, 1+β) 抽一个「质量分」。

    - 无数据帖子：Beta(1,1) 均匀分布 → 公平竞争
    - 互动好的帖子：α 大 → 分数右移，更容易再被抽中
    - 曝光多但没互动的帖子：β 大 → 分数左移，自动降温
    """
    return rng.betavariate(int(alpha) + 1, int(beta) + 1)


def _weighted_sample(
    items: list[Post],
    weights: list[float],
    k: int,
    rng: random.Random,
) -> list[Post]:
    """按权重不放回抽样（Efraimidis-Spirakis 指数竞赛法）。"""
    scored = [
        (rng.random() ** (1.0 / max(w, 1e-9)), item)
        for item, w in zip(items, weights)
    ]
    scored.sort(reverse=True, key=lambda x: x[0])
    return [item for _, item in scored[:k]]


def get_seen_post_ids(db: Session, user_id: int, days: int = 0) -> set[int]:
    """该用户在推荐流中已经看过的帖子 id 集合（「推过的不再推」去重依据）。

    - 覆盖 post_feed（探索位曝光）与 feed_push（推荐流常规曝光）两个场景
    - days=0 表示全部历史；days>0 只统计最近 N 天内的曝光（超窗可再次推荐）
    """
    query = (
        select(FeedImpressionLog.post_id)
        .where(
            FeedImpressionLog.user_id == user_id,
            FeedImpressionLog.post_id.is_not(None),
            FeedImpressionLog.scene.in_(_DEDUPE_SCENES),
        )
        .distinct()
    )
    if days and days > 0:
        cutoff = now_utc() - timedelta(days=days)
        query = query.where(FeedImpressionLog.created_at >= cutoff)
    return set(db.scalars(query).all())


def get_seen_since_map(db: Session, user_id: int, days: int = 0) -> dict[int, datetime]:
    """每个已看帖子最近一次曝光时间（用于看过内容补位时的 LRU 排序）。"""
    query = (
        select(FeedImpressionLog.post_id, func.max(FeedImpressionLog.created_at))
        .where(
            FeedImpressionLog.user_id == user_id,
            FeedImpressionLog.post_id.is_not(None),
            FeedImpressionLog.scene.in_(_DEDUPE_SCENES),
        )
        .group_by(FeedImpressionLog.post_id)
    )
    if days and days > 0:
        cutoff = now_utc() - timedelta(days=days)
        query = query.where(FeedImpressionLog.created_at >= cutoff)
    return {pid: ts for pid, ts in db.execute(query).all()}


def _sample_from_pool(
    pool: list[Post],
    k: int,
    mode: str,
    config: dict,
    stats: dict[int, PostExploreStat],
    rng: random.Random,
) -> list[Post]:
    """从候选池按指定采样算法抽取 k 条。"""
    if k <= 0 or not pool:
        return []
    if len(pool) <= k:
        return pool

    if mode == "uniform":
        return rng.sample(pool, k)

    if mode == "weighted":
        # 权重 = 低互动红利 + 新鲜度红利：点赞越少、越新，越容易被抽中
        now = now_utc()
        since = now - timedelta(hours=config["feed_explore_hours"])
        total_hours = max(1, (now - since).total_seconds() / 3600)
        weights = []
        for p in pool:
            freshness = max(0.0, 1.0 - (now - p.created_at).total_seconds() / 3600 / total_hours)
            weights.append(1.0 / (1.0 + (p.like_count or 0)) + 0.5 * freshness)
        return _weighted_sample(pool, weights, k, rng)

    # thompson：Beta 采样后取 Top-N
    scored = []
    for p in pool:
        stat = stats.get(p.id)
        alpha = ((stat.like_count or 0) + (stat.comment_count or 0)) if stat else 0
        impressions = (stat.impressions or 0) if stat else 0
        beta = max(0, impressions - alpha)
        scored.append((_thompson_sample(alpha, beta, rng), p))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in scored[:k]]


def pick_explore_posts(
    db: Session,
    user: User | None,
    limit: int,
    config: dict,
    exclude_ids: set[int] | None = None,
    rng: random.Random | None = None,
    seen_post_ids: set[int] | None = None,
    seen_since: dict[int, datetime] | None = None,
) -> list[Post]:
    """从探索池中挑选 limit 条帖子（支持三种采样算法）。

    个性化去重（大厂做法「推过的不再推」）：
    - seen_post_ids: 该用户已看过的帖子 id 集合，未看过的候选优先被抽中
    - seen_since: 已看帖子最近曝光时间，未看过候选不足时用「最久没看过」的补位，
      避免探索位空窗，同时保证不立刻重复刚看过的内容
    """
    limit = max(0, int(limit))
    if limit <= 0:
        return []

    query = (
        _base_explore_query(db, user, config, exclude_ids)
        .order_by(desc(Post.created_at))
        .limit(_MAX_POOL_CANDIDATES)
    )
    candidates = list(db.scalars(query).all())
    if not candidates:
        return []
    if len(candidates) <= limit:
        return candidates

    rng = rng or random.Random()
    mode = config["feed_explore_mode"]
    stats: dict[int, PostExploreStat] = {}
    if mode == "thompson":
        stats = {
            s.post_id: s
            for s in db.scalars(
                select(PostExploreStat).where(PostExploreStat.post_id.in_([p.id for p in candidates]))
            ).all()
        }

    if seen_post_ids:
        unseen = [p for p in candidates if p.id not in seen_post_ids]
        seen = [p for p in candidates if p.id in seen_post_ids]
        if len(unseen) >= limit:
            return _sample_from_pool(unseen, limit, mode, config, stats, rng)
        if seen:
            # 未看过的全部保留；缺口用「看过」里最久没看过的补足
            if seen_since:
                seen = sorted(seen, key=lambda p: seen_since.get(p.id) or datetime.min)
            remaining = limit - len(unseen)
            return unseen + _sample_from_pool(seen, remaining, mode, config, stats, rng)

    return _sample_from_pool(candidates, limit, mode, config, stats, rng)


def merge_explore(
    hot_items: list[Post],
    explore_items: list[Post],
    user: User | None,
    page: int,
    rng: random.Random | None = None,
) -> list[Post]:
    """把探索帖随机插入热门列表的 N 个位置（保留热门相对顺序）。

    种子 = user_id + page，保证同一用户同一页刷新时位置稳定，翻页不抖动。
    """
    if not explore_items:
        return hot_items
    if not hot_items:
        return explore_items

    seed = ((user.id if user and user.id else 0) * 1000003 + int(page) * 1009) % (2**32)
    rng = rng or random.Random(seed)
    total = len(hot_items) + len(explore_items)
    positions = set(rng.sample(range(total), len(explore_items)))

    result: list[Post] = []
    hi = ei = 0
    for i in range(total):
        if i in positions and ei < len(explore_items):
            result.append(explore_items[ei])
            ei += 1
        elif hi < len(hot_items):
            result.append(hot_items[hi])
            hi += 1
        elif ei < len(explore_items):
            result.append(explore_items[ei])
            ei += 1
        else:
            result.append(hot_items[hi])
            hi += 1
    return result


def mmr_dedupe(posts: list[Post], max_per_category: int) -> list[Post]:
    """MMR 类别多样性：同圈子内容超过上限时裁剪，避免热门页刷屏。"""
    if max_per_category <= 0:
        return posts
    counts: dict[str, int] = {}
    kept: list[Post] = []
    for p in posts:
        cat = p.category or "default"
        if counts.get(cat, 0) < max_per_category:
            counts[cat] = counts.get(cat, 0) + 1
            kept.append(p)
    return kept


def record_feed_impressions(
    db: Session,
    post_ids: list[int],
    user_id: int | None,
    scene: str = SCENE_POST_FEED,
    page: int = 1,
    track_stats: bool = True,
    target_ids: list[int] | None = None,
) -> None:
    """记录探索曝光：帖子统计 impressions + 1，并写入曝光日志。

    track_stats=False 时只写曝光日志（用于评论探索等无独立统计表的场景），
    避免评论曝光被误计入帖子探索统计。
    失败不影响主流程（热门流照常返回），仅打日志。
    """
    if target_ids:
        # 带场景内目标时保留逐条记录（评论探索一个帖子可对应多条曝光）
        ids = [int(i) for i in post_ids]
    else:
        ids = list(dict.fromkeys(int(i) for i in post_ids))
    if not ids:
        return
    targets = target_ids or []
    targets += [None] * (len(ids) - len(targets))
    try:
        for idx, pid in enumerate(ids):
            if track_stats:
                stat = db.get(PostExploreStat, pid)
                if stat is None:
                    db.add(PostExploreStat(post_id=pid, impressions=1))
                else:
                    stat.impressions = (stat.impressions or 0) + 1
            db.add(FeedImpressionLog(
                post_id=pid,
                target_id=targets[idx],
                user_id=user_id,
                scene=scene,
                page=int(page),
            ))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[EXPLORE] record_feed_impressions failed: {}", exc)


def record_post_click(db: Session, post_id: int) -> None:
    """记录探索帖点击（进入详情）。仅统计有探索曝光的帖子。"""
    try:
        stat = db.get(PostExploreStat, post_id)
        if stat is None or (stat.impressions or 0) <= 0:
            return
        stat.click_count = (stat.click_count or 0) + 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[EXPLORE] record_post_click failed: {}", exc)


def record_interaction(db: Session, post_id: int, user_id: int, kind: str) -> None:
    """记录探索奖励互动（点赞 / 评论），带 7 天归因窗口。

    只有「近期在探索位看过这个帖子」的用户产生的互动才计入奖励，
    避免把自然流量互动错误归因到探索。
    """
    if kind not in {"like", "comment"}:
        return
    try:
        cutoff = now_utc() - timedelta(days=_INTERACTION_ATTRIBUTION_DAYS)
        seen = db.scalar(
            select(FeedImpressionLog.id)
            .where(
                FeedImpressionLog.post_id == post_id,
                FeedImpressionLog.user_id == user_id,
                FeedImpressionLog.scene == SCENE_POST_FEED,
                FeedImpressionLog.created_at >= cutoff,
            )
            .limit(1)
        )
        if not seen:
            return
        stat = db.get(PostExploreStat, post_id)
        if stat is None:
            return
        if kind == "like":
            stat.like_count = (stat.like_count or 0) + 1
        else:
            stat.comment_count = (stat.comment_count or 0) + 1
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[EXPLORE] record_interaction failed: {}", exc)


def pick_explore_comments(
    db: Session,
    post_id: int,
    limit: int,
    config: dict,
    exclude_ids: set[int] | None = None,
    rng: random.Random | None = None,
) -> list[Comment]:
    """评论探索：从低赞新评论中随机挑 limit 条（只挑根评论，不打乱回复树）。"""
    limit = max(0, int(limit))
    if limit <= 0:
        return []
    since = now_utc() - timedelta(hours=config["feed_explore_hours"])
    query = (
        select(Comment)
        .where(
            Comment.post_id == post_id,
            Comment.ai_status == "approved",
            Comment.parent_id.is_(None),
            Comment.created_at >= since,
            Comment.like_count <= 3,
        )
        .order_by(desc(Comment.created_at))
        .limit(_MAX_POOL_CANDIDATES)
    )
    if exclude_ids:
        query = query.where(Comment.id.not_in(exclude_ids))
    candidates = list(db.scalars(query).all())
    if not candidates:
        return []
    if len(candidates) <= limit:
        return candidates
    rng = rng or random.Random()
    return rng.sample(candidates, limit)


def explore_stats(db: Session, top_limit: int = 20, log_limit: int = 50) -> dict:
    """后台探索效果统计：汇总指标 + Top 探索帖 + 最近曝光日志。"""
    row = db.execute(
        select(
            func.coalesce(func.sum(PostExploreStat.impressions), 0),
            func.coalesce(func.sum(PostExploreStat.click_count), 0),
            func.coalesce(func.sum(PostExploreStat.like_count), 0),
            func.coalesce(func.sum(PostExploreStat.comment_count), 0),
        )
    ).one()
    impressions, clicks, likes, comments = (int(v) for v in row)
    interactions = likes + comments
    ctr = round(clicks / impressions, 4) if impressions else 0.0
    interaction_rate = round(interactions / impressions, 4) if impressions else 0.0

    # Top 探索帖（按曝光量排序，附互动与 CTR）
    top_rows = db.execute(
        select(PostExploreStat, Post)
        .join(Post, Post.id == PostExploreStat.post_id)
        .order_by(desc(PostExploreStat.impressions))
        .limit(top_limit)
    ).all()
    top_posts = []
    for stat, post in top_rows:
        imp = int(stat.impressions or 0)
        clk = int(stat.click_count or 0)
        top_posts.append({
            "post_id": post.id,
            "title": post.title,
            "category": post.category,
            "impressions": imp,
            "click_count": clk,
            "like_count": int(stat.like_count or 0),
            "comment_count": int(stat.comment_count or 0),
            "ctr": round(clk / imp, 4) if imp else 0.0,
        })

    # 最近曝光日志
    log_rows = db.execute(
        select(FeedImpressionLog, Post.title, User.nickname)
        .join(Post, Post.id == FeedImpressionLog.post_id)
        .outerjoin(User, User.id == FeedImpressionLog.user_id)
        .order_by(desc(FeedImpressionLog.id))
        .limit(log_limit)
    ).all()
    recent_logs = [
        {
            "id": log.id,
            "post_id": log.post_id,
            "target_id": log.target_id,
            "title": title,
            "user_id": log.user_id,
            "nickname": nickname,
            "scene": log.scene,
            "page": log.page,
            "created_at": log.created_at,
        }
        for log, title, nickname in log_rows
    ]

    return {
        "summary": {
            "impressions": impressions,
            "click_count": clicks,
            "ctr": ctr,
            "like_count": likes,
            "comment_count": comments,
            "interaction_count": interactions,
            "interaction_rate": interaction_rate,
        },
        "top_posts": top_posts,
        "recent_logs": recent_logs,
    }
