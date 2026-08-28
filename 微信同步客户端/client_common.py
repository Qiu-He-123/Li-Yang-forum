"""共享配置读取 + 账号独立配置管理。

结构：
- 微信同步客户端/config.json         全局配置（api_base / device_token / data_root / current_account）
- 微信同步客户端/账号配置/<wxid>/config.json  该账号独立配置（datadir / state_file）
- 微信同步客户端/账号配置/<wxid>/state.json   该账号的同步进度（已同步 tid）

每个账号互不覆盖；切换账号只改 current_account 指针。
"""

import json
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parent
CONFIG = CLIENT_DIR / "config.json"
ACCOUNTS_DIR = CLIENT_DIR / "账号配置"


def load_shared_config() -> dict:
    if CONFIG.is_file():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_shared_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_name(wxid: str) -> str:
    cleaned = "".join(c for c in str(wxid or "default") if c.isalnum() or c in "_-")
    return cleaned or "default"


def account_dir(wxid: str) -> Path:
    return ACCOUNTS_DIR / safe_name(wxid)


def account_config_path(wxid: str) -> Path:
    return account_dir(wxid) / "config.json"


def account_state_path(wxid: str) -> Path:
    return account_dir(wxid) / "state.json"


def account_key_path(wxid: str) -> Path:
    return account_dir(wxid) / "db_key.txt"


def account_image_key_path(wxid: str) -> Path:
    return account_dir(wxid) / "图片密钥.json"


def load_effective_config() -> dict:
    """全局配置 + 当前账号配置合并；账号配置只覆盖账号相关字段。"""
    shared = load_shared_config()
    cfg = dict(shared)
    wxid = shared.get("current_account") or ""
    if wxid:
        p = account_config_path(wxid)
        if p.is_file():
            try:
                cfg.update(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass
    return cfg


def save_account_config(wxid: str, overrides: dict) -> Path:
    p = account_config_path(wxid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def save_image_key_file(wxid: str, key_dict: dict) -> Path:
    """把（重新推导出的）图片密钥写入账号目录，并更新该账号配置的 images_key。"""
    p = account_image_key_path(wxid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(key_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    overrides = {"datadir": "", "state_file": "state.json"}
    cfg_path = account_config_path(wxid)
    if cfg_path.is_file():
        try:
            overrides.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            pass
    overrides["images_key"] = str(p)
    save_account_config(wxid, overrides)
    return p
