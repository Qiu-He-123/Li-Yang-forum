#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在已解密数据库中查找账号资料，并扫描运行中的微信内存中的手机号/wxid。"""

import ctypes
import ctypes.wintypes as wt
import os
import re
import sqlite3
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


WXID = "wxid_p0u3uey9etr822_5cde"
CONTACT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "输出", "decrypted", "contact", "contact.db")

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


k32 = ctypes.windll.kernel32
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.VirtualQueryEx.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t,
]
k32.ReadProcessMemory.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]


def db_account_info():
    """从已解密的 contact.db 中找自己的资料。"""
    print("=== contact.db 中的账号资料 ===")
    con = sqlite3.connect(CONTACT_DB)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    print("表:", tables)
    if "contact" in tables:
        cols = [r[1] for r in con.execute("PRAGMA table_info(contact)")]
        print("contact 列:", cols)
        try:
            name_col = "UserName" if "UserName" in cols else cols[1]
            rows = con.execute(
                "SELECT * FROM contact WHERE %s LIKE ?" % name_col,
                ("wxid_p0u3uey9etr822%",)).fetchall()
            print("匹配自账号行数:", len(rows))
            for r in rows:
                d = dict(zip(cols, r))
                print("\n[自账号]")
                for k, v in d.items():
                    if v not in (None, "", 0, b""):
                        print("  %s = %r" % (k, v))
                    if k == "extra_buffer" and v:
                        print("  extra_buffer(hex) = %s" % v.hex())
                        digits = re.findall(rb"\d{8,}", v)
                        print("  extra_buffer 内数字串: %s" %
                              [x.decode() for x in digits[:20]])
                        phone_cand = re.findall(rb"(?<!\d)1\d{10}(?!\d)", v)
                        if phone_cand:
                            print("  extra_buffer 手机号候选: %s" %
                                  [x.decode() for x in phone_cand])
        except Exception as e:
            print("查询失败:", e)
    con.close()


