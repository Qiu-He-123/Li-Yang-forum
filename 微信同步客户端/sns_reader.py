"""朋友圈/好友数据读取：复用「获取微信朋友圈」的现有解密逻辑。

对外只暴露几个函数：
- find_sns_db(datadir, key_hex)       -> (account_dir, sns_db_path) | None
- decrypt_to_tmp(sns_db_path, key_hex) -> 解密后的临时 db 路径
- read_feeds(dec_db, images_dir)      -> list[dict]（含 tid/wxid/正文/时间/本地图片）
- read_contacts(account_dir, key_hex) -> list[dict]（wxid/微信号/昵称/备注）
- find_image_key_file(images_key_path)-> dict | None
- verify_image_key(data_root, images_key) -> bool
"""

import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# 仓库根目录（本文件在 微信同步客户端/ 下，向上两级）
_REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORTER_PATH = _REPO_ROOT / "获取微信朋友圈" / "导出朋友圈.py"
IMAGE_KEY_DEFAULT = _REPO_ROOT / "获取微信朋友圈" / "图片密钥.json"
# 聊天记录导出工具来自独立的 ai群聊 项目：换电脑后按相对位置探测，找不到则跳过该能力
_CHAT_EXPORT_CANDIDATES = [
    _REPO_ROOT.parent / "ai群聊" / "取聊天记录_自研" / "聊天记录导出工具" / "export_chat.py",
]


def _load_exporter():
    spec = importlib.util.spec_from_file_location("sns_exporter", EXPORTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_sns_db(datadir, key_hex):
    exp = _load_exporter()
    data_root = datadir or exp.find_data_root()
    if not data_root or not os.path.isdir(data_root):
        return None, None, None
    for acc, p in exp.find_sns_db_candidates(data_root):
        try:
            if exp.check_key(p, key_hex):
                return data_root, acc, p
        except Exception:
            continue
    return data_root, None, None


def decrypt_to_tmp(sns_db_path, key_hex):
    exp = _load_exporter()
    tmp = tempfile.mkdtemp(prefix="sns_sync_")
    raw = os.path.join(tmp, "sns.db")
    dec = os.path.join(tmp, "sns.dec.db")
    shutil.copy2(sns_db_path, raw)
    exp.decrypt_db(raw, key_hex, dec)
    return tmp, dec


def read_feeds(dec_db_path, images_dir=None):
    """读取全部朋友圈动态。media 里 type=2 的项若匹配到本地图片会带 local 路径。"""
    exp = _load_exporter()
    con = sqlite3.connect(dec_db_path)
    feeds = []
    for tid, uname, content in con.execute(
        "SELECT tid, user_name, content FROM SnsTimeLine"
    ):
        f = exp.parse_feed(content)
        if f is None:
            f = {"create_time": 0, "username": uname or "", "text": "", "location": {}, "media": []}
        f["tid"] = str(tid)
        f["wxid"] = f.get("username") or uname or ""
        feeds.append(f)
    con.close()

    if images_dir and os.path.isdir(images_dir):
        # 图片目录按 账号wxid/YYYY-MM 组织，且缓存里文件 mtime=下载时间
        # 而非发布时间：按 wxid + 动态发布月份 分组，只在该账号该月份的
        # 图片里匹配；该月份没有图片就返回空（宁缺毋错），避免像旧逻辑
        # 那样全库按 mtime 乱配，把别的月份/账号的图安到动态上。
        by_key: dict[tuple, list] = {}
        for f in feeds:
            wxid = f.get("wxid") or ""
            ts = int(f.get("create_time") or 0)
            month = time.strftime("%Y-%m", time.localtime(ts)) if ts else ""
            by_key.setdefault((wxid, month), []).append(f)
        for (wxid, month), group in by_key.items():
            wx_dir = os.path.join(images_dir, wxid) if wxid else images_dir
            month_dir = os.path.join(wx_dir, month) if month else wx_dir
            index = exp.build_image_index(month_dir)
            index_mtimes = [e[0] for e in index]
            for f in group:
                local_list = exp.match_media_to_images(
                    f.get("create_time") or 0, f.get("media") or [], index, index_mtimes
                )
                for md, local in zip(f.get("media") or [], local_list):
                    md["local"] = local
    return feeds


def read_contacts(account_dir, key_hex):
    exp = _load_exporter()
    contact_src = os.path.join(account_dir, "db_storage", "contact", "contact.db")
    if not os.path.isfile(contact_src):
        return []
    tmp = tempfile.mkdtemp(prefix="sns_contact_")
    try:
        dec = os.path.join(tmp, "contact.dec.db")
        exp.decrypt_db(contact_src, key_hex, dec)
    except Exception:
        return []
    out = []
    try:
        con = sqlite3.connect(dec)
        cols = [r[1] for r in con.execute("PRAGMA table_info(contact)")]
        for row in con.execute("SELECT * FROM contact"):
            d = dict(zip(cols, row))
            uname = (d.get("username") or "").strip()
            if not uname:
                continue
            out.append(
                {
                    "wxid": uname,
                    "wechat_id": (d.get("alias") or "").strip(),
                    "nickname": (d.get("nick_name") or "").strip(),
                    "remark": (d.get("remark") or "").strip() or None,
                }
            )
        con.close()
    except sqlite3.Error:
        pass
    return out


def read_recent_incoming_messages(account_dir, key_hex):
    """读取社区账号收到的最近文本消息，返回 {peer_wxid: (last_time, text)}。
    绑定分步流程第 2 步用：用户把验证码发给社区微信号后，这里能读到。
    """
    import sqlite3 as _sqlite

    msg_dir = os.path.join(account_dir, "db_storage", "message")
    if not os.path.isdir(msg_dir):
        return {}
    exp = _load_exporter()
    chat_mod = None
    for cand in _CHAT_EXPORT_CANDIDATES:
        if cand.is_file():
            mod_path = cand
            break
    else:
        mod_path = _CHAT_EXPORT_CANDIDATES[0]
    if mod_path.is_file():
        spec = importlib.util.spec_from_file_location("chat_exporter", mod_path)
        chat_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(chat_mod)
    if chat_mod is None:
        return {}

    out = {}
    for name in sorted(os.listdir(msg_dir)):
        if not (name.startswith("message_") or name.startswith("biz_message")):
            continue
        src = os.path.join(msg_dir, name)
        tmp = tempfile.mkdtemp(prefix="sns_msg_")
        try:
            dec = os.path.join(tmp, name + ".db")
            exp.decrypt_db(src, key_hex, dec)
            con = _sqlite.connect(dec)
            try:
                md5map = chat_mod.build_md5map(con)
                tables = [
                    r[0]
                    for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                    )
                ]
                for tbl in tables:
                    peer = md5map.get(tbl[4:])
                    if not peer:
                        continue
                    try:
                        rows = con.execute(
                            'SELECT local_type, real_sender_id, create_time, message_content '
                            'FROM "%s" ORDER BY local_id DESC LIMIT 1' % tbl
                        ).fetchall()
                    except _sqlite.Error:
                        continue
                    for local_type, sender_id, ct, content in rows:
                        # 只要"收到的"文本消息（sender_id != 2 表示不是自己发的）
                        if local_type != 1 or sender_id == 2:
                            continue
                        _sender, text = chat_mod.parse_text_message(content)
                        if not text or not text.strip():
                            continue
                        cur = out.get(peer)
                        if cur is None or (ct or 0) > cur[0]:
                            out[peer] = (int(ct or 0), text.strip()[:500])
            finally:
                con.close()
        except Exception:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def load_image_key(path=None):
    p = Path(path) if path else IMAGE_KEY_DEFAULT
    if not p.is_file():
        return None
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    aes = cfg.get("aes_key", "")
    if not aes:
        return None
    return cfg


