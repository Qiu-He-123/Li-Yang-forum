# -*- coding: utf-8 -*-
"""
live_wcdb - 微信 WCDB 加密库直连读取模块

原理：微信 Windows 4.x 的数据库是 SQLCipher 4 加密的 SQLite。将 32 字节主密钥
通过 sqlite3_key 传入后，SQLCipher 会自动完成 encKey / macKey 派生
(encKey = PBKDF2-HMAC-SHA512(主密钥, 盐, 256000), macKey 由 encKey 派生)，
因此可以直接对微信正在使用的库做只读查询，无需复制、无需离线解密。

依赖：同目录下的 e_sqlcipher.dll（SQLCipher 4 的官方开源构建）。
"""

import ctypes
import base64
import hashlib
import os
import re
import sqlite3 as _sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

SQLITE_OPEN_READONLY = 0x00000001
SQLITE_OK = 0
SQLITE_ROW = 100
SQLITE_DONE = 101

SQLITE_INTEGER = 1
SQLITE_FLOAT = 2
SQLITE_TEXT = 3
SQLITE_BLOB = 4
SQLITE_NULL = 5

EXCLUDE_CONTACTS = (
    "brandsessionholder", "brandservicesessionholder", "notifymessage",
    "weixin", "qqmail",
    "floatbottle", "medianote", "shakeapp",
)

TYPE_LABELS = {
    1: "文本", 3: "[图片]", 34: "[语音]", 43: "[视频]", 47: "[表情]",
    42: "[名片]", 48: "[位置]", 49: "[链接/文件]", 50: "[通话]",
    10000: "[系统消息]", 10002: "[消息已撤回]",
    1090519080: "[语音通话]", 21474836529: "[消息]",
}


