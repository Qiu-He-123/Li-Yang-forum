"""后端直读微信本地数据库（不依赖同步客户端"投递"）。

职责：
1. 从 ``微信同步客户端/账号配置/<账号>/db_key.txt`` 读取数据库密钥；
2. 解密 sns.db / contact.db / message 各 Msg_ 表（AES-CBC + HMAC 分页，与
   ``获取微信朋友圈/导出朋友圈.py`` 同一算法）；
3. 解析朋友圈 XML，媒体按 XML 自带的 ``url + token + key`` 精确下载解密
   （x-enc:1 用 WxIsaac64，见 ``wx_isaac.py``），彻底替代旧的
   "按时间窗口猜测缓存文件" 逻辑，保证图片与内容一一对应；
4. 绑定验证码直接读 message 库实时校验。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import struct
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.services.wx_isaac import wx_isaac_keystream

try:
    from Crypto.Cipher import AES
except ImportError:  # pragma: no cover
    AES = None

# 微信数据库加密参数（与导出工具一致）
PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE = (IV_SIZE + HMAC_SIZE + 15) // 16 * 16
ITER_COUNT = 256000
KEY_SIZE = 32
SQLITE_HEADER = b"SQLite format 3\x00"

REPO_ROOT = Path(__file__).resolve().parents[3]
CLIENT_DIR = REPO_ROOT / "微信同步客户端"
ACCOUNTS_DIR = CLIENT_DIR / "账号配置"
UPLOAD_ROOT = REPO_ROOT / "backend" / "uploads"

WECHAT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090719) XWEB/8351"
)


# ============ 数据库解密（与 获取微信朋友圈/导出朋友圈.py 同一算法）============

def derive_keys(key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    enc_key = hashlib.pbkdf2_hmac("sha512", key, salt, ITER_COUNT, KEY_SIZE)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, KEY_SIZE)
    return enc_key, mac_key


def page_hmac(page_buf: bytes, mac_key: bytes, offset: int, page_no: int) -> bytes:
    h = hmac.new(mac_key, digestmod=hashlib.sha512)
    h.update(page_buf[offset:PAGE_SIZE - RESERVE + IV_SIZE])
    h.update(struct.pack("<I", page_no))
    return h.digest()


def check_key(src: str, key_hex: str) -> bool:
    try:
        key = bytes.fromhex(key_hex.strip())
    except ValueError:
        return False
    if len(key) != 32:
        return False
    try:
        with open(src, "rb") as f:
            data = f.read(PAGE_SIZE)
    except OSError:
        return False
    if len(data) < PAGE_SIZE or data[:16] == SQLITE_HEADER:
        return False
    salt = data[:SALT_SIZE]
    _enc_key, mac_key = derive_keys(key, salt)
    expect = page_hmac(data, mac_key, SALT_SIZE, 1)
    stored = data[PAGE_SIZE - RESERVE + IV_SIZE:PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
    return hmac.compare_digest(expect, stored)


def decrypt_db(src: str, key_hex: str, dst: str) -> str:
    if AES is None:
        raise RuntimeError("缺少 pycryptodome，请安装 backend 依赖")
    key = bytes.fromhex(key_hex.strip())
    if len(key) != 32:
        raise ValueError("密钥长度错误")
    with open(src, "rb") as f:
        data = f.read()
    if len(data) < PAGE_SIZE:
        raise ValueError("数据库文件过小")
    if data[:16] == SQLITE_HEADER:
        shutil.copyfile(src, dst)
        return dst
    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)
    total_pages = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    with open(dst, "wb") as out:
        out.write(SQLITE_HEADER)
        for page_no in range(total_pages):
            page_buf = data[page_no * PAGE_SIZE:(page_no + 1) * PAGE_SIZE]
            if len(page_buf) < PAGE_SIZE:
                break
            if not any(page_buf):
                out.write(page_buf)
                continue
            offset = SALT_SIZE if page_no == 0 else 0
            expect = page_hmac(page_buf, mac_key, offset, page_no + 1)
            stored = page_buf[PAGE_SIZE - RESERVE + IV_SIZE:PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
            if expect != stored:
                raise ValueError("第 %d 页 HMAC 校验失败（密钥不正确或文件损坏）" % (page_no + 1))
            iv = page_buf[PAGE_SIZE - RESERVE:PAGE_SIZE - RESERVE + IV_SIZE]
            ct = page_buf[offset:PAGE_SIZE - RESERVE]
            plain = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(ct)
            out.write(plain)
            out.write(page_buf[PAGE_SIZE - RESERVE:])
    return dst


_DEC_DB_CACHE: dict[tuple[str, int, int], str] = {}


def decrypt_to_tmp(src: str, key_hex: str) -> str:
    """解密到临时目录并缓存（按文件大小+mtime 判断是否过期）。"""
    stat = os.stat(src)
    cache_key = (src, stat.st_size, int(stat.st_mtime))
    cached = _DEC_DB_CACHE.get(cache_key)
    if cached and os.path.isfile(cached):
        return cached
    tmp = tempfile.mkdtemp(prefix="wechat_local_")
    dst = os.path.join(tmp, os.path.basename(src) + ".dec.db")
    decrypt_db(src, key_hex, dst)
    # 只保留最近 8 个解密缓存
    if len(_DEC_DB_CACHE) >= 8:
        _DEC_DB_CACHE.clear()
    _DEC_DB_CACHE[cache_key] = dst
    return dst


# ============ 账号配置发现 ============

def list_accounts() -> list[dict]:
    """扫描 微信同步客户端/账号配置/*，返回带密钥的账号列表。"""
    out = []
    if not ACCOUNTS_DIR.is_dir():
        return out
    for entry in sorted(os.listdir(ACCOUNTS_DIR)):
        d = ACCOUNTS_DIR / entry
        key_file = d / "db_key.txt"
        cfg_file = d / "config.json"
        if not key_file.is_file():
            continue
        try:
            key_hex = key_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        cfg = {}
        if cfg_file.is_file():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        datadir = cfg.get("datadir") or ""
        out.append(
            {
                "account_dir": str(d),
                "account_id": entry,
                "wxid": re.sub(r"_([a-zA-Z0-9]{4})$", "", entry),
                "datadir": datadir,
                "key_hex": key_hex,
            }
        )
    return out


def resolve_sns_db(account: dict) -> str | None:
    """定位账号的 sns.db（支持 datadir 指向账号目录或数据根目录）。"""
    datadir = account.get("datadir") or ""
    cands = []
    if datadir:
        base = Path(datadir)
        cands.append(base / "db_storage" / "sns" / "sns.db")
        for p in base.iterdir():
            if p.is_dir():
                cands.append(p / "db_storage" / "sns" / "sns.db")
    cands.append(Path(os.environ.get("USERPROFILE", "C:/Users")) / "Documents" /
                 "xwechat_files" / account["account_id"] / "db_storage" / "sns" / "sns.db")
    for c in cands:
        if os.path.isfile(c):
            return str(c)
    return None


def resolve_contact_db(account: dict) -> str | None:
    datadir = account.get("datadir") or ""
    cands = []
    if datadir:
        base = Path(datadir)
        cands.append(base / "db_storage" / "contact" / "contact.db")
        for p in base.iterdir():
            if p.is_dir():
                cands.append(p / "db_storage" / "contact" / "contact.db")
    for c in cands:
        if os.path.isfile(c):
            return str(c)
    return None


def resolve_message_dir(account: dict) -> str | None:
    datadir = account.get("datadir") or ""
    cands = []
    if datadir:
        base = Path(datadir)
        cands.append(base / "db_storage" / "message")
        for p in base.iterdir():
            if p.is_dir():
                cands.append(p / "db_storage" / "message")
    for c in cands:
        if os.path.isdir(c):
            return str(c)
    return None


# ============ 朋友圈 XML 解析 ============

def _unesc(s: str) -> str:
    import html

    return html.unescape(s or "").strip()


def _parse_attrs(tag: str) -> dict:
    d = {}
    for m in re.finditer(r'([\w:]+)="([^"]*)"', tag):
        d[m.group(1)] = _unesc(m.group(2))
    return d


def _tag_text(block: str, name: str) -> tuple[dict, str]:
    """取 <name attrs>text</name>（或自闭合）的属性与文本。"""
    m = re.search(r"<" + name + r"([^>]*)>(.*?)</" + name + r">", block, re.S)
    if m:
        return _parse_attrs(m.group(1)), _unesc(m.group(2))
    m = re.search(r"<" + name + r"([^>]*)/>", block)
    if m:
        return _parse_attrs(m.group(1)), ""
    return {}, ""


def parse_feed(content: str) -> dict | None:
    """解析 SnsTimeLine.content 的 XML；媒体携带 url/token/key 解密参数。"""
    if not content:
        return None
    feed: dict = {}
    m = re.search(r"<createTime>(\d+)</createTime>", content)
    feed["create_time"] = int(m.group(1)) if m else 0
    m = re.search(r"<username>([^<]+)</username>", content)
    feed["username"] = _unesc(m.group(1)) if m else ""
    m = re.search(r"<contentDesc>(.*?)</contentDesc>", content, re.S)
    feed["text"] = _unesc(m.group(1)) if m else ""
    m = re.search(r"<location([^>]*)/?>", content)
    feed["location"] = _parse_attrs(m.group(1)) if m else {}
    media = []
    for block in re.findall(r"<media>(.*?)</media>", content, re.S):
        mm = re.search(r"<type>(\d+)</type>", block)
        mid = re.search(r"<id>(\d+)</id>", block)
        url_attrs, url = _tag_text(block, "url")
        thumb_attrs, thumb = _tag_text(block, "thumb")
        size_tag = re.search(r"<size([^>]*)/?>", block)
        size_attrs = _parse_attrs(size_tag.group(1)) if size_tag else {}
        enc_m = re.search(r"<enc(?: key=\"([^\"]*)\")?\s*>([^<]*)</enc>", block)
        enc_key = (enc_m.group(1) if enc_m and enc_m.group(1) else "") or ""
        media.append(
            {
                "id": mid.group(1) if mid else "",
                "type": int(mm.group(1)) if mm else 0,
                "url": url,
                "url_attrs": url_attrs,
                "thumb": thumb,
                "thumb_attrs": thumb_attrs,
                "md5": url_attrs.get("md5", ""),
                "key": url_attrs.get("key") or enc_key,
                "token": url_attrs.get("token", ""),
                "enc_idx": url_attrs.get("enc_idx", "0"),
                "width": int(size_attrs.get("width") or 0),
                "height": int(size_attrs.get("height") or 0),
                "local": None,
            }
        )
    feed["media"] = media
    return feed


# ============ 读朋友圈 ============

def read_feeds(account: dict, after_ts: int = 0) -> list[dict]:
    """直读 sns.db，返回 tid/wxid/正文/时间/媒体（含解密参数）。"""
    sns_db = resolve_sns_db(account)
    if not sns_db:
        return []
    key_hex = account["key_hex"]
    if not check_key(sns_db, key_hex):
        return []
    dec = decrypt_to_tmp(sns_db, key_hex)
    feeds = []
    con = sqlite3.connect(dec)
    try:
        for tid, uname, content in con.execute(
            "SELECT tid, user_name, content FROM SnsTimeLine"
        ):
            f = parse_feed(content)
            if f is None:
                f = {"create_time": 0, "username": uname or "", "text": "", "location": {}, "media": []}
            f["tid"] = str(tid)
            f["wxid"] = f.get("username") or uname or ""
            if after_ts and int(f.get("create_time") or 0) < after_ts:
                continue
            feeds.append(f)
    finally:
        con.close()
    return feeds


def read_friends(account: dict) -> list[dict]:
    contact_db = resolve_contact_db(account)
    if not contact_db:
        return []
    try:
        dec = decrypt_to_tmp(contact_db, account["key_hex"])
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


def read_recent_incoming_messages(account: dict) -> dict:
    """直读 message 各 Msg_ 表，返回 {对方wxid: (最近时间, 文本)}。
    绑定验证码校验用：实时、不依赖客户端上报。
    """
    msg_dir = resolve_message_dir(account)
    if not msg_dir:
        return {}
    out: dict[str, tuple[int, str]] = {}
    for name in sorted(os.listdir(msg_dir)):
        if not (name.startswith("message_") or name.startswith("biz_message")):
            continue
        src = os.path.join(msg_dir, name)
        try:
            dec = decrypt_to_tmp(src, account["key_hex"])
            con = sqlite3.connect(dec)
            try:
                md5map = {}
                try:
                    for (u,) in con.execute('SELECT user_name FROM "Name2Id"'):
                        md5map[hashlib.md5(u.encode()).hexdigest()] = u
                except sqlite3.Error:
                    pass
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
                    except sqlite3.Error:
                        continue
                    for local_type, sender_id, ct, content in rows:
                        if local_type != 1 or sender_id == 2:
                            continue
                        text = _parse_text_message(content)
                        if not text or not text.strip():
                            continue
                        cur = out.get(peer)
                        if cur is None or (ct or 0) > cur[0]:
                            out[peer] = (int(ct or 0), text.strip()[:500])
            finally:
                con.close()
        except Exception:
            continue
    return out


def _parse_text_message(content) -> str:
    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8", "replace")
        except Exception:
            return ""
    else:
        text = str(content or "")
    m = re.match(r"^(wxid_[^\n:：]+)[:：]\s*(.*)$", text, re.S)
    return m.group(2) if m else text


# ============ 媒体精确下载 + WxIsaac64 解密 ============

def fix_sns_url(url: str, token: str) -> str:
    """WeFlow 的规则：http→https、/150 缩略图→/0 原图、补 token。"""
    fixed = url.replace("http://", "https://").replace("/150", "/0")
    if token and "token=" not in fixed:
        sep = "&" if "?" in fixed else "?"
        fixed = f"{fixed}{sep}token={token}&idx=1"
    return fixed


def _detect_ext(raw: bytes) -> str:
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:4] == b"\x00\x00\x00\x18" or b"ftyp" in raw[4:12]:
        return "mp4"
    return "bin"


def compress_image_bytes(raw: bytes, max_side: int = 1080, quality: int = 75) -> bytes | None:
    """把图片狠狠压缩成 JPEG：最长边不超过 max_side、质量 quality。

    - Exif 方向转正；透明图垫白底再转 RGB；GIF 动图请由调用方自行跳过；
    - 只有压缩后确实比原图小才返回，否则返回 None（调用方保留原图）；
    - 失败（非图片/损坏）返回 None，绝不抛异常。
    """
    try:
        import io

        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        out = buf.getvalue()
        return out if len(out) < len(raw) else None
    except Exception:
        return None


def compress_video_bytes(raw: bytes, max_side: int = 540, crf: int = 30) -> bytes | None:
    """用 ffmpeg 压缩/转码视频：最长边 max_side、H.264 CRF、AAC 32k、faststart。

    默认最长边 540 / CRF 30 / 音频 32k（追求小体积；6 秒 720p 约可压到 0.5MB）。
    规则（保证浏览器能播 + 尽量小）：
    - 转码成功且比原文件小 → 用转码结果；
    - 转码后更大：原文件若是 HEVC(h265)（浏览器普遍播不了）→ 仍用 H.264 保证可播；
    - 原文件是 H.264 且转码更大 → 保留原文件；
    - ffmpeg 失败/超时 → 返回 None（调用方保留原文件）。绝不抛异常。
    """
    try:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "in.mp4")
            dst = os.path.join(td, "out.mp4")
            with open(src, "wb") as f:
                f.write(raw)
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", src,
                "-vf", "scale='min(%d,iw)':-2" % max_side,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                "-c:a", "aac", "-b:a", "32k",
                "-movflags", "+faststart",
                dst,
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=180)
            if r.returncode != 0 or not os.path.isfile(dst):
                return None
            with open(dst, "rb") as f:
                out = f.read()
            if len(out) < len(raw):
                return out
            # 转码后更大：HEVC 源浏览器播不了，仍用 H.264
            if b"hev1" in raw or b"hvc1" in raw:
                return out
            return None
    except Exception:
        return None


def _account_cache_dir(account_id: str) -> str:
    """账号微信数据 cache 根目录（cache/YYYY-MM/Sns/Video/...）。"""
    for account in list_accounts():
        if account["account_id"] == account_id:
            datadir = account.get("datadir") or ""
            if datadir:
                cache_dir = os.path.join(datadir, "cache")
                return cache_dir if os.path.isdir(cache_dir) else ""
    return ""


def _find_cached_video(cache_root: str, md: dict, create_time: int) -> str | None:
    """在微信本地缓存找明文视频（微信 4.x 把播放过的朋友圈视频明文缓存在本地）。

    匹配顺序：
    1) 缓存文件名 == XML 的 md5 / videomd5（直接命中）；
    2) 缓存 mtime 在动态创建时间 ±72h 内，取最接近的（导出工具同款启发式）。
    """
    attrs = md.get("url_attrs") or {}
    md5 = (attrs.get("md5") or "").strip()
    videomd5 = (attrs.get("videomd5") or "").strip()
    best = None
    best_dist = 0.0
    for dp, _dn, fns in os.walk(cache_root):
        if "Video" not in dp.split(os.sep):
            continue
        for fn in fns:
            if not fn.endswith(".mp4"):
                continue
            base = fn[:-4]
            full = os.path.join(dp, fn)
            if (md5 and base == md5) or (videomd5 and base == videomd5):
                return full
            if not create_time:
                continue
            try:
                mt = os.path.getmtime(full)
            except OSError:
                continue
            dist = abs(mt - create_time)
            if dist <= 72 * 3600 and (best is None or dist < best_dist):
                best = full
                best_dist = dist
    return best


def download_moment_media(md: dict, account_id: str, create_time: int = 0) -> dict | None:
    """按 XML 里的 url+token+key 获取单条媒体，保存到 uploads/wechat/。

    视频：优先复制微信本地缓存明文 mp4（CDN 下载是加密的，现有密钥解不开）；
    找不到缓存才走 CDN，且必须校验 ftyp，解密失败/加密体一律不保存（避免黑屏垃圾）。
    """
    mtype = md.get("type") or 0
    url = (md.get("url") or "").strip()
    if not url or mtype == 0:
        return None
    if mtype == 2:  # 图片
        fixed = fix_sns_url(url, md.get("token") or "")
        try:
            r = requests.get(fixed, timeout=30, headers={"User-Agent": WECHAT_UA})
            raw = r.content
        except requests.RequestException:
            return None
        if not raw:
            return None
        if str(r.headers.get("x-enc") or "") == "1":
            key = (md.get("key") or "").strip()
            if not key:
                return None
            ks = wx_isaac_keystream(key, len(raw))
            raw = bytes(b ^ k for b, k in zip(raw, ks))
        ext = _detect_ext(raw)
        if ext not in ("jpg", "png", "gif", "webp"):
            return None
        # 存储前狠狠压缩：统一转 JPEG（最长边 1080、质量 75）；GIF 动图保留原样
        if ext != "gif":
            compressed = compress_image_bytes(raw)
            if compressed:
                raw = compressed
                ext = "jpg"
    elif mtype in (6, 3, 4):  # 视频
        raw = None
        cover_path = None
        # 1) 优先本地缓存明文视频（微信 4.x 缓存即明文 mp4）
        cache_root = _account_cache_dir(account_id)
        if cache_root:
            cached = _find_cached_video(cache_root, md, create_time)
            if cached:
                try:
                    raw = Path(cached).read_bytes()
                    cp = Path(cached).with_suffix(".jpg")
                    if cp.is_file():
                        cover_path = str(cp)
                except OSError:
                    raw = None
        # 2) 缓存没有 -> CDN 下载（加密体必须校验 ftyp，拒绝垃圾文件）
        if not raw:
            fixed = fix_sns_url(url, md.get("token") or "")
            try:
                r = requests.get(fixed, timeout=60, headers={"User-Agent": WECHAT_UA})
                raw = r.content
            except requests.RequestException:
                raw = None
            if raw:
                if str(r.headers.get("x-enc") or "") == "1":
                    key = (md.get("key") or "").strip()
                    if key:
                        try:
                            k = int(key, 16) if key.lower().startswith("0x") else int(key)
                        except ValueError:
                            k = key
                        ks = wx_isaac_keystream(k, len(raw))
                        raw = bytes(b ^ x for b, x in zip(raw, ks))
                if len(raw) < 12 or raw[4:8] != b"ftyp":
                    raw = None
        if not raw:
            return None
        ext = "mp4"
        # 存储前狠狠压缩：ffmpeg 转码（更小才替换）
        compressed = compress_video_bytes(raw)
        if compressed:
            raw = compressed
        # 封面：本地缓存同名明文封面（CDN 缩略图同样是加密的，拿不到）
        thumb_url = ""
        if cover_path:
            try:
                cv = Path(cover_path).read_bytes()
                comp_cv = compress_image_bytes(cv)
                if comp_cv:
                    cv = comp_cv
                thumb_md5 = hashlib.md5(cv).hexdigest()
                thumb_path = UPLOAD_ROOT / "wechat" / account_id / f"{thumb_md5}.jpg"
                if not thumb_path.exists():
                    thumb_path.parent.mkdir(parents=True, exist_ok=True)
                    thumb_path.write_bytes(cv)
                thumb_url = f"/uploads/wechat/{account_id}/{thumb_md5}.jpg"
            except OSError:
                thumb_url = ""
    else:  # 音乐/其他：不下载
        return None

    md5 = (md.get("md5") or "").strip() or hashlib.md5(raw).hexdigest()
    rel_dir = "wechat/" + account_id
    path = UPLOAD_ROOT / rel_dir / f"{md5}.{ext}"
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        except OSError:
            return None
    return {
        "type": mtype,
        "url": f"/uploads/{rel_dir}/{md5}.{ext}",
        "md5": md5,
        "width": md.get("width") or 0,
        "height": md.get("height") or 0,
        "thumb_url": thumb_url,
    }


def _moment_time(ts: int | None):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def convert_emoji(text: str) -> str:
    from app.utils.wechat_emoji import convert_wechat_emoji

    return convert_wechat_emoji(text or "")


def format_media_json(media: list[dict]) -> str:
    return json.dumps(media, ensure_ascii=False)


def utcnow():
    from datetime import datetime as _dt

    return _dt.now(timezone.utc).replace(tzinfo=None)
