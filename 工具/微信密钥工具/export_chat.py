#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""微信聊天记录导出工具（单文件版）。

功能：
  1. 用 db_key.txt 里的密钥解密微信 4.x 的全部数据库（SQLCipher4 口令模式）；
  2. 提取聊天记录、联系人、会话列表；
  3. 输出：解密后的数据库 + 联系人.csv + 会话列表.csv + 聊天记录.html。

用法：
  python export_chat.py                # 打开图形界面
  python export_chat.py --cli          # 命令行模式（自动检测数据目录和密钥）
  python export_chat.py --datadir <微信数据目录> --key <密钥文件> --out <输出目录>
"""

import csv
import hashlib
import html
import os
import re
import sqlite3
import struct
import sys
import time

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


# ============ 解密（SQLCipher4 / 微信 4.x 口令模式） ============

PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE = (IV_SIZE + HMAC_SIZE + 15) // 16 * 16
KEY_SIZE = 32
ITER_COUNT = 256000
SQLITE_HEADER = b"SQLite format 3\x00"


def derive_keys(key, salt):
    enc_key = hashlib.pbkdf2_hmac("sha512", key, salt, ITER_COUNT, KEY_SIZE)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, KEY_SIZE)
    return enc_key, mac_key


def page_hmac(page_buf, mac_key, offset, page_no):
    h = __import__("hmac").new(mac_key, digestmod=hashlib.sha512)
    h.update(page_buf[offset: PAGE_SIZE - RESERVE + IV_SIZE])
    h.update(struct.pack("<I", page_no))
    return h.digest()


def check_key(src, key_hex):
    """只校验第一页 HMAC，快速判断密钥是否正确。返回 (ok, msg)。"""
    try:
        key = bytes.fromhex(key_hex.strip())
    except ValueError:
        return False, "密钥不是合法 hex"
    if len(key) != 32:
        return False, "密钥长度不是 32 字节"
    try:
        with open(src, "rb") as f:
            data = f.read(PAGE_SIZE)
    except OSError as e:
        return False, str(e)
    if len(data) < PAGE_SIZE:
        return False, "数据库文件过小"
    if data[:16] == SQLITE_HEADER:
        return False, "该库已是明文"
    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)
    expect = page_hmac(data, mac_key, SALT_SIZE, 1)
    stored = data[PAGE_SIZE - RESERVE + IV_SIZE: PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
    if expect != stored:
        return False, "HMAC 校验失败（密钥不正确）"
    return True, "ok"


def decrypt_db(src, key_hex, dst):
    """解密单个数据库到 dst。返回 dst 或抛出异常。"""
    key = bytes.fromhex(key_hex.strip())
    if len(key) != 32:
        raise ValueError("密钥长度错误")
    with open(src, "rb") as f:
        data = f.read()
    if len(data) < PAGE_SIZE:
        raise ValueError("文件过小: %s" % src)
    if data[:16] == SQLITE_HEADER:
        raise ValueError("已是明文: %s" % src)
    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)
    total_pages = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    os.makedirs(os.path.dirname(dst), exist_ok=True)
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
                raise ValueError("第 %d 页 HMAC 校验失败（密钥不正确）" % (page_no + 1))
            iv = page_buf[PAGE_SIZE - RESERVE: PAGE_SIZE - RESERVE + IV_SIZE]
            ct = page_buf[offset: PAGE_SIZE - RESERVE]
            plain = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(ct)
            out.write(plain)
            out.write(page_buf[PAGE_SIZE - RESERVE:])
    return dst


# ============ 目录检测 ============

DATA_ROOTS = [
    r"D:\Users\Documents\xwechat_files",
    os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files\All Users"),
    os.path.expandvars(r"%USERPROFILE%\Documents\wcf"),
]


def find_data_root():
    for root in DATA_ROOTS:
        if os.path.isdir(root):
            return root
    return None


def find_db_files(data_root):
    """递归找 .db 文件，返回 [(大小, 路径)]。"""
    found = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        for fn in filenames:
            if fn.lower().endswith(".db"):
                p = os.path.join(dirpath, fn)
                try:
                    found.append((os.path.getsize(p), p))
                except OSError:
                    pass
    return [p for _s, p in sorted(found)]


def find_account_roots(data_root):
    """数据目录下可能有多个账号（wxid_* 子目录），返回账号根目录列表。"""
    if os.path.isdir(os.path.join(data_root, "db_storage")):
        return [data_root]
    roots = []
    try:
        for entry in os.listdir(data_root):
            p = os.path.join(data_root, entry)
            if os.path.isdir(p) and (
                    entry.startswith("wxid_")
                    or os.path.isdir(os.path.join(p, "db_storage"))):
                roots.append(p)
    except OSError:
        pass
    return roots or [data_root]


def find_key_file():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "db_key.txt"),
                 os.path.join(os.getcwd(), "db_key.txt")):
        if os.path.isfile(cand):
            return cand
    return None


# ============ 消息类型 ============

TYPE_NAMES = {
    1: "文本", 3: "图片", 34: "语音", 42: "名片", 43: "视频",
    47: "表情", 48: "位置", 49: "链接/文件", 10000: "系统消息",
    10002: "撤回", 1090519080: "语音通话",
}


def decode_content(content):
    if content is None:
        return ""
    if isinstance(content, bytes):
        try:
            return content.decode("utf-8", "replace")
        except Exception:
            return ""
    return str(content)


def parse_text_message(content):
    """文本消息可能带 'wxid_xxx:\n' 前缀（群聊），返回 (sender, text)。"""
    text = decode_content(content)
    m = re.match(r"^(wxid_[^\n:：]+)[:：]\s*(.*)$", text, re.S)
    if m:
        return m.group(1), m.group(2)
    return None, text


def parse_embedded_text(content):
    """部分消息（非 1 类型）内嵌 'wxid:\n文本'，去掉二进制头后尽量抠出来。"""
    text = decode_content(content)
    clean = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", text)
    m = re.match(r"^(wxid_[^\n:：]+)[:：]\s*(.+)$", clean, re.S)
    if m:
        return m.group(1), m.group(2).strip()
    return None, None


def extract_sys_text(content):
    """系统消息里尽量抠出可读文本。"""
    text = decode_content(content)
    m = re.search(r"<plain><!\[CDATA\[(.*?)\]\]></plain>", text, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"<!\[CDATA\[(.*?)\]\]>", text, re.S)
    if m:
        return m.group(1).strip()
    return text[:120]


def build_md5map(con):
    """Name2Id + contact 的用户名 -> md5 映射，反查会话名。"""
    md5map = {}
    try:
        rows = con.execute('SELECT user_name FROM "Name2Id"').fetchall()
        for (u,) in rows:
            md5map[hashlib.md5(u.encode()).hexdigest()] = u
    except sqlite3.Error:
        pass
    return md5map


def extract_contacts(contact_db):
    contacts = {}
    try:
        con = sqlite3.connect(contact_db)
        cols = [r[1] for r in con.execute("PRAGMA table_info(contact)")]
        for row in con.execute("SELECT * FROM contact"):
            d = dict(zip(cols, row))
            contacts[d.get("username")] = {
                "username": d.get("username"),
                "nick": d.get("nick_name") or "",
                "remark": d.get("remark") or "",
                "alias": d.get("alias") or "",
                "avatar": d.get("small_head_url") or d.get("big_head_url") or "",
            }
        con.close()
    except sqlite3.Error:
        pass
    return contacts


def display_name(username, contacts):
    c = contacts.get(username)
    if c:
        return c["remark"] or c["nick"] or username
    return username


def extract_messages(message_dbs, contacts):
    """遍历所有消息库，按会话聚合。返回 {username: [msg,...]}。"""
    conv = {}
    for db in message_dbs:
        try:
            con = sqlite3.connect(db)
        except sqlite3.Error:
            continue
        md5map = build_md5map(con)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")]
        except sqlite3.Error:
            tables = []
        for tbl in tables:
            h = tbl[4:]
            username = md5map.get(h)
            if not username:
                username = "会话_" + h[:8]
            try:
                rows = con.execute(
                    'SELECT local_type, real_sender_id, create_time, message_content '
                    'FROM "%s" ORDER BY create_time, local_id' % tbl).fetchall()
            except sqlite3.Error:
                continue
            lst = conv.setdefault(username, [])
            for local_type, sender_id, ct, content in rows:
                type_name = TYPE_NAMES.get(local_type, "类型%d" % local_type)
                detail = ""
                if local_type == 1:
                    sender, text = parse_text_message(content)
                    if sender:
                        sender_name = display_name(sender, contacts)
                    else:
                        sender_name = "我" if sender_id == 2 else "对方"
                    display = text
                elif local_type == 10000:
                    sender_name = "系统消息"
                    display = extract_sys_text(content)
                else:
                    raw = decode_content(content)
                    sender, text = parse_embedded_text(content)
                    if text:
                        sender_name = display_name(sender, contacts) if sender else (
                            "我" if sender_id == 2 else "对方")
                        display = text
                        detail = ""
                    else:
                        sender_name = "我" if sender_id == 2 else "对方"
                        display = "[%s]" % type_name
                        detail = raw[:200]
                lst.append({
                    "time": ct,
                    "sender": sender_name,
                    "display": display,
                    "detail": detail,
                    "type": type_name,
                })
        con.close()
    # 按时间排序
    for u in conv:
        conv[u].sort(key=lambda m: m["time"])
    return conv


def extract_sessions(session_db):
    sessions = []
    try:
        con = sqlite3.connect(session_db)
        cols = [r[1] for r in con.execute("PRAGMA table_info(SessionTable)")]
        for row in con.execute("SELECT * FROM SessionTable"):
            d = dict(zip(cols, row))
            sessions.append((d.get("username"), d.get("summary") or "",
                             d.get("last_timestamp") or 0))
        con.close()
    except sqlite3.Error:
        pass
    return sessions


# ============ 输出 ============

def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def esc(s):
    return html.escape(str(s or ""), quote=False)


def fmt_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except Exception:
        return ""


HTML_CSS = ("body{font-family:'Microsoft YaHei',sans-serif;margin:24px;"
            "background:#f5f5f5}.conv{background:#fff;border:1px solid #ddd;"
            "border-radius:8px;padding:16px;margin:16px 0}h2{font-size:18px;"
            "margin:0 0 12px}.msg{margin:8px 0}.msg .meta{color:#999;font-size:12px}"
            ".msg .body{margin-top:2px;white-space:pre-wrap;word-break:break-all}"
            ".mine .meta .sender{color:#07c160}.detail{color:#888;font-size:12px;"
            "background:#f8f8f8;padding:4px;border-radius:4px}"
            "a{color:#1f4e79;text-decoration:none}")


def write_conversation_html(path, username, msgs, contacts):
    title = display_name(username, contacts)
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
             "<title>%s</title><style>%s</style></head><body>"
             % (esc(title), HTML_CSS)]
    parts.append("<p><a href='index.html'>&larr; 返回会话列表</a></p>")
    parts.append("<div class='conv'><h2>%s <span style='font-size:12px;"
                 "color:#aaa'>%s</span></h2>" % (esc(title), esc(username)))
    for m in msgs:
        mine = "mine" if m["sender"] == "我" else ""
        parts.append("<div class='msg %s'><div class='meta'>[%s] "
                     "<span class='sender'>%s</span></div>"
                     "<div class='body'>%s</div>%s</div>"
                     % (mine, fmt_time(m["time"]), esc(m["sender"]),
                        esc(m["display"]),
                        "<div class='detail'>%s</div>" % esc(m["detail"])
                        if m["detail"] else ""))
    parts.append("</div></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def write_index_html(chat_dir, conv, contacts, safe_map):
    items = sorted(conv.items(), key=lambda kv: kv[1][-1]["time"] if kv[1] else 0,
                   reverse=True)
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
             "<title>微信聊天记录 - 会话列表</title><style>%s</style></head><body>"
             % HTML_CSS]
    parts.append("<h1>微信聊天记录（共 %d 个会话）</h1>" % len(items))
    parts.append("<table style='border-collapse:collapse;width:100%'>")
    parts.append("<tr style='text-align:left;color:#666'>"
                 "<th>会话</th><th>消息数</th><th>最后消息时间</th></tr>")
    for username, msgs in items:
        title = display_name(username, contacts)
        last = fmt_time(msgs[-1]["time"]) if msgs else ""
        parts.append("<tr><td><a href='%s'>%s</a>"
                     "<div style='color:#aaa;font-size:12px'>%s</div></td>"
                     "<td>%d</td><td>%s</td></tr>"
                     % (esc(safe_map[username] + ".html"), esc(title),
                        esc(username), len(msgs), esc(last)))
    parts.append("</table></body></html>")
    with open(os.path.join(chat_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# ============ 主流程 ============

def run_export(data_dir, key_hex, out_dir, progress=None):
    if progress is None:
        progress = lambda s: print(s, flush=True)
    if AES is None:
        progress("缺少 pycryptodome，无法解密")
        return 1
    if not data_dir or not os.path.isdir(data_dir):
        progress("微信数据目录不存在: %s" % data_dir)
        return 1
    if not key_hex:
        progress("缺少密钥（请先运行密钥获取工具，或指定 --key）")
        return 1
    key_hex = key_hex.strip()
    if len(bytes.fromhex(key_hex)) != 32:
        progress("密钥长度不是 32 字节")
        return 1

    os.makedirs(out_dir, exist_ok=True)
    dec_dir = os.path.join(out_dir, "decrypted")
    os.makedirs(dec_dir, exist_ok=True)

    # 逐个账号试密钥，只处理密钥匹配的那个账号
    account_dir = None
    dbs = []
    for acc in find_account_roots(data_dir):
        acc_dbs = find_db_files(acc)
        if not acc_dbs:
            continue
        ok, msg = check_key(acc_dbs[0], key_hex)
        progress("账号 %s 密钥校验: %s" % (os.path.basename(acc), msg))
        if ok:
            account_dir = acc
            dbs = acc_dbs
            break
    if not dbs:
        progress("没有找到密钥匹配的账号数据库（请确认密钥和数据目录）")
        return 2
    progress("匹配账号: %s，共 %d 个数据库文件" % (account_dir, len(dbs)))

    # 解密全部
    decrypted = []
    for i, src in enumerate(dbs, 1):
        rel = os.path.relpath(src, account_dir)
        dst = os.path.join(dec_dir, rel)
        try:
            decrypt_db(src, key_hex, dst)
            progress("[%d/%d] %s" % (i, len(dbs), rel))
            decrypted.append(dst)
        except Exception as e:
            progress("[%d/%d] 失败 %s: %s" % (i, len(dbs), rel, e))

    # 提取联系人
    contacts = {}
    for d in decrypted:
        if os.path.basename(d) == "contact.db":
            contacts = extract_contacts(d)
            break
    if contacts:
        write_csv(os.path.join(out_dir, "联系人.csv"),
                  ["微信号", "昵称", "备注", "微信号(alias)", "头像"],
                  [[c["username"], c["nick"], c["remark"], c["alias"], c["avatar"]]
                   for c in contacts.values()])
        progress("联系人: %d 条" % len(contacts))

    # 提取会话列表
    sessions = []
    for d in decrypted:
        if os.path.basename(d) == "session.db":
            sessions = extract_sessions(d)
            break
    if sessions:
        write_csv(os.path.join(out_dir, "会话列表.csv"),
                  ["微信号", "最后消息摘要", "最后时间"],
                  [[u, s, fmt_time(t)] for u, s, t in sessions])
        progress("会话: %d 条" % len(sessions))

    # 提取聊天记录
    msg_dbs = [d for d in decrypted
               if os.path.basename(d).startswith("message_")
               or os.path.basename(d).startswith("biz_message")]
    conv = extract_messages(msg_dbs, contacts)
    total = sum(len(v) for v in conv.values())
    if conv:
        chat_dir = os.path.join(out_dir, "聊天记录")
        os.makedirs(chat_dir, exist_ok=True)
        safe_map = {}
        for username in conv:
            safe = re.sub(r'[\\/:*?"<>|]', "_", username)[:60] or "chat"
            safe_map[username] = safe
            write_conversation_html(
                os.path.join(chat_dir, safe + ".html"), username,
                conv[username], contacts)
        write_index_html(chat_dir, conv, contacts, safe_map)
        progress("聊天记录: %d 个会话，%d 条消息" % (len(conv), total))

    progress("完成。输出目录: %s" % out_dir)
    return 0


# ============ 图形界面 ============

def gui_main():
    import tkinter as tk
    from tkinter import ttk, scrolledtext, filedialog, messagebox

    root = tk.Tk()
    root.title("微信聊天记录导出工具")
    root.geometry("720x600")
    root.minsize(620, 480)

    pad = {"padx": 12, "pady": 4}
    head = ttk.Frame(root)
    head.pack(fill="x", **pad)
    ttk.Label(head, text="微信聊天记录导出工具",
              font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
    ttk.Label(head, text="解密数据库并导出聊天记录（需先获取密钥 db_key.txt）",
              foreground="#666666").pack(anchor="w")

    info = ttk.LabelFrame(root, text="配置")
    info.pack(fill="x", **pad)
    var_dir = tk.StringVar(value=find_data_root() or "")
    var_key = tk.StringVar(value=find_key_file() or "")
    var_out = tk.StringVar(value=os.path.join(os.getcwd(), "导出结果"))
    ttk.Label(info, text="微信数据目录: ").grid(row=0, column=0, sticky="e", padx=6, pady=3)
    ttk.Entry(info, textvariable=var_dir).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Button(info, text="选择…",
               command=lambda: var_dir.set(
                   filedialog.askdirectory(title="选择微信数据目录（xwechat_files）")
                   or var_dir.get())).grid(row=0, column=2)
    ttk.Label(info, text="密钥文件: ").grid(row=1, column=0, sticky="e", padx=6, pady=3)
    ttk.Entry(info, textvariable=var_key).grid(row=1, column=1, sticky="ew", padx=6)
    ttk.Button(info, text="选择…",
               command=lambda: var_key.set(
                   filedialog.askopenfilename(title="选择密钥文件 db_key.txt")
                   or var_key.get())).grid(row=1, column=2)
    ttk.Label(info, text="输出目录: ").grid(row=2, column=0, sticky="e", padx=6, pady=3)
    ttk.Entry(info, textvariable=var_out).grid(row=2, column=1, sticky="ew", padx=6)
    ttk.Button(info, text="选择…",
               command=lambda: var_out.set(
                   filedialog.askdirectory(title="选择输出目录") or var_out.get())
               ).grid(row=2, column=2)
    info.columnconfigure(1, weight=1)

    btns = ttk.Frame(root)
    btns.pack(fill="x", **pad)

    logbox = ttk.LabelFrame(root, text="进度")
    logbox.pack(fill="both", expand=True, **pad)
    txt = scrolledtext.ScrolledText(logbox, height=10, state="disabled",
                                    font=("Consolas", 9))
    txt.pack(fill="both", expand=True, padx=8, pady=6)

    def log(s):
        txt.configure(state="normal")
        txt.insert("end", s + "\n")
        txt.see("end")
        txt.configure(state="disabled")

    def start():
        btn.configure(state="disabled")
        import threading
        import queue
        q = queue.Queue()

        def work():
            data_dir = var_dir.get().strip()
            key_file = var_key.get().strip()
            out_dir = var_out.get().strip()
            key_hex = ""
            if key_file:
                try:
                    with open(key_file, encoding="utf-8") as f:
                        key_hex = f.read().strip()
                except OSError as e:
                    q.put(("log", "读取密钥失败: %s" % e))
            q.put(("log", "==== 开始导出 ===="))
            code = run_export(data_dir, key_hex, out_dir, progress=lambda s: q.put(("log", s)))
            q.put(("done", code))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "log":
                        log(payload)
                    elif kind == "done":
                        btn.configure(state="normal")
                        if payload == 0:
                            messagebox.showinfo("完成", "导出完成！\n输出目录: %s" % var_out.get())
                        else:
                            messagebox.showerror("失败", "导出失败，请查看进度日志。")
            except Exception:
                pass
            root.after(120, poll)

        root.after(120, poll)

    btn = ttk.Button(btns, text="开始提取", command=start)
    btn.pack(side="left")
    ttk.Button(btns, text="退出", command=root.destroy).pack(side="right")
    root.mainloop()


def main():
    if "--cli" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--cli"]
        data_dir = None
        key_file = None
        out_dir = "导出结果"
        i = 0
        while i < len(args):
            if args[i] == "--datadir" and i + 1 < len(args):
                data_dir = args[i + 1]
                i += 2
            elif args[i] == "--key" and i + 1 < len(args):
                key_file = args[i + 1]
                i += 2
            elif args[i] == "--out" and i + 1 < len(args):
                out_dir = args[i + 1]
                i += 2
            else:
                i += 1
        if data_dir is None:
            data_dir = find_data_root()
        if key_file is None:
            kf = find_key_file()
            key_file = kf if kf else ""
        key_hex = ""
        if key_file:
            with open(key_file, encoding="utf-8") as f:
                key_hex = f.read().strip()
        return run_export(data_dir, key_hex, out_dir)
    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