class _SqliteCipher:
    """基于 ctypes 的最小 SQLCipher 封装，只读使用。"""

    def __init__(self, dll_path):
        self._dll = ctypes.CDLL(dll_path)
        self._bound_buffers = []
        lib = self._dll

        lib.sqlite3_open_v2.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_int,
            ctypes.c_char_p,
        ]
        lib.sqlite3_open_v2.restype = ctypes.c_int

        lib.sqlite3_key.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_key.restype = ctypes.c_int

        lib.sqlite3_prepare_v2.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_char_p),
        ]
        lib.sqlite3_prepare_v2.restype = ctypes.c_int

        lib.sqlite3_bind_int64.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]
        lib.sqlite3_bind_int64.restype = ctypes.c_int
        lib.sqlite3_bind_text.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        lib.sqlite3_bind_text.restype = ctypes.c_int

        lib.sqlite3_step.argtypes = [ctypes.c_void_p]
        lib.sqlite3_step.restype = ctypes.c_int
        lib.sqlite3_column_count.argtypes = [ctypes.c_void_p]
        lib.sqlite3_column_count.restype = ctypes.c_int
        lib.sqlite3_column_name.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_name.restype = ctypes.c_char_p
        lib.sqlite3_column_type.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_type.restype = ctypes.c_int
        lib.sqlite3_column_int64.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_int64.restype = ctypes.c_longlong
        lib.sqlite3_column_text.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_text.restype = ctypes.c_void_p
        lib.sqlite3_column_bytes.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_bytes.restype = ctypes.c_int
        lib.sqlite3_column_blob.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.sqlite3_column_blob.restype = ctypes.c_void_p

        lib.sqlite3_finalize.argtypes = [ctypes.c_void_p]
        lib.sqlite3_finalize.restype = ctypes.c_int
        lib.sqlite3_errmsg.argtypes = [ctypes.c_void_p]
        lib.sqlite3_errmsg.restype = ctypes.c_char_p
        lib.sqlite3_close.argtypes = [ctypes.c_void_p]
        lib.sqlite3_close.restype = ctypes.c_int

    def open(self, path, key: bytes):
        pdb = ctypes.c_void_p()
        rc = self._dll.sqlite3_open_v2(
            path.encode("utf-8"), ctypes.byref(pdb), SQLITE_OPEN_READONLY, None
        )
        if rc != SQLITE_OK:
            raise OSError(f"无法打开数据库: {path} (rc={rc})")
        keybuf = ctypes.create_string_buffer(key, len(key))
        rc = self._dll.sqlite3_key(pdb, ctypes.cast(keybuf, ctypes.c_void_p), len(key))
        if rc != SQLITE_OK:
            self.close(pdb)
            raise OSError(f"设置密钥失败: {path} (rc={rc})")
        return pdb

    def close(self, pdb):
        if pdb:
            self._dll.sqlite3_close(pdb)

    def error(self, pdb):
        msg = self._dll.sqlite3_errmsg(pdb)
        return msg.decode("utf-8", errors="replace") if msg else "unknown error"

    def _bind(self, stmt, params):
        for i, p in enumerate(params or [], start=1):
            if p is None:
                continue
            if isinstance(p, int):
                rc = self._dll.sqlite3_bind_int64(stmt, i, p)
            else:
                pb = p.encode("utf-8") if isinstance(p, str) else p
                buf = ctypes.create_string_buffer(pb)
                self._bound_buffers.append(buf)  # 保持缓冲区存活，避免临时对象提前释放
                rc = self._dll.sqlite3_bind_text(stmt, i, buf, len(pb), None)
            if rc != SQLITE_OK:
                raise OSError(f"参数绑定失败 (rc={rc})")

    def query(self, pdb, sql, params=None, limit=10000):
        stmt = ctypes.c_void_p()
        rc = self._dll.sqlite3_prepare_v2(
            pdb, sql.encode("utf-8"), -1, ctypes.byref(stmt), None
        )
        if rc != SQLITE_OK:
            raise OSError(f"SQL 错误: {self.error(pdb)} -> {sql[:120]}")
        try:
            self._bind(stmt, params)
            ncol = self._dll.sqlite3_column_count(stmt)
            names = [
                self._dll.sqlite3_column_name(stmt, i).decode("utf-8", errors="replace")
                for i in range(ncol)
            ]
            rows = []
            while True:
                rc = self._dll.sqlite3_step(stmt)
                if rc == SQLITE_DONE:
                    break
                if rc != SQLITE_ROW:
                    raise OSError(f"查询执行失败: {self.error(pdb)}")
                row = []
                for i in range(ncol):
                    t = self._dll.sqlite3_column_type(stmt, i)
                    if t == SQLITE_INTEGER or t == SQLITE_FLOAT:
                        row.append(self._dll.sqlite3_column_int64(stmt, i))
                    elif t == SQLITE_TEXT:
                        p = self._dll.sqlite3_column_text(stmt, i)
                        row.append(ctypes.string_at(p).decode("utf-8", errors="replace") if p else None)
                    elif t == SQLITE_BLOB:
                        p = self._dll.sqlite3_column_blob(stmt, i)
                        n = self._dll.sqlite3_column_bytes(stmt, i)
                        row.append(ctypes.string_at(p, n) if p else None)
                    else:
                        row.append(None)
                rows.append(row)
                if len(rows) >= limit:
                    break
            return names, rows
        finally:
            self._dll.sqlite3_finalize(stmt)
            self._bound_buffers.clear()

    def query_one(self, pdb, sql, params=None):
        names, rows = self.query(pdb, sql, params, limit=1)
        if not rows:
            return None
        return dict(zip(names, rows[0]))


