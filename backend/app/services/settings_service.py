"""系统设置服务层。

提供 key-value 形式的设置读写，支持管理员后台动态修改 DeepSeek 配置等。
所有设置缓存在内存中，避免每次 AI 调用都查库。
"""
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Setting

# ============ 内存缓存 ============
_cache: dict[str, str] = {}
_cache_lock = threading.Lock()
_cache_loaded = False

# ============ 默认值 ============
_DEFAULTS: dict[str, str] = {
    "deepseek_enabled": "false",
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com/v1",
    "deepseek_model": "deepseek-chat",
    "audit_auto_delete_days": "0",
    # 需要审核的内容范围：post 帖子 / comment 评论 / bottle 漂流瓶 / image 含图片/视频帖子转人工
    "audit_scope": "post,comment,bottle,image",
    # 转人工复核的触发条件：ai_unavailable / violation / high_severity / sensitive_category
    "manual_review_triggers": "ai_unavailable",
    "default_friend_user_id": "",
    "default_friend_user_ids": "",
    # ============ 推荐探索（Explore-Exploit）配置 ============
    "feed_explore_enabled": "true",
    "feed_explore_rate": "0.15",
    "feed_explore_hours": "48",
    "feed_explore_max_likes": "10",
    "feed_explore_mode": "thompson",
    "feed_mmr_enabled": "true",
    "feed_mmr_max_per_category": "6",
    "comment_explore_enabled": "true",
    "comment_explore_rate": "0.15",
    # 个性化去重（大厂做法「推过的不再推」）：推荐流已推给该用户的帖子不再重复推荐
    "feed_dedupe_enabled": "true",
    "feed_dedupe_days": "0",
    # 绑定微信时展示的社区微信号（后台可改）
    "wechat_bind_account": "",
    # 微信同步客户端设备令牌（客户端启动时展示，后台可改）
    "wechat_device_token": "",
    # 微信朋友圈自动同步：多久检查一次朋友圈是否刷新（秒，最小 5）
    "wechat_sync_interval_seconds": "10",
    # 抖音/快手视频直链：多久检测一次失效并自动恢复（分钟）
    "video_link_refresh_interval": "30",
    # ============ 首页滚动字幕 ============
    "home_marquee": "",
}

_DESC: dict[str, str] = {
    "deepseek_enabled": "是否启用 DeepSeek AI 审核",
    "deepseek_api_key": "DeepSeek API 密钥",
    "deepseek_base_url": "DeepSeek API 基础 URL",
    "deepseek_model": "DeepSeek 模型名",
    "audit_auto_delete_days": "审核失败内容自动删除天数（0=不自动删除）",
    "audit_scope": "需要 AI 审核的内容范围（逗号分隔：post 帖子 / comment 评论 / bottle 漂流瓶 / image 含图片/视频帖子转人工审核）",
    "manual_review_triggers": "转人工复核的触发条件（逗号分隔：ai_unavailable AI不可用 / violation AI判违规 / high_severity 中高严重度 / sensitive_category 敏感类别）",
    "default_friend_user_id": "默认好友（官方账号）用户 ID（旧配置，建议改用 default_friend_user_ids 支持多人）",
    "default_friend_user_ids": "默认好友（官方账号）用户 ID 列表（逗号分隔，可配置多人，留空关闭）",
    "feed_explore_enabled": "是否启用推荐探索：热门页按比例插入冷启动帖子，避免低权重内容永远沉底",
    "feed_explore_rate": "探索比例 ε（0-0.5，默认 0.15）：每页约 15% 的位置给低互动新帖随机曝光",
    "feed_explore_hours": "探索窗口（小时，默认 48）：只探索最近 N 小时内发布、尚未破圈的内容",
    "feed_explore_max_likes": "冷启动点赞上限（默认 10）：点赞数超过该值的帖子不再进入探索池",
    "feed_explore_mode": "探索采样算法：uniform 均匀随机 / weighted 按新鲜度+低互动加权 / thompson Thompson 采样（有反馈自动调整，推荐）",
    "feed_mmr_enabled": "是否启用 MMR 类别多样性：热门页同圈子内容超过上限时自动穿插其他圈子",
    "feed_mmr_max_per_category": "热门页单圈子最多展示条数（默认 6，防止热门页被单一圈子刷屏）",
    "comment_explore_enabled": "是否启用评论探索：帖子「最热」评论页按比例插入低赞新评论",
    "comment_explore_rate": "评论探索比例 ε（0-0.5，默认 0.15）",
    "feed_dedupe_enabled": "推荐去重开关（默认开）：推荐流已推给该用户的帖子不再重复推荐，未看过的优先曝光（大厂做法）",
    "feed_dedupe_days": "推荐去重窗口（天，0=全部历史）：只对最近 N 天内已推过的帖子去重，超过窗口后可再次推荐",
    "home_marquee": "首页顶部滚动字幕内容（每行一条，留空关闭）",
    "wechat_bind_account": "用户绑定微信时需要添加的社区微信号（展示在绑定引导页）",
    "wechat_device_token": "微信同步客户端的设备令牌（客户端与后端鉴权用）",
    "wechat_sync_interval_seconds": "微信朋友圈自动同步检查间隔（秒，最小 5）：朋友圈刷新后自动扫描发布",
    "video_link_refresh_interval": "抖音/快手视频直链失效检测间隔（分钟）：后台自动重解析恢复失效直链",
}


def _load_cache(db: Session) -> None:
    """从数据库加载所有设置到内存缓存。"""
    global _cache_loaded
    with _cache_lock:
        if _cache_loaded:
            return
        rows = db.scalars(select(Setting)).all()
        for r in rows:
            _cache[r.key] = r.value
        # 补全默认值
        for k, v in _DEFAULTS.items():
            if k not in _cache:
                _cache[k] = v
        _cache_loaded = True