def key_file_valid(image_key) -> tuple[bool, str]:
    """新算法格式校验：aes_key 为 16 位 ASCII 或 32 位 hex，xor_key 必须存在。"""
    if not image_key:
        return False, "缺少图片密钥"
    aes = str(image_key.get("aes_key") or "")
    if len(aes) not in (16, 32):
        return False, "图片密钥格式错误（aes_key 应为 16 位 ASCII 或 32 位 hex）"
    if image_key.get("xor_key") is None:
        return False, "图片密钥缺少 xor_key"
    return True, ""


def data_root_of(account_path) -> str:
    """账号目录 -> 微信数据根目录（含 db_storage 的目录取父级）。"""
    p = str(account_path)
    if os.path.isdir(os.path.join(p, "db_storage")):
        return os.path.dirname(p)
    return p


def _load_key_tool_module():
    """加载 获取微信朋友圈/获取图片密钥.py（新算法：kvcomm 推导）。"""
    mod_path = _REPO_ROOT / "获取微信朋友圈" / "获取图片密钥.py"
    spec = importlib.util.spec_from_file_location("image_key_tool", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def derive_image_key_for_account(data_root, account_path) -> dict | None:
    """新算法：从本地 kvcomm 缓存推导该账号的图片密钥。
    返回 {aes_key, xor_key, uin, wxid, account_dir, source} 或 None。
    微信重启不影响；前提是该账号先在朋友圈点开浏览过 2-3 张图片。
    """
    try:
        mod = _load_key_tool_module()
        acc_name = os.path.basename(str(account_path))
        return mod.derive_via_kvcomm(
            data_root, None, lambda *a, **k: None, account_dir=acc_name
        )
    except Exception:
        return None


def normalize_wxid(account_id):
    """wxid_xxx_abcd -> wxid_xxx（去掉 4 位随机后缀），与密钥 json 里的 wxid 对齐。"""
    aid = (account_id or "").strip()
    if aid.lower().startswith("wxid_"):
        m = re.match(r"^(wxid_[^_]+)", aid, re.IGNORECASE)
        return m.group(1) if m else aid
    m = re.match(r"^(.+)_([a-zA-Z0-9]{4})$", aid)
    return m.group(1) if m else aid


def image_key_matches_account(image_key, account_path) -> tuple[bool, str]:
    """校验图片密钥 json 里的 wxid 是否属于指定账号目录。
    新算法按账号推导（MD5(code+wxid)），密钥和账号是一一对应的，串了就是错的。
    """
    kw = (image_key.get("wxid") or "").strip()
    if not kw:
        return True, ""
    expect = normalize_wxid(os.path.basename(str(account_path)))
    if not expect or not expect.lower().startswith("wxid_"):
        # 传入的不是账号目录（如微信数据根目录），不做账号归属校验
        return True, ""
    if normalize_wxid(kw) != expect:
        return False, f"图片密钥属于其他账号（{kw}），请登录该账号后重新抓取"
    return True, ""


def find_v2_cache_images(data_root, limit=20):
    """找朋友圈缓存里的 V2/V1 加密图片（带魔数头），按缓存时间倒序取最近 limit 个。
    只有这类图片才真正依赖 AES 密钥，能验证密钥是否有效；旧 XOR 单字节格式无法验证 AES。
    """
    v2_magic = b"\x07\x08V2\x08\x07"
    v1_magic = b"\x07\x08V1\x08\x07"
    candidates = []
    if not data_root or not os.path.isdir(data_root):
        return candidates
    for dp, _dn, fns in os.walk(data_root):
        parts = dp.split(os.sep)
        if "Sns" not in parts or "Img" not in parts:
            continue
        for fn in fns:
            if fn.endswith("_t"):
                continue
            p = os.path.join(dp, fn)
            try:
                if os.path.getsize(p) < 32:
                    continue
                with open(p, "rb") as f:
                    head = f.read(6)
                if head in (v2_magic, v1_magic):
                    candidates.append((os.path.getmtime(p), p))
            except OSError:
                continue
    candidates.sort(key=lambda e: e[0], reverse=True)
    return [p for _m, p in candidates[:limit]]


def verify_image_key(data_root, image_key, expect_wxid=None):
    """验证图片密钥是否有效。

    新算法说明（微信 4.x）：
    - 图片密钥按账号从本地 kvcomm 缓存推导：xor_key = code & 0xFF，
      aes_key = MD5(code + wxid)[:16]，与微信是否重启无关，密钥稳定
    - 前提：必须先在该账号微信里打开「朋友圈」，点开浏览 2-3 张图片，
      让 V2 加密缓存写入本地，验证才有样本可用
    - 校验只认 V2/V1 加密图（带魔数头，真正依赖 AES），并优先最新缓存；
      旧 XOR 单字节格式无法验证 AES，不再作为通过依据
    """
    if not image_key:
        return False, "缺少图片密钥"
    ok_fmt, msg_fmt = key_file_valid(image_key)
    if not ok_fmt:
        return False, msg_fmt
    if expect_wxid:
        ok, msg = image_key_matches_account(image_key, expect_wxid)
        if not ok:
            return False, msg
    mod_path = _REPO_ROOT / "获取微信朋友圈" / "下载朋友圈图片.py"
    spec = importlib.util.spec_from_file_location("sns_media", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    aes_raw = image_key.get("aes_key", "")
    aes_key = bytes.fromhex(aes_raw) if len(aes_raw) == 32 else aes_raw.encode("ascii")[:16]
    xor_key = image_key.get("xor_key")

    samples = find_v2_cache_images(data_root)
    if not samples:
        return False, "该账号还没有 V2 图片缓存，请打开朋友圈点开浏览 2-3 张图片后再试"
    for sample in samples:
        try:
            result, fmt = mod.decrypt_dat_file(sample, aes_key, xor_key)
        except Exception:
            continue
        # 严格校验：必须是完整图片（JPEG 以 FF D9 结尾 / PNG 以 IEND 结尾），
        # 避免 XOR/AES 错误时把花图当成功
        if result and fmt and mod.is_complete_image(result, fmt):
            return True, f"图片解密验证通过（{fmt}，完整图片）"
    return False, "图片解密验证失败（V2 图片解不开），密钥与账号不匹配或需要重新抓取"