class LiveWcdb:
    """微信 WCDB 直连读取器。持有只读连接，微信运行时可实时查询。"""

    def __init__(self, data_dir, key_hex, dll_path=None, cache_file=None):
        self.data_dir = data_dir
        self.key = bytes.fromhex(key_hex) if isinstance(key_hex, str) else key_hex
        if len(self.key) != 32:
            raise ValueError("密钥必须是 32 字节")
        self._cache_file = cache_file
        self._cache_lock = threading.Lock()
        if dll_path is None:
            dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "e_sqlcipher.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"缺少 SQLCipher 运行库: {dll_path}")
        self._sql = _SqliteCipher(dll_path)
        self._conns = {}
        self._locks = {}
        self._root_lock = threading.RLock()
        self._index_lock = threading.Lock()
        self._msg_dbs = None
        self._table_index = None

    # ---------- 本地缓存（联系人/头像，避免重复读取微信库与压缩） ----------

    def _cache_conn(self):
        con = _sqlite3.connect(self._cache_file, timeout=10)
        con.execute(
            "CREATE TABLE IF NOT EXISTS avatars("
            "username TEXT PRIMARY KEY, data TEXT, updated INTEGER)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS contacts_cache("
            "username TEXT PRIMARY KEY, nick TEXT, remark TEXT, alias TEXT,"
            " updated INTEGER)"
        )
        con.commit()
        return con

    def _cache_get_avatars(self, usernames):
        if not self._cache_file or not usernames:
            return {}
        out = {}
        try:
            with self._cache_lock:
                con = self._cache_conn()
                try:
                    for i in range(0, len(usernames), 300):
                        chunk = usernames[i : i + 300]
                        marks = ",".join("?" * len(chunk))
                        rows = con.execute(
                            f"SELECT username, data FROM avatars WHERE username IN ({marks})",
                            chunk,
                        ).fetchall()
                        for u, data in rows:
                            out[u] = data or ""
                finally:
                    con.close()
        except Exception:
            pass
        return out

    def _cache_put_avatars(self, items):
        if not self._cache_file or not items:
            return
        try:
            with self._cache_lock:
                con = self._cache_conn()
                try:
                    con.executemany(
                        "INSERT OR REPLACE INTO avatars(username, data, updated)"
                        " VALUES (?,?,?)",
                        [(u, d, int(time.time())) for u, d in items],
                    )
                    con.commit()
                finally:
                    con.close()
        except Exception:
            pass

    def _cache_get_contacts(self, usernames, max_age=24 * 3600):
        if not self._cache_file or not usernames:
            return {}
        out = {}
        now = int(time.time())
        try:
            with self._cache_lock:
                con = self._cache_conn()
                try:
                    for i in range(0, len(usernames), 300):
                        chunk = usernames[i : i + 300]
                        marks = ",".join("?" * len(chunk))
                        rows = con.execute(
                            "SELECT username, nick, remark, alias, updated"
                            f" FROM contacts_cache WHERE username IN ({marks})",
                            chunk,
                        ).fetchall()
                        for u, nick, remark, alias, upd in rows:
                            if now - (upd or 0) < max_age:
                                out[u] = {
                                    "nick_name": nick or "",
                                    "remark": remark or "",
                                    "alias": alias or "",
                                }
                finally:
                    con.close()
        except Exception:
            pass
        return out

    def _cache_put_contacts(self, items):
        if not self._cache_file or not items:
            return
        try:
            with self._cache_lock:
                con = self._cache_conn()
                try:
                    con.executemany(
                        "INSERT OR REPLACE INTO contacts_cache"
                        "(username, nick, remark, alias, updated)"
                        " VALUES (?,?,?,?,?)",
                        [(u, c.get("nick_name") or "", c.get("remark") or "",
                          c.get("alias") or "", int(time.time()))
                         for u, c in items],
                    )
                    con.commit()
                finally:
                    con.close()
        except Exception:
            pass

    def warmup(self):
        """后台预热常用库连接，减少首次查询等待。"""
        def _work():
            for rel in (
                self._db_path("session", "session.db"),
                self._db_path("contact", "contact.db"),
                self._db_path("head_image", "head_image.db"),
            ):
                try:
                    self._conn(rel)
                except Exception:
                    pass

        threading.Thread(target=_work, daemon=True).start()

    # ---------- 连接管理 ----------

    def _db_path(self, *parts):
        return os.path.join(self.data_dir, "db_storage", *parts)

    def _conn(self, rel_path):
        path = os.path.normpath(rel_path)
        with self._root_lock:
            if path in self._conns:
                return self._conns[path]
            if not os.path.exists(path):
                raise FileNotFoundError(f"数据库不存在: {path}")
            pdb = self._sql.open(path, self.key)
            self._conns[path] = pdb
            self._locks.setdefault(path, threading.Lock())
            return pdb

    def _query(self, rel_path, sql, params=None, limit=10000, retries=1):
        path = os.path.normpath(rel_path)
        lock = self._locks.setdefault(path, threading.Lock())
        last_err = None
        for attempt in range(retries + 1):
            with lock:
                try:
                    pdb = self._conn(path)
                    return self._sql.query(pdb, sql, params, limit=limit)
                except FileNotFoundError:
                    raise
                except OSError as e:
                    last_err = e
                    self._drop(path)
                    if attempt >= retries:
                        break
        raise OSError(f"查询失败: {last_err}")

    def _query_one(self, rel_path, sql, params=None, retries=1):
        names, rows = self._query(rel_path, sql, params, limit=1, retries=retries)
        if not rows:
            return None
        return dict(zip(names, rows[0]))

    def _drop(self, path):
        with self._root_lock:
            pdb = self._conns.pop(path, None)
            if pdb:
                try:
                    self._sql.close(pdb)
                except Exception:
                    pass

    def refresh(self):
        """微信重启后重新建立连接。"""
        with self._root_lock:
            for path in list(self._conns):
                self._drop(path)
            self._msg_dbs = None
            self._table_index = None

    def close(self):
        with self._root_lock:
            for path in list(self._conns):
                self._drop(path)

    # ---------- 会话 / 联系人 ----------

    def _name_to_table(self, username):
        """消息表名 = Msg_ + md5(用户名)。"""
        return "Msg_" + hashlib.md5(username.encode("utf-8")).hexdigest()

    @staticmethod
    def decode_content(content, max_size=64 * 1024 * 1024):
        """解 WCDB 内置压缩（zstd）的消息内容；非压缩数据原样返回。"""
        if isinstance(content, str):
            return content
        if content and content[:4] == b"\x28\xb5\x2f\xfd":
            try:
                import zstandard

                return zstandard.ZstdDecompressor().decompress(
                    content, max_output_size=max_size
                )
            except Exception:
                return content
        return content

    def _decode_batch(self, items, workers=8):
        """并行解压一批消息内容（zstd 解压释放 GIL，可真并行）。"""
        if not items:
            return
        n = min(workers, len(items))
        with ThreadPoolExecutor(max_workers=n) as ex:
            decoded = list(ex.map(
                lambda it: self.decode_content(it.get("message_content")),
                items))
        for it, d in zip(items, decoded):
            it["content_text"] = d

    def _message_tables(self):
        if self._msg_dbs is None:
            self._msg_dbs = []
            msg_dir = self._db_path("message")
            if os.path.isdir(msg_dir):
                for name in sorted(os.listdir(msg_dir)):
                    if (name.startswith("message_") or name.startswith("biz_message_")) and name.endswith(".db"):
                        self._msg_dbs.append(os.path.join(msg_dir, name))
        return self._msg_dbs

    def _find_table(self, table):
        """消息表 -> 所在库 的索引（惰性构建，微信新增会话后可重建）。"""
        if self._table_index is None:
            with self._index_lock:
                if self._table_index is None:
                    self._build_table_index()
        if table in self._table_index:
            return self._table_index[table]
        # 微信可能新建了会话，重建一次索引再查
        with self._index_lock:
            if self._table_index is None:
                self._build_table_index()
            elif table not in self._table_index:
                self._build_table_index()
        return self._table_index.get(table)

    def _build_table_index(self):
        """消息表 -> 所在库列表（同一会话可能跨多个消息库，需合并）。"""
        index = {}
        for db in self._message_tables():
            try:
                names, rows = self._query(
                    db,
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'",
                    limit=100000,
                )
                for (name,) in rows:
                    index.setdefault(name, [])
                    if db not in index[name]:
                        index[name].append(db)
            except OSError:
                continue
        self._table_index = index

    def list_sessions(self, limit=500):
        """返回最近会话列表（含最后一条消息摘要）。"""
        names, rows = self._query(
            self._db_path("session", "session.db"),
            "SELECT username, type, summary, draft, last_timestamp, sort_timestamp, "
            "last_msg_type, last_msg_sender, last_sender_display_name, unread_count "
            "FROM SessionTable WHERE last_timestamp > 0 ORDER BY sort_timestamp DESC LIMIT ?",
            (limit,),
            limit=limit,
        )
        return [dict(zip(names, r)) for r in rows]

    def get_messages(self, username, limit=50, before=None):
        """读取某个会话的历史消息。before=(create_time, local_id) 用于向上翻页。"""
        table = self._name_to_table(username)
        rels = self._find_table(table)
        if not rels:
            return []
        sql = (
            f"SELECT local_id, server_id, local_type, sort_seq, real_sender_id, "
            f"create_time, status, message_content, source FROM {table} "
        )
        rows_all = []
        for rel in rels:
            try:
                if before:
                    names, rows = self._query(
                        rel,
                        sql + "WHERE create_time < ? OR (create_time = ? "
                              "AND local_id < ?) "
                              "ORDER BY create_time DESC, local_id DESC LIMIT ?",
                        (before[0], before[0], before[1], limit), limit=limit)
                else:
                    names, rows = self._query(
                        rel,
                        sql + "ORDER BY create_time DESC, local_id DESC LIMIT ?",
                        (limit,), limit=limit)
            except Exception:
                continue
            rows_all.extend(rows)
        rows_all.sort(key=lambda r: (-(r[5] or 0), -(r[0] or 0)))
        rows = rows_all[: int(limit)]
        items = [dict(zip(names, r)) for r in rows]
        self._decode_batch(items)
        return items

    def count_messages(self, username, start_ts=None, end_ts=None):
        """统计某会话在实时库中的消息总数（跨库，可选时间范围）。"""
        table = self._name_to_table(username)
        rels = self._find_table(table)
        if not rels:
            return 0
        cond = ""
        params = ()
        if start_ts is not None or end_ts is not None:
            conds = []
            if start_ts is not None:
                conds.append("create_time >= ?")
                params += (int(start_ts),)
            if end_ts is not None:
                conds.append("create_time <= ?")
                params += (int(end_ts),)
            cond = " WHERE " + " AND ".join(conds)
        total = 0
        for rel in rels:
            try:
                names, rows = self._query(
                    rel, "SELECT COUNT(*) FROM %s%s" % (table, cond),
                    params, limit=1)
                total += int(rows[0][0]) if rows else 0
            except Exception:
                pass
        return total

    def get_new_messages(self, username, since_create_time=0,
                         since_local_id=0, limit=500):
        """增量拉取某个会话的新消息（按 create_time 游标，跨库合并）。"""
        table = self._name_to_table(username)
        rels = self._find_table(table)
        if not rels:
            return []
        sql = (
            f"SELECT local_id, server_id, local_type, sort_seq, real_sender_id, "
            f"create_time, status, message_content, source FROM {table} "
            f"WHERE create_time > ? "
            f"ORDER BY create_time ASC, local_id ASC LIMIT ?"
        )
        rows_all = []
        for rel in rels:
            try:
                names, rows = self._query(
                    rel, sql, (int(since_create_time or 0), limit), limit=limit)
            except Exception:
                continue
            rows_all.extend(rows)
        rows_all.sort(key=lambda r: (r[5] or 0, r[0] or 0))
        rows = rows_all[: int(limit)]
        items = [dict(zip(names, r)) for r in rows]
        self._decode_batch(items)
        return items

    # ---------- 消息解析（供展示 / 索引共用） ----------

    @staticmethod
    def _to_text(content):
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return content or ""

    @classmethod
    def _extract_sender_text(cls, text):
        m = re.search(
            r"(wxid_[A-Za-z0-9_\-]+)[:：]([^\x00-\x08\x0b-\x0c\x0e-\x1f]{2,})",
            text,
        )
        if m:
            body = re.split(r"[\ufffd]", m.group(2), 1)[0].strip()
            if body:
                return m.group(1), body
        runs = re.findall(
            r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9，。！？、；：（）「」…]{1,}",
            text,
        )
        if runs:
            best = max(runs, key=len).strip()
            if best:
                return None, best
        return None, None

    @classmethod
    def parse_message(cls, local_type, sender_id, content):
        """返回 (sender, display, detail)。content 可为原始二进制（自动解 zstd）。"""
        text = cls._to_text(cls.decode_content(content))
        me = "我" if sender_id == 2 else "对方"
        if local_type == 1:
            if text.lstrip().startswith("<") and "</" in text:
                return me, "[消息]", text[:120]
            m = re.match(r"^(wxid_[A-Za-z0-9_\-]+)[:：]\s*(.*)$", text, re.S)
            if m and m.group(2).strip():
                return m.group(1), m.group(2).strip(), ""
            sender, body = cls._extract_sender_text(text)
            if body:
                return sender or me, body, ""
            if re.search(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\ufffd]", text):
                return me, "[消息]", ""
            return me, text.strip() or "[消息]", ""
        if local_type == 10000:
            m = re.search(r"<plain><!\[CDATA\[(.*?)\]\]></plain>", text, re.S)
            if m and m.group(1).strip() and not m.group(1).startswith("("):
                return "系统消息", m.group(1).strip(), ""
            if "<" in text and ">" in text:
                return "系统消息", "[系统消息]", text[:120]
            sender, body = cls._extract_sender_text(text)
            if body:
                return "系统消息", body, ""
            return "系统消息", "[系统消息]", ""
        # 非文本类型：只显示类型标签，绝不回显原始 XML
        detail = ""
        if ("<" in text and ">" in text) or "\ufffd" in text:
            detail = text[:120]
        if local_type == 47:
            m = re.search(r'attachedtext\s*=\s*"([^"]+)"', text)
            if m:
                return me, "[表情] " + m.group(1).strip(), detail
            return me, "[表情]", detail
        if local_type == 49:
            m = re.search(
                r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", text, re.S
            )
            title = m.group(1).strip() if m else ""
            if not title:
                m = re.search(
                    r"<des>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</des>", text, re.S
                )
                title = m.group(1).strip() if m else ""
            if title:
                return me, "[链接/文件] " + title, detail
            return me, "[链接/文件]", detail
        return me, TYPE_LABELS.get(local_type, "[消息]"), detail

    # ---------- 联系人与头像 ----------

    def _contact_batch(self, usernames):
        """批量取 contact.db 昵称/备注，返回 {username: {...}}。"""
        if not usernames:
            return {}
        out = self._cache_get_contacts(usernames)
        missing = [u for u in usernames if u not in out]
        if not missing:
            return out
        fresh = {}
        for i in range(0, len(missing), 200):
            chunk = missing[i : i + 200]
            marks = ",".join("?" * len(chunk))
            try:
                names, rows = self._query(
                    self._db_path("contact", "contact.db"),
                    "SELECT username, nick_name, remark, alias, small_head_url "
                    f"FROM contact WHERE username IN ({marks})",
                    chunk,
                    limit=len(chunk),
                )
                for r in rows:
                    d = dict(zip(names, r))
                    fresh[d["username"]] = d
            except OSError:
                continue
        out.update(fresh)
        self._cache_put_contacts(
            [(u, fresh.get(u, {})) for u in missing]
        )
        return out

    def _session_titles(self, usernames):
        """群/特殊会话标题回退（SessionNoContactInfoTable）。"""
        if not usernames:
            return {}
        out = {}
        try:
            for i in range(0, len(usernames), 200):
                chunk = usernames[i : i + 200]
                marks = ",".join("?" * len(chunk))
                names, rows = self._query(
                    self._db_path("session", "session.db"),
                    "SELECT username, session_title FROM SessionNoContactInfoTable "
                    f"WHERE username IN ({marks})",
                    chunk,
                    limit=len(chunk),
                )
                for r in rows:
                    out[r[0]] = r[1]
        except OSError:
            pass
        return out

    def _avatar_data_uri(self, username):
        """从 head_image.db 取头像图片，返回 data URI（过大/缺失则空串）。"""
        if self._cache_file:
            cached = self._cache_get_avatars([username])
            if username in cached:
                return cached[username]
        try:
            row = self._query_one(
                self._db_path("head_image", "head_image.db"),
                "SELECT image_buffer FROM head_image WHERE username = ?",
                (username,),
            )
        except OSError:
            return ""
        blob = (row or {}).get("image_buffer")
        if not isinstance(blob, (bytes, bytearray)) or not blob:
            return ""
        if len(blob) > 64 * 1024:
            return ""
        img = self._downscale(blob)
        ext = "jpeg"
        uri = "data:image/%s;base64,%s" % (ext, base64.b64encode(img).decode("ascii"))
        self._cache_put_avatars([(username, uri)])
        return uri

    @staticmethod
    def _downscale(blob, max_side=96):
        """有 Pillow 时压缩头像，减小前端传输体积。"""
        try:
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(blob))
            im.thumbnail((max_side, max_side))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
            return buf.getvalue()
        except Exception:
            return blob

    def _avatar_batch(self, usernames, limit_per=48 * 1024):
        """批量头像 data URI，限制单次查询数量避免桥接过重。"""
        out = {}
        if not usernames:
            return out
        out = self._cache_get_avatars(usernames)
        missing = [u for u in usernames if u not in out]
        if not missing:
            return out
        try:
            raw = {}
            for i in range(0, len(missing), 50):
                chunk = missing[i : i + 50]
                marks = ",".join("?" * len(chunk))
                names, rows = self._query(
                    self._db_path("head_image", "head_image.db"),
                    "SELECT username, image_buffer FROM head_image "
                    f"WHERE username IN ({marks})",
                    chunk,
                    limit=len(chunk),
                )
                for u, blob in rows:
                    if isinstance(blob, (bytes, bytearray)) and blob and len(blob) <= limit_per:
                        raw[u] = blob

            def build(u):
                return (u, "data:image/jpeg;base64," + base64.b64encode(
                    self._downscale(raw[u])
                ).decode("ascii"))

            users = list(raw)
            if users:
                with ThreadPoolExecutor(max_workers=min(8, len(users))) as ex:
                    built = list(ex.map(build, users))
                for u, uri in built:
                    out[u] = uri
            for u in missing:
                out.setdefault(u, "")
            self._cache_put_avatars([(u, out.get(u, "")) for u in missing])
        except OSError:
            pass
        return out

    def contact_pool(self):
        """全部会话联系人（构建索引选择用）。"""
        sessions = self.list_sessions(limit=100000)
        users = [
            s["username"]
            for s in sessions
            if not s["username"].startswith("gh_")
            and not s["username"].startswith("@")
            and s["username"] not in EXCLUDE_CONTACTS
        ]
        contacts = self._contact_batch(users)
        titles = self._session_titles(users)
        avatars = self._avatar_batch(users)
        out = []
        for s in sessions:
            u = s["username"]
            if (u.startswith("gh_") or u.startswith("@")
                    or u in EXCLUDE_CONTACTS):
                continue
            c = contacts.get(u, {})
            out.append({
                "username": u,
                "nick": c.get("nick_name") or titles.get(u) or "",
                "remark": c.get("remark") or "",
                "avatar": avatars.get(u, ""),
            })
        return out

    def contacts_page(self, kw="", offset=0, limit=200):
        """会话列表分页（与前端结构一致）。"""
        kw = (kw or "").strip()
        like = "%" + kw + "%"
        conds = [
            "last_timestamp > 0",
            "substr(username,1,3) <> 'gh_'",
            "username NOT LIKE '@placeholder%'",
            "username NOT IN (%s)" % ",".join("?" * len(EXCLUDE_CONTACTS)),
        ]
        args = list(EXCLUDE_CONTACTS)
        if like != "%%":
            conds.append("username LIKE ?")
            args.append(like)
        where = " AND ".join(conds)
        row = self._query_one(
            self._db_path("session", "session.db"),
            "SELECT count(*) AS n FROM SessionTable WHERE " + where,
            args,
        )
        total = int((row or {}).get("n", 0))
        names, rows = self._query(
            self._db_path("session", "session.db"),
            "SELECT username, type, summary, last_timestamp, sort_timestamp, unread_count "
            "FROM SessionTable WHERE " + where +
            " ORDER BY sort_timestamp DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
            limit=int(limit),
        )
        users = [r[0] for r in rows]
        contacts = self._contact_batch(users)
        titles = self._session_titles(users)
        avatars = self._avatar_batch(users)
        items = []
        for r in rows:
            d = dict(zip(names, r))
            u = d["username"]
            c = contacts.get(u, {})
            items.append({
                "username": u,
                "nick": c.get("nick_name") or titles.get(u) or "",
                "remark": c.get("remark") or "",
                "alias": c.get("alias") or "",
                "avatar": avatars.get(u, ""),
                "lastTs": d.get("last_timestamp") or 0,
                "summary": d.get("summary") or "",
                "unread": d.get("unread_count") or 0,
            })
        return {"total": total, "items": items}

    def self_info(self):
        """当前账号信息（wxid、昵称、头像）。"""
        base = os.path.basename(os.path.normpath(self.data_dir))
        username = base.rsplit("_", 1)[0] if "_" in base else base
        c = self._contact_batch([username]).get(username, {})
        avatar = self._avatar_data_uri(username)
        return {
            "username": username,
            "nick": c.get("nick_name") or "",
            "avatar": avatar,
        }

    def messages_page(self, username, before_ts=0, before_id=0, limit=50):
        """会话消息分页（与前端结构一致，id=local_id）。"""
        table = self._name_to_table(username)
        rels = self._find_table(table)
        if not rels:
            return {"items": [], "hasMore": False}
        bt = int(before_ts or 0)
        bi = int(before_id or 0)
        n = int(limit) + 1
        sel = (
            "SELECT local_id, server_id, local_type, sort_seq, real_sender_id, "
            "create_time, status, message_content, source FROM %s " % table
        )
        rows_all = []
        for rel in rels:
            try:
                if bi:
                    names, rows = self._query(
                        rel,
                        sel + "WHERE create_time < ? OR (create_time = ? "
                              "AND local_id < ?) "
                              "ORDER BY create_time DESC, local_id DESC LIMIT ?",
                        (bt, bt, bi, n), limit=n)
                else:
                    names, rows = self._query(
                        rel,
                        sel + "ORDER BY create_time DESC, local_id DESC LIMIT ?",
                        (n,), limit=n)
            except Exception:
                continue
            rows_all.extend(rows)
        rows_all.sort(key=lambda r: (-(r[5] or 0), -(r[0] or 0)))
        has_more = len(rows_all) > int(limit)
        rows = rows_all[: int(limit)]

        def parse(r):
            d = dict(zip(names, r))
            sender, display, detail = self.parse_message(
                d.get("local_type"), d.get("real_sender_id"),
                d.get("message_content"))
            return {
                "id": d.get("local_id") or 0,
                "sender": sender,
                "ts": d.get("create_time") or 0,
                "content": display,
                "detail": detail,
                "mtype": d.get("local_type") or 0,
            }

        with ThreadPoolExecutor(max_workers=min(8, len(rows) or 1)) as ex:
            items = list(ex.map(parse, rows))
        items.reverse()
        return {"items": items, "hasMore": has_more}

    def iter_chat_messages(self, username, batch=5000):
        """按时间顺序遍历一个会话的全部消息（构建索引用）。"""
        table = self._name_to_table(username)
        rels = self._find_table(table)
        if not rels:
            return
        for rel in rels:
            last_id = 0
            while True:
                sql = (
                    f"SELECT local_id, local_type, sort_seq, real_sender_id, "
                    f"create_time, status, message_content FROM {table} "
                    f"WHERE local_id > ? "
                    f"ORDER BY local_id ASC LIMIT ?"
                )
                names, rows = self._query(
                    rel, sql, (last_id, batch), limit=batch
                )
                if not rows:
                    break
                for r in rows:
                    yield dict(zip(names, r))
                last_id = rows[-1][0]
                if len(rows) < batch:
                    break

    def session_snapshot(self):
        """会话状态快照（实时对比用）。"""
        out = {}
        try:
            names, rows = self._query(
                self._db_path("session", "session.db"),
                "SELECT username, last_timestamp, summary, unread_count FROM SessionTable",
                limit=100000,
            )
            for r in rows:
                d = dict(zip(names, r))
                u = d["username"]
                if u.startswith("gh_") or u in EXCLUDE_CONTACTS or u.startswith("@"):
                    continue
                out[u] = (d.get("last_timestamp") or 0, d.get("summary") or "",
                          d.get("unread_count") or 0)
        except OSError:
            pass
        return out


def guess_data_dir():
    """自动定位微信数据目录（xwechat_files）。"""
    docs = os.path.join(os.path.expanduser("~"), "Documents", "xwechat_files")
    if os.path.isdir(docs):
        candidates = [
            d for d in os.listdir(docs)
            if d.startswith("wxid_") and os.path.isdir(os.path.join(docs, d))
        ]
        if len(candidates) == 1:
            return os.path.join(docs, candidates[0])
    return None