def _ensure_key(db: Session, key: str, value: str) -> None:
    """确保某个 key 存在（不存在则插入）。"""
    existing = db.get(Setting, key)
    if not existing:
        db.add(Setting(key=key, value=value, description=_DESC.get(key)))
        db.commit()


def get_setting(db: Session, key: str, default: str | None = None) -> str:
    """读取单个设置项。优先从缓存读，未命中则查库。"""
    _load_cache(db)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    # 缓存未命中：查库并补全
    row = db.get(Setting, key)
    val = row.value if row else (default if default is not None else _DEFAULTS.get(key, ""))
    if not row:
        _ensure_key(db, key, val)
    with _cache_lock:
        _cache[key] = val
    return val


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    val = get_setting(db, key)
    if not val:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def get_int(db: Session, key: str, default: int = 0) -> int:
    val = get_setting(db, key)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_set_list(db: Session, key: str, default: str = "") -> set[str]:
    """读取逗号分隔的集合类设置（自动过滤空值）。"""
    raw = get_setting(db, key, default)
    return {s.strip() for s in raw.split(",") if s.strip()}


def get_audit_scope(db: Session) -> set[str]:
    """当前需要审核的内容范围：post / comment / bottle / image。"""
    return get_set_list(db, "audit_scope", "post,comment,bottle,image")


def get_manual_review_triggers(db: Session) -> set[str]:
    """当前触发人工复核的条件集合。"""
    return get_set_list(db, "manual_review_triggers", "ai_unavailable")


def is_audit_scope_enabled(db: Session, key: str) -> bool:
    """指定内容范围是否开启审核。"""
    return key in get_audit_scope(db)


def is_manual_review_trigger_enabled(db: Session, key: str) -> bool:
    """指定人工复核触发条件是否开启。"""
    return key in get_manual_review_triggers(db)


def set_setting(db: Session, key: str, value: str) -> None:
    """写入单个设置项（upsert），同步刷新缓存。"""
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value, description=_DESC.get(key)))
    db.commit()
    with _cache_lock:
        _cache[key] = value
        _cache_loaded = True


def set_many(db: Session, items: dict[str, str]) -> None:
    """批量写入设置项。"""
    for k, v in items.items():
        row = db.get(Setting, k)
        if row:
            row.value = v
        else:
            db.add(Setting(key=k, value=v, description=_DESC.get(k)))
    db.commit()
    with _cache_lock:
        _cache.update(items)
        _cache_loaded = True


def list_settings(db: Session) -> list[dict[str, Any]]:
    """列出所有设置项（含描述）。"""
    _load_cache(db)
    rows = db.scalars(select(Setting)).all()
    by_key = {r.key: r for r in rows}
    result: list[dict[str, Any]] = []
    # 先返回已知默认 key（保证顺序）
    for k in _DEFAULTS:
        row = by_key.get(k)
        result.append({
            "key": k,
            "value": _cache.get(k, _DEFAULTS[k]),
            "description": _DESC.get(k, row.description if row else None),
        })
    # 再返回其他自定义 key
    for r in rows:
        if r.key not in _DEFAULTS:
            result.append({"key": r.key, "value": r.value, "description": r.description})
    return result


def invalidate_cache() -> None:
    """清除内存缓存（下次读取会重新从数据库加载）。"""
    global _cache_loaded
    with _cache_lock:
        _cache.clear()
        _cache_loaded = False


# ============ DeepSeek 便捷封装 ============

def get_deepseek_config(db: Session) -> dict[str, Any]:
    """读取 DeepSeek 完整配置。"""
    return {
        "enabled": get_bool(db, "deepseek_enabled", False),
        "api_key": get_setting(db, "deepseek_api_key", ""),
        "base_url": get_setting(db, "deepseek_base_url", "https://api.deepseek.com/v1"),
        "model": get_setting(db, "deepseek_model", "deepseek-chat"),
        "auto_delete_days": get_int(db, "audit_auto_delete_days", 0),
        "audit_scope": sorted(get_audit_scope(db)),
        "manual_review_triggers": sorted(get_manual_review_triggers(db)),
    }


def update_deepseek_config(db: Session, config: dict[str, Any]) -> None:
    """更新 DeepSeek 配置。"""
    items: dict[str, str] = {}
    if "enabled" in config:
        items["deepseek_enabled"] = "true" if config["enabled"] else "false"
    if "api_key" in config:
        items["deepseek_api_key"] = str(config["api_key"] or "")
    if "base_url" in config:
        items["deepseek_base_url"] = str(config["base_url"] or "")
    if "model" in config:
        items["deepseek_model"] = str(config["model"] or "")
    if "auto_delete_days" in config:
        items["audit_auto_delete_days"] = str(int(config["auto_delete_days"] or 0))
    if "audit_scope" in config:
        scope = config["audit_scope"] or []
        if isinstance(scope, str):
            scope = [s.strip() for s in scope.split(",") if s.strip()]
        valid_scope = {"post", "comment", "bottle", "image"}
        items["audit_scope"] = ",".join(sorted(k for k in scope if k in valid_scope))
    if "manual_review_triggers" in config:
        triggers = config["manual_review_triggers"] or []
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.split(",") if t.strip()]
        valid_triggers = {"ai_unavailable", "violation", "high_severity", "sensitive_category"}
        items["manual_review_triggers"] = ",".join(sorted(k for k in triggers if k in valid_triggers))
    if items:
        set_many(db, items)
