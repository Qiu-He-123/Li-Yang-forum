"""微信 WCDB 直连实时读取（绑定验证码校验用，替代整库解密）。

原理见 live_wcdb.py：微信 4.x 的聊天库是 SQLCipher 4 加密的 SQLite，
用 sqlite3_key 传入 32 字节主密钥后，SQLCipher 自动完成微信同款密钥派生，
可以直接对微信运行中的库开只读连接。连接常驻、按页解密：

- 首次连接/建消息表索引约 0.4~2 秒（多个 message 库逐个做密钥派生）；
- 之后每次查询毫秒级，微信刚收到的新消息立即可见
  （发送消息 -> 微信写入本地库 -> 直连查询，链路毫秒级）。

本模块所有失败都返回 None / 空，由调用方回退到旧的整库解密路径，
不会因缺 dll / 数据目录不可用 / 密钥错误而报错。
"""

import logging
import os
import threading

from app.services import live_wcdb

logger = logging.getLogger(__name__)

_registry: dict[str, live_wcdb.LiveWcdb] = {}
_registry_lock = threading.Lock()


def _data_dir(account: dict) -> str | None:
    """定位微信数据根目录（含 db_storage 的 wxid 目录）。"""
    datadir = account.get("datadir") or ""
    if datadir and os.path.isdir(os.path.join(datadir, "db_storage")):
        return datadir
    base = os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "xwechat_files",
        account.get("account_id") or "",
    )
    if os.path.isdir(os.path.join(base, "db_storage")):
        return base
    return None


def _get_reader(account: dict) -> live_wcdb.LiveWcdb | None:
    data_dir = _data_dir(account)
    key_hex = (account.get("key_hex") or "").strip()
    if not data_dir or not key_hex:
        return None
    try:
        if len(bytes.fromhex(key_hex)) != 32:
            return None
    except ValueError:
        return None
    with _registry_lock:
        wc = _registry.get(data_dir)
        if wc is None:
            try:
                wc = live_wcdb.LiveWcdb(data_dir, key_hex)
            except Exception as exc:
                logger.warning("live_wcdb 初始化失败(%s): %s", data_dir, exc)
                return None
            _registry[data_dir] = wc
        return wc


def latest_incoming_text(account: dict, peer_wxid: str) -> tuple[int, str] | None:
    """实时直连读好友发给社区账号的最新一条文本消息，返回 (create_time, 文本)。

    失败（无数据目录/无密钥/库打不开/没有该会话文本消息）返回 None，
    调用方回退旧的整库解密路径。
    """
    wc = _get_reader(account)
    if wc is None or not peer_wxid:
        return None
    try:
        items = wc.get_messages(peer_wxid, limit=10)
    except Exception as exc:
        logger.warning("live_wcdb 读取失败(%s): %s", peer_wxid, exc)
        return None
    for m in items:
        if int(m.get("local_type") or 0) != 1:
            continue
        if int(m.get("real_sender_id") or 0) == 2:
            continue  # 自己（社区账号）发的消息不算
        text = m.get("content_text")
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        text = (text or "").strip()
        if not text:
            continue
        return (int(m.get("create_time") or 0), text[:500])
    return None
