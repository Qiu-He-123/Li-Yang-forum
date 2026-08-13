#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 PC 版朋友圈导出工具

基于微信 4.x 本地缓存与数据库的解密链路：
  1. 用 db_key.txt 里的密钥（微信运行时从内存抓取，32 字节 hex）
  2. 找到当前账号的 db_storage\\sns\\sns.db 并复制到临时目录
  3. SQLCipher4 口令模式解密（PBKDF2-HMAC-SHA512 + AES-256-CBC）
  4. 解析 SnsTimeLine（动态）与 SnsMessage_tmp3（赞/评论）
  5. 结合 contact.db 还原昵称，输出一份可读的 txt 报告

用法：
  python 导出朋友圈.py                      # 自动检测数据目录与密钥
  python 导出朋友圈.py --datadir <微信数据目录> --key <密钥文件> --out <结果txt>
"""

import argparse
import bisect
import hashlib
import hmac as hmac_mod
import html
import os
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
import time
import datetime
from pathlib import Path

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


# ============ SQLCipher4 解密（与参考工具一致） ============

PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE = (IV_SIZE + HMAC_SIZE + 15) // 16 * 16
KEY_SIZE = 32
ITER_COUNT = 256000
SQLITE_HEADER = b"SQLite format 3\x00"

DATA_ROOTS = [
    os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files\All Users"),
]

# 参考密钥文件：优先本目录下 db_key.txt，没有则靠 --key 参数
def _find_ref_key_file() -> str:
    here = Path(__file__).resolve().parent
    key = here / "db_key.txt"
    return str(key) if key.is_file() else ""

REF_KEY_FILE = _find_ref_key_file()


def derive_keys(key, salt):
    enc_key = hashlib.pbkdf2_hmac("sha512", key, salt, ITER_COUNT, KEY_SIZE)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, KEY_SIZE)
    return enc_key, mac_key


def page_hmac(page_buf, mac_key, offset, page_no):
    h = hmac_mod.new(mac_key, digestmod=hashlib.sha512)
    h.update(page_buf[offset: PAGE_SIZE - RESERVE + IV_SIZE])
    h.update(struct.pack("<I", page_no))
    return h.digest()


def check_key(src, key_hex):
    """只校验第一页 HMAC，快速判断密钥是否匹配。"""
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
    if len(data) < PAGE_SIZE:
        return False
    if data[:16] == SQLITE_HEADER:
        return False
    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)
    expect = page_hmac(data, mac_key, SALT_SIZE, 1)
    stored = data[PAGE_SIZE - RESERVE + IV_SIZE: PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
    return hmac_mod.compare_digest(expect, stored)


def decrypt_db(src, key_hex, dst):
    key = bytes.fromhex(key_hex.strip())
    if len(key) != 32:
        raise ValueError("密钥长度错误")
    with open(src, "rb") as f:
        data = f.read()
    if len(data) < PAGE_SIZE:
        raise ValueError("数据库文件过小: %s" % src)
    if data[:16] == SQLITE_HEADER:
        raise ValueError("已是明文: %s" % src)
    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)
    total_pages = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    with open(dst, "wb") as out:
        out.write(SQLITE_HEADER)
        for page_no in range(total_pages):
            page_buf = data[page_no * PAGE_SIZE: (page_no + 1) * PAGE_SIZE]
            if len(page_buf) < PAGE_SIZE:
                break
            if not any(page_buf):
                out.write(page_buf)
                continue
            offset = SALT_SIZE if page_no == 0 else 0
            expect = page_hmac(page_buf, mac_key, offset, page_no + 1)
            stored = page_buf[PAGE_SIZE - RESERVE + IV_SIZE: PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
            if expect != stored:
                raise ValueError("第 %d 页 HMAC 校验失败（密钥不正确或文件损坏）" % (page_no + 1))
            iv = page_buf[PAGE_SIZE - RESERVE: PAGE_SIZE - RESERVE + IV_SIZE]
            ct = page_buf[offset: PAGE_SIZE - RESERVE]
            plain = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(ct)
            out.write(plain)
            out.write(page_buf[PAGE_SIZE - RESERVE:])
    return dst


# ============ 数据目录 / 账号定位 ============

def find_data_root():
    for root in DATA_ROOTS:
        if os.path.isdir(root):
            return root
    return None


def find_sns_db_candidates(data_root):
    """返回 [(账号目录, sns.db 路径)]。"""
    cands = []
    roots = [data_root]
    try:
        for entry in os.listdir(data_root):
            p = os.path.join(data_root, entry)
            if os.path.isdir(p) and (
                    entry.startswith("wxid_")
                    or os.path.isdir(os.path.join(p, "db_storage"))):
                roots.append(p)
    except OSError:
        pass
    seen = set()
    for r in roots:
        p = os.path.join(r, "db_storage", "sns", "sns.db")
        if os.path.isfile(p) and p not in seen:
            seen.add(p)
            cands.append((r, p))
    return cands


def load_key_file(key_path):
    with open(key_path, encoding="utf-8") as f:
        return f.read().strip()


def find_key(key_arg):
    if key_arg and os.path.isfile(key_arg):
        return load_key_file(key_arg)
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "db_key.txt"), REF_KEY_FILE):
        if os.path.isfile(cand):
            return load_key_file(cand)
    return None


# ============ 朋友圈 XML 解析 ============

def _unesc(s):
    return html.unescape(s or "").strip()


def _parse_attrs(tag):
    """把 <tag k="v" ...> 的属性解析成 dict。"""
    d = {}
    for m in re.finditer(r'([\w:]+)="([^"]*)"', tag):
        d[m.group(1)] = _unesc(m.group(2))
    return d


def parse_feed(content):
    """解析 SnsTimeLine.content 的 XML，返回 dict。"""
    if not content:
        return None
    feed = {}
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
        thumb = re.search(r"<thumb[^>]*>([^<]+)</thumb>", block)
        url = re.search(r"<url[^>]*>([^<]+)</url>", block)
        size_tag = re.search(r"<size([^>]*)/?>", block)
        size_attrs = _parse_attrs(size_tag.group(1)) if size_tag else {}
        media.append({
            "id": mid.group(1) if mid else "",
            "type": int(mm.group(1)) if mm else 0,
            "thumb": _unesc(thumb.group(1)) if thumb else "",
            "url": _unesc(url.group(1)) if url else "",
            "width": int(size_attrs.get("width") or 0),
            "height": int(size_attrs.get("height") or 0),
            "local": None,
        })
    feed["media"] = media
    return feed


def parse_pb_field8(buf):
    """极简 protobuf 解析：取 field 8（0x42）的 UTF-8 字符串（评论正文）。"""
    if not buf:
        return ""
    i, n = 0, len(buf)
    while i < n:
        tag = 0
        shift = 0
        while True:
            b = buf[i]
            i += 1
            tag |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        field, wire = tag >> 3, tag & 7
        if wire == 2:
            ln = 0
            shift = 0
            while True:
                b = buf[i]
                i += 1
                ln |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            val = buf[i:i + ln]
            i += ln
            if field == 8:
                try:
                    return val.decode("utf-8")
                except UnicodeDecodeError:
                    return ""
        elif wire == 0:
            while True:
                b = buf[i]
                i += 1
                if not (b & 0x80):
                    break
        elif wire == 5:
            i += 4
        elif wire == 1:
            i += 8
        else:
            break
    return ""


def parse_interactions(con):
    """SnsMessage_tmp3: type 1=赞, type 2=评论。"""
    rows = con.execute(
        "SELECT feed_id, type, from_username, from_nickname, "
        "create_time, content, serialized_comment_buf "
        "FROM SnsMessage_tmp3").fetchall()
    out = {}
    orphan = []
    for feed_id, itype, fuser, fnick, ct, content, buf in rows:
        item = {
            "type": itype,
            "username": fuser or "",
            "nickname": fnick or "",
            "time": ct or 0,
            "text": "",
        }
        if itype == 2:
            item["text"] = (content or "").strip() or parse_pb_field8(buf)
        if feed_id:
            out.setdefault(feed_id, []).append(item)
        else:
            orphan.append(item)
    return out, orphan


# ============ 联系人昵称 ============

def load_contacts(contact_db):
    contacts = {}
    try:
        con = sqlite3.connect(contact_db)
        cols = [r[1] for r in con.execute("PRAGMA table_info(contact)")]
        for row in con.execute("SELECT * FROM contact"):
            d = dict(zip(cols, row))
            uname = d.get("username")
            if uname:
                contacts[uname] = (d.get("remark") or "").strip() or \
                    (d.get("nick_name") or "").strip() or uname
        con.close()
    except sqlite3.Error:
        pass
    return contacts


def display_name(uname, contacts):
    return contacts.get(uname, uname or "(未知)")


# ============ 统计 ============

def count_cache_media(account_dir):
    """统计 cache\\*\\Sns 下的媒体文件数。"""
    cache = os.path.join(account_dir, "cache")
    by_ext = {}
    total = 0
    if os.path.isdir(cache):
        for dp, _dn, fns in os.walk(cache):
            if "Sns" not in dp.split(os.sep):
                continue
            for fn in fns:
                ext = os.path.splitext(fn)[1].lower()
                by_ext[ext or "(无扩展名=图片)"] = by_ext.get(ext or "(无扩展名=图片)", 0) + 1
                total += 1
    return total, by_ext


def fmt_time(ts):
    if not ts:
        return ""
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


MEDIA_TYPE_NAMES = {2: "图片", 6: "视频", 5: "音乐", 4: "视频动态", 3: "视频"}


def image_dims(path):
    """快速解析图片宽高（jpg/png/webp），失败返回 (0, 0)。"""
    try:
        with open(path, "rb") as f:
            head = f.read(256 * 1024)
    except OSError:
        return 0, 0
    if head[:4] == b"\x89PNG" and len(head) >= 24:
        return struct.unpack(">II", head[16:24])
    if head[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(head):
            if head[i] != 0xFF:
                i += 1
                continue
            marker = head[i + 1]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", head[i + 5:i + 9])
                return w, h
            if i + 3 >= len(head):
                break
            seg = struct.unpack(">H", head[i + 2:i + 4])[0]
            i += 2 + seg
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) >= 30:
        return (struct.unpack("<H", head[26:28])[0] & 0x3FFF,
                struct.unpack("<H", head[28:30])[0] & 0x3FFF)
    return 0, 0


def build_image_index(images_dir):
    """扫描解密后的朋友圈图片目录，建立 (mtime, 路径, 大小, 格式, 宽, 高) 索引。"""
    idx = []
    if not os.path.isdir(images_dir):
        return idx
    for dp, _dn, fns in os.walk(images_dir):
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
                continue
            p = os.path.join(dp, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            w, h = image_dims(p)
            if w <= 0 or h <= 0:
                continue
            idx.append((st.st_mtime, p, st.st_size, ext.lstrip("."), w, h))
    idx.sort(key=lambda e: e[0])
    return idx


def match_media_to_images(create_time, media_list, index, index_mtimes,
                          time_window=72 * 3600):
    """为一条动态的每个图片媒体匹配本地已解密文件（开源社区同款启发式）。

    规则：图片宽高一致 + 缓存 mtime 在动态发布时间 ±72h 内，按
    (解码大小差, 时间差) 打分，已用文件不重复分配。
    """
    results = [None] * len(media_list)
    used = set()
    for i, md in enumerate(media_list):
        if md.get("type") != 2:
            continue
        want_w = md.get("width") or 0
        want_h = md.get("height") or 0
        lo = bisect.bisect_left(index_mtimes, create_time - time_window)
        hi = bisect.bisect_right(index_mtimes, create_time + time_window)
        if lo >= hi:
            lo, hi = 0, len(index)
        best = None
        for j in range(lo, hi):
            mtime_j, path_j, size_j, _fmt_j, w_j, h_j = index[j]
            if path_j in used:
                continue
            if want_w > 0 and want_h > 0 and (w_j != want_w or h_j != want_h):
                continue
            score = (abs(mtime_j - create_time))
            if best is None or score < best[0]:
                best = (score, path_j)
        if best:
            used.add(best[1])
            results[i] = best[1]
    return results


def media_label(t):
    return MEDIA_TYPE_NAMES.get(t, "媒体(类型%d)" % t)


# ============ 主流程 ============

def main():
    ap = argparse.ArgumentParser(description="微信PC版朋友圈导出")
    ap.add_argument("--datadir", help="微信数据目录（xwechat_files），默认自动检测")
    ap.add_argument("--key", help="密钥文件（db_key.txt），默认自动查找")
    ap.add_argument("--out", help="输出 txt 路径，默认 ./朋友圈导出结果.txt")
    ap.add_argument("--images-dir", help="朋友圈图片目录（下载朋友圈图片.py 的输出），"
                                        "默认 ./朋友圈图片")
    ap.add_argument("--keep-tmp", action="store_true", help="保留解密临时目录")
    args = ap.parse_args()

    if AES is None:
        print("缺少 pycryptodome，请先: pip install pycryptodome")
        return 1

    out_path = os.path.abspath(args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "朋友圈导出结果.txt"))

    data_root = args.datadir or find_data_root()
    if not data_root or not os.path.isdir(data_root):
        print("找不到微信数据目录，请用 --datadir 指定")
        return 1
    key_hex = find_key(args.key)
    if not key_hex:
        print("找不到密钥文件，请先运行密钥获取工具并生成 db_key.txt")
        return 1

    # 1. 找密钥匹配的账号
    account_dir = None
    sns_src = None
    for acc, p in find_sns_db_candidates(data_root):
        ok = check_key(p, key_hex)
        print("账号 %s 密钥校验: %s" % (os.path.basename(acc), "OK" if ok else "不匹配"))
        if ok:
            account_dir, sns_src = acc, p
            break
    if not sns_src:
        print("没有找到密钥匹配的账号朋友圈数据库")
        return 2

    # 2. 复制到临时目录再解密（不动微信原文件）
    tmp = tempfile.mkdtemp(prefix="sns_export_")
    try:
        sns_raw = os.path.join(tmp, "sns.db")
        shutil.copy2(sns_src, sns_raw)
        sns_dec = os.path.join(tmp, "sns.dec.db")
        t0 = time.time()
        print("解密 sns.db (%d MB) ..." % (os.path.getsize(sns_src) // 1024 // 1024))
        decrypt_db(sns_raw, key_hex, sns_dec)
        print("解密完成，用时 %.1fs" % (time.time() - t0))

        contact_src = os.path.join(account_dir, "db_storage", "contact", "contact.db")
        contact_dec = None
        if os.path.isfile(contact_src):
            try:
                contact_dec = os.path.join(tmp, "contact.dec.db")
                decrypt_db(contact_src, key_hex, contact_dec)
            except Exception as e:
                print("contact.db 解密失败（不影响导出，昵称将显示 wxid）: %s" % e)
                contact_dec = None

        # 3. 读取并解析
        con = sqlite3.connect(sns_dec)
        feeds = []
        for tid, uname, content in con.execute(
                "SELECT tid, user_name, content FROM SnsTimeLine"):
            f = parse_feed(content)
            if f is None:
                f = {"create_time": 0, "username": uname or "",
                     "text": "", "location": {}, "media": []}
            f["tid"] = tid
            feeds.append(f)
        interactions, orphan = parse_interactions(con)
        con.close()

        contacts = load_contacts(contact_dec) if contact_dec else {}
        # 账号目录形如 wxid_xxx_5cde，去掉末尾随机后缀即本机 wxid
        acc_base = os.path.basename(account_dir)
        self_uname = acc_base
        if acc_base.startswith("wxid_") and "_" in acc_base:
            self_uname = acc_base.rsplit("_", 1)[0]
        self_name = display_name(self_uname, contacts) if self_uname else "(未知)"

        # 4. 图片本地匹配（优先用本账号自己的子目录，避免多账号混淆）
        images_root = os.path.abspath(args.images_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "朋友圈图片"))
        images_dir = os.path.join(images_root, self_uname)
        if not os.path.isdir(images_dir):
            images_dir = images_root
        img_index = build_image_index(images_dir)
        img_mtimes = [e[0] for e in img_index]
        matched = 0
        for f in feeds:
            if not f["media"]:
                continue
            locals_ = match_media_to_images(
                f["create_time"], f["media"], img_index, img_mtimes)
            for md, lp in zip(f["media"], locals_):
                if lp:
                    md["local"] = os.path.relpath(lp, images_dir)
                    matched += 1
        print("本地图片匹配: %d 张（索引 %d 张）" % (matched, len(img_index)))

        # 5. 写结果 txt
        write_report(out_path, account_dir, sns_src, contacts,
                     feeds, interactions, orphan, self_uname, self_name,
                     key_hex, images_dir)
        print("完成: %s" % out_path)
        return 0
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def write_report(out_path, account_dir, sns_src, contacts, feeds,
                 interactions, orphan, self_uname, self_name, key_hex,
                 images_dir):
    feeds.sort(key=lambda f: f["create_time"], reverse=True)
    total = len(feeds)
    users = {}
    times = [f["create_time"] for f in feeds if f["create_time"]]
    img_cnt = sum(1 for f in feeds for md in f["media"] if md["type"] == 2)
    vid_cnt = sum(1 for f in feeds for md in f["media"] if md["type"] in (3, 4, 6))
    music_cnt = sum(1 for f in feeds for md in f["media"] if md["type"] == 5)
    feed_ids_with_ia = set()
    n_comments = n_likes = 0
    for fid, items in interactions.items():
        if fid in {f["tid"] for f in feeds}:
            feed_ids_with_ia.add(fid)
        for it in items:
            if it["type"] == 2:
                n_comments += 1
            else:
                n_likes += 1
    cache_total, cache_by_ext = count_cache_media(account_dir)
    for f in feeds:
        users[f["username"]] = users.get(f["username"], 0) + 1
    top_users = sorted(users.items(), key=lambda x: -x[1])[:20]

    L = []
    A = L.append
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    A("=" * 72)
    A("微信朋友圈导出结果")
    A("生成时间: %s" % now)
    A("=" * 72)
    A("")
    A("【数据来源】")
    A("  账号目录 : %s" % account_dir)
    A("  本机微信  : %s（%s）" % (self_uname, self_name))
    A("  数据库    : %s (%d MB)" % (sns_src, os.path.getsize(sns_src) // 1024 // 1024))
    A("  说明      : 已用 db_key.txt 密钥解密，快照为数据库当前主文件状态")
    A("")
    A("【统计汇总】")
    A("  朋友圈动态总数 : %d" % total)
    A("  发布者数        : %d" % len(users))
    A("  时间范围        : %s ~ %s" % (
        fmt_time(min(times)) if times else "?", fmt_time(max(times)) if times else "?"))
    A("  图片媒体数      : %d（来自 XML 内 <media> 计数）" % img_cnt)
    A("  视频媒体数      : %d" % vid_cnt)
    A("  音乐媒体数      : %d" % music_cnt)
    A("  评论数          : %d" % n_comments)
    A("  点赞数          : %d" % n_likes)
    A("  有互动记录的动态: %d 条" % len(feed_ids_with_ia))
    A("  本地缓存媒体文件: %d 个（cache\\*\\Sns 下）" % cache_total)
    A("  已解密导出图片数  : %d 个（%s）" % (
        sum(1 for _dp, _dn, fns in os.walk(images_dir)
            for fn in fns if os.path.splitext(fn)[1].lower()
            in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))
        if os.path.isdir(images_dir) else 0, images_dir))
    A("  动态图片匹配到本地: %d 张" % sum(
        1 for f in feeds for md in f["media"] if md.get("local")))
    for ext, n in sorted(cache_by_ext.items()):
        A("      %-14s %d" % (ext, n))
    A("")
    A("【发布者 TOP 20】")
    A("  %-4s %-30s %-8s %s" % ("排名", "昵称", "动态数", "wxid"))
    for i, (u, c) in enumerate(top_users, 1):
        A("  %-4d %-30s %-8d %s" % (i, display_name(u, contacts), c, u))
    A("")
    A("【动态明细】共 %d 条，按发布时间倒序" % total)
    A("")
    for idx, f in enumerate(feeds, 1):
        author = display_name(f["username"], contacts)
        A("-" * 72)
        A("[%04d] %s  %s（%s）  tid=%s" % (
            idx, fmt_time(f["create_time"]), author, f["username"], f["tid"]))
        A("-" * 72)
        if f["text"]:
            A("正文: %s" % f["text"])
        loc = f["location"]
        if loc:
            parts = []
            for k in ("poiName", "city", "poiAddress"):
                if loc.get(k):
                    parts.append(loc[k])
            if loc.get("latitude") and loc.get("latitude") != "0":
                parts.append("(%s, %s)" % (loc.get("latitude"), loc.get("longitude")))
            if parts:
                A("位置: %s" % " · ".join(parts))
        if f["media"]:
            A("媒体: %d 个" % len(f["media"]))
            for j, md in enumerate(f["media"], 1):
                A("  [%d] %s" % (j, media_label(md["type"])))
                if md.get("local"):
                    A("      本地文件: %s" % md["local"])
                if md["url"]:
                    A("      原图/视频: %s" % md["url"])
                if md["thumb"] and md["thumb"] != md["url"]:
                    A("      缩略图    : %s" % md["thumb"])
        items = interactions.get(f["tid"], [])
        likes = [it for it in items if it["type"] == 1]
        comments = [it for it in items if it["type"] == 2]
        if likes:
            A("赞(%d): %s" % (len(likes),
              "、".join(display_name(it["nickname"] or it["username"], contacts)
                        for it in likes)))
        if comments:
            A("评论(%d):" % len(comments))
            for it in comments:
                A("  - %s(%s) %s: %s" % (
                    display_name(it["nickname"] or it["username"], contacts),
                    it["username"], fmt_time(it["time"]), it["text"] or "(无文字)"))
        A("")

    if orphan:
        A("=" * 72)
        A("【未关联到本地动态的互动记录】%d 条（对应动态不在本地缓存中）" % len(orphan))
        A("=" * 72)
        for it in orphan:
            kind = "赞" if it["type"] == 1 else "评论"
            A("  [%s] %s(%s) %s  %s" % (
                kind, display_name(it["nickname"] or it["username"], contacts),
                it["username"], fmt_time(it["time"]), it["text"] or ""))
        A("")

    A("=" * 72)
    A("【说明与限制】")
    A("1. 本结果是微信 PC 端本地缓存快照，不是服务器上的完整朋友圈历史。")
    A("2. 要拿到更多内容，需在微信里打开朋友圈并滚动加载，然后重新运行本工具。")
    A("3. 评论/点赞只有在客户端加载过详情时才会进入数据库，覆盖率天然偏低。")
    A("4. 图片/视频本体在 cache\\YYYY-MM\\Sns 目录下，数据库内保存的是带 token 的下载 URL。")
    A("5. 数据库解密密钥需在微信运行时从内存抓取；换账号/重装后需重新抓取。")
    A("=" * 72)

    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(L))
    return out_path


if __name__ == "__main__":
    sys.exit(main())