def db_session_probe():
    """在 session.db 中找账号资料线索（手机号/昵称相关表）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "输出", "decrypted", "session", "session.db")
    if not os.path.exists(path):
        print("无 session.db:", path)
        return
    print("\n=== session.db 线索 ===")
    con = sqlite3.connect(path)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    print("表数量:", len(tables))
    for t in tables:
        try:
            cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % t)]
        except Exception:
            continue
        hot = [c for c in cols if any(k in c.lower() for k in
                                      ("phone", "mobile", "account", "profile",
                                       "self", "user", "nick", "alias"))]
        if hot:
            print("表 %s 相关列: %s" % (t, hot))
    con.close()


def find_weixin_pid():
    best, best_mem = None, -1
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            if (p.info["name"] or "").lower() == "weixin.exe":
                mem = p.info["memory_info"].rss
                if mem > best_mem:
                    best, best_mem = p.info["pid"], mem
    except ImportError:
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Weixin.exe",
                              "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        for line in out.strip().splitlines():
            pid = int(line.split(",")[1].strip('"'))
            best = pid
    return best


def regions(pid):
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        return
    try:
        addr = 0
        mbi = MBI()
        while True:
            n = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                   ctypes.sizeof(mbi))
            if n == 0:
                break
            base = mbi.BaseAddress or 0
            if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE \
                    and (mbi.Protect & 0xFF) in (0x02, 0x04, 0x08, 0x20, 0x40, 0x80) \
                    and not (mbi.Protect & 0x100):
                yield h, base, mbi.RegionSize
            addr = base + (mbi.RegionSize or 0x10000)
    finally:
        k32.CloseHandle(h)


def scan_memory(pid):
    print("\n=== 内存扫描 (PID %d) ===" % pid)
    phone_re = re.compile(rb"(?<!\d)\d{11}(?!\d)")
    wxid_re = re.compile(rb"wxid_[0-9a-zA-Z_]{5,40}")
    cn_mobile_re = re.compile(rb"(?<!\d)1[3-9]\d{9}(?!\d)")
    found_phone = {}
    found_wxid = {}
    cn_mobiles = {}
    buf = ctypes.create_string_buffer(4 * 1024 * 1024)
    total = 0
    for h, base, size in regions(pid):
        off = 0
        while off < size:
            chunk = min(size - off, 4 * 1024 * 1024)
            got = ctypes.c_size_t(0)
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + off),
                                         buf, chunk, ctypes.byref(got)):
                off += chunk
                continue
            data = buf.raw[:got.value]
            total += len(data)
            for m in phone_re.finditer(data):
                addr = base + off + m.start()
                ctx = data[max(0, m.start() - 48):m.end() + 48]
                found_phone.setdefault(m.group(), []).append((addr, ctx))
            for m in wxid_re.finditer(data):
                addr = base + off + m.start()
                found_wxid.setdefault(m.group(), []).append(addr)
            for m in cn_mobile_re.finditer(data):
                addr = base + off + m.start()
                ctx = data[max(0, m.start() - 40):m.end() + 40]
                cn_mobiles.setdefault(m.group(), []).append((addr, ctx))
            off += chunk
    print("扫描字节数:", total)
    print("\n-- wxid 出现位置 (前 20) --")
    for w, addrs in list(found_wxid.items())[:20]:
        print("  %s x%d  e.g. 0x%x" % (w.decode(), len(addrs), addrs[0]))
    print("\n-- 11 位数字 (前 40) --")
    for ph, items in sorted(found_phone.items(), key=lambda x: -len(x[1]))[:40]:
        addrs = [a for a, _ in items]
        print("  %s x%d  e.g. 0x%x" % (ph.decode(), len(items), addrs[0]))
    print("\n-- 合法大陆手机号 (1[3-9] 开头, 前 30, 含上下文) --")
    for ph, items in sorted(cn_mobiles.items(), key=lambda x: -len(x[1]))[:30]:
        addr, ctx = items[0]
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        print("  %s x%d  @0x%x  ctx=[%s]" %
              (ph.decode(), len(items), addr, txt))
    return found_phone, found_wxid


def read_at(pid, addr, length):
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_string_buffer(length)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, length,
                                     ctypes.byref(got)):
            return None
        return buf.raw[:got.value]
    finally:
        k32.CloseHandle(h)


def write_report(found_phone, found_wxid, pid):
    """把账号相关发现写入 UTF-8 报告文件。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "账号资料报告.txt")
    lines = []
    lines.append("=== 微信账号资料报告 ===")
    lines.append("时间: %s" % __import__("datetime").datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"))
    lines.append("进程 PID: %d" % pid)
    lines.append("")
    lines.append("【数据库内自账号资料】")
    lines.append("  wxid: wxid_p0u3uey9etr822")
    lines.append("  微信号(alias): qhqe2623655749")
    lines.append("  昵称: ℳℴѵ℘ℯ")
    lines.append("  地区: 中国/重庆 (extra_buffer protobuf)")
    lines.append("  头像: https://wx.qlogo.cn/mmhead/ver_1/I36qkibr8F5Qdfl5wuM6Rfac1ToIugfukz6KCtM2fLPWI8EBJ1ppyOAtepSe5YSiaNUASWarvubaiaKhkSU1mIf9leRx1qaFj472ib7ia5TtXC5EuicyoBQiaUURXG0lMTpjxS3/132")
    lines.append("")
    lines.append("【内存中出现次数】")
    lines.append("  wxid_p0u3uey9etr822_5cde: %d 次" %
                 len(found_wxid.get(b"wxid_p0u3uey9etr822_5cde", [])))
    lines.append("  wxid_p0u3uey9etr822: %d 次" %
                 len(found_wxid.get(b"wxid_p0u3uey9etr822", [])))
    lines.append("  11 位数字字符串总数: %d 种" % len(found_phone))
    lines.append("")
    lines.append("【合法大陆手机号候选(内存)】")
    cn = [(ph, items) for ph, items in found_phone.items()
          if re.fullmatch(rb"1[3-9]\d{9}", ph)]
    cn.sort(key=lambda x: -len(x[1]))
    for ph, items in cn[:50]:
        addr, ctx = items[0]
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
        lines.append("  %s x%d  @0x%x  ctx=[%s]" %
                     (ph.decode(), len(items), addr, txt))
    lines.append("")
    lines.append("【说明】")
    lines.append("  校准报告中的 0x18466fa8 '手机号' 实为日志字符串，非真实手机号。")
    lines.append("  本地数据库未存自账号绑定手机号；手机号候选多来自联系人/日志。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n报告已写入: %s" % path)


def probe_addresses(pid):
    print("\n=== 校准地址定点读取 (PID %d) ===" % pid)
    probes = [
        ("校准密钥地址", 0x1845CEB0, 64),
        ("校准手机号锚点", 0x18466FA8, 32),
    ]
    for name, addr, n in probes:
        data = read_at(pid, addr, n)
        if data is None:
            print("%s @ 0x%x: 读取失败" % (name, addr))
            continue
        print("\n%s @ 0x%x:" % (name, addr))
        for base in range(0, len(data), 16):
            chunk = data[base:base + 16]
            hexs = " ".join("%02x" % b for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print("  %08x  %-47s  %s" % (addr + base, hexs, asc))


def main():
    db_account_info()
    db_session_probe()
    pid = find_weixin_pid()
    print("\n微信主进程 PID:", pid)
    if pid:
        found_phone, found_wxid = scan_memory(pid)
        write_report(found_phone, found_wxid, pid)
        probe_addresses(pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
