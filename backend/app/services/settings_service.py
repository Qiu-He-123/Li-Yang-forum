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
}

_DESC: dict[str, str] = {
    "deepseek_enabled": "是否启用 DeepSeek AI 审核",
    "deepseek_api_key": "DeepSeek API 密钥",
    "deepseek_base_url": "DeepSeek API 基础 URL",
    "deepseek_model": "DeepSeek 模型名",
    "audit_auto_delete_days": "审核失败内容自动删除天数（0=不自动删除）",
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
    if items:
        set_many(db, items)
