#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 4.x 朋友圈图片密钥提取工具（纯 Python 独立实现，无任何外部 DLL）

【重要前提 · 必须先做】
  必须先在微信里打开朋友圈，点开浏览 2-3 张图片（大图），
  并保持其中一张图片处于打开状态，才能成功获取密钥。
  —— 只有浏览过图片，微信才会把 V2 图片缓存、kvcomm 状态写入本地，
     内存扫描路径也才能命中临时加载的密钥。

【原理 · GitHub 开源社区公开算法（WeChatDaily 致谢 WeFlow/@hicccc77）】
  V2 图片格式（文件头 07 08 56 32 08 07）：
    [6B 签名] [4B aes_size LE] [4B xor_size LE] [1B 填充]
    + [AES-128-ECB 加密] [明文 raw] [单字节 XOR 加密]

  每个微信账号的图片密钥可以从本地 kvcomm 缓存推导，无需扫内存：
    code      = kvcomm 文件名 key_<code>_*.statistic 中的数字
    xor_key   = code & 0xFF
    aes_key   = MD5(str(code) + wxid).hexdigest()[:16]   # 16 字符 ASCII

  验证：取多个不同的 V2 模板密文（文件 [0xF:0x1F] 16 字节），
  AES-128-ECB 解出图片魔数（JPEG/PNG/GIF/WebP），全部通过才算命中；
  再用完整解密（检查 JPEG 结尾 FF D9 / PNG 结尾 IEND）做最终确认。

  主路径：kvcomm 本地推导（无需读内存，多账号稳定）
  回退路径：内存扫描 16/32 位字母数字串 + 已知明文验证

用法：
  python 获取图片密钥.py                          # 自动检测
  python 获取图片密钥.py --datadir <微信数据目录> --out <密钥json>
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import glob
import hashlib
import json
import os
import re
import struct
import sys
import time

try:
    from Crypto.Cipher import AES
    from Crypto.Util import Padding
except ImportError:
    print("缺少 pycryptodome，请先: pip install pycryptodome")
    sys.exit(1)


V2_MAGIC = b"\x07\x08V2\x08\x07"
V1_MAGIC = b"\x07\x08V1\x08\x07"
IMAGE_MAGICS = (
    b"\xFF\xD8\xFF",          # JPEG
    b"\x89PNG",               # PNG
    b"GIF",                   # GIF
    b"RIFF",                  # WebP 容器
    b"wxgf",                  # 微信 HEVC GIF / Live Photo
)


def normalize_wxid(account_id):
    """账号 wxid 归一化：wxid_xxx_abcd -> wxid_xxx（去掉 4 位随机后缀）。"""
    aid = (account_id or "").strip()
    if not aid:
        return ""
    if aid.lower().startswith("wxid_"):
        m = re.match(r"^(wxid_[^_]+)", aid, re.IGNORECASE)
        return m.group(1) if m else aid
    m = re.match(r"^(.+)_([a-zA-Z0-9]{4})$", aid)
    return m.group(1) if m else aid


def derive_image_keys(code, wxid):
    """核心派生算法：xor_key = code & 0xFF；aes_key = MD5(code+wxid)[:16]。"""
    xor_key = int(code) & 0xFF
    aes_key = hashlib.md5(f"{code}{wxid}".encode("utf-8")).hexdigest()[:16]
    return xor_key, aes_key


# ════════════════════════════════════════════════════════════
# 主路径 1：kvcomm 本地推导
# ════════════════════════════════════════════════════════════

def find_kvcomm_dirs():
    """找微信 kvcomm 缓存目录（Windows：AppData\\Roaming\\Tencent\\xwechat\\net*\\kvcomm）。"""
    dirs = []
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        xwechat = os.path.join(appdata, "Tencent", "xwechat")
        if os.path.isdir(xwechat):
            for entry in os.listdir(xwechat):
                p = os.path.join(xwechat, entry, "kvcomm")
                if os.path.isdir(p):
                    dirs.append(p)
    docs = os.path.expandvars(r"%USERPROFILE%\Documents")
    for p in (os.path.join(docs, "app_data", "net", "kvcomm"),
              os.path.join(docs, "xwechat", "net", "kvcomm")):
        if os.path.isdir(p):
            dirs.append(p)
    return list(dict.fromkeys(dirs))


def collect_kvcomm_codes(kvcomm_dir):
    """从 kvcomm 文件名 key_<code>_*.statistic 提取 code（uin）。"""
    codes = set()
    try:
        names = os.listdir(kvcomm_dir)
    except OSError:
        return codes
    pat = re.compile(r"^key_(\d+)_.+\.statistic$", re.IGNORECASE)
    for name in names:
        m = pat.match(name)
        if not m:
            continue
        try:
            code = int(m.group(1))
        except ValueError:
            continue
        if 0 < code <= 0xFFFFFFFF:
            codes.add(code)
    return codes


def collect_wxid_candidates(data_root):
    """从 xwechat_files 账号目录提取 wxid 候选（原值 + 归一化）。"""
    cands = set()
    try:
        entries = os.listdir(data_root)
    except OSError:
        return cands
    for entry in entries:
        p = os.path.join(data_root, entry)
        if not os.path.isdir(p):
            continue
        if entry.startswith("wxid_") or os.path.isdir(os.path.join(p, "db_storage")):
            cands.add(entry)
            norm = normalize_wxid(entry)
            if norm:
                cands.add(norm)
    return sorted(cands)


# ════════════════════════════════════════════════════════════
# V2 模板收集与密钥验证
# ════════════════════════════════════════════════════════════

def collect_v2_files(data_root, account_dir=None):
    """收集 V2 文件：目标账号的 Sns 缓存 + 聊天 attach 的 _t.dat / .dat。"""
    files = []
    roots = [os.path.join(data_root, account_dir)] if account_dir else [data_root]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dp, _dn, fns in os.walk(root):
            if "Sns" in dp.split(os.sep):
                for fn in fns:
                    files.append(os.path.join(dp, fn))
        for pat in ("msg/attach/*/*/Img/*_t.dat",
                    "msg/attach/*/*/Img/*.dat"):
            for p in glob.glob(os.path.join(root, pat)):
                files.append(p)
    return files


def is_v2(path):
    try:
        with open(path, "rb") as f:
            return f.read(6) == V2_MAGIC
    except OSError:
        return False


def get_v2_templates(files, max_templates=3):
    """取多个不同的 V2 模板密文（[0xF:0x1F] 16 字节），用于交叉验证。"""
    out, seen = [], set()
    for p in sorted(files, key=os.path.getmtime, reverse=True):
        try:
            with open(p, "rb") as f:
                head = f.read(0x1F)
        except OSError:
            continue
        if len(head) >= 0x1F and head[:6] == V2_MAGIC:
            ct = head[0xF:0x1F]
            if ct not in seen:
                seen.add(ct)
                out.append(ct)
                if len(out) >= max_templates:
                    break
    return out


def verify_aes_key(aes_key_ascii, template_ct):
    """AES-128-ECB 解模板密文，检查是否为图片魔数。"""
    if not aes_key_ascii or not template_ct or len(template_ct) != 16:
        return False
    key = aes_key_ascii.encode("ascii", errors="ignore")[:16]
    if len(key) < 16:
        return False
    try:
        dec = AES.new(key, AES.MODE_ECB).decrypt(template_ct)
    except (ValueError, TypeError):
        return False
    return any(dec.startswith(m) for m in IMAGE_MAGICS)


def verify_aes_key_against_all(aes_key_ascii, templates):
    """多个不同模板全部通过才算命中（防短魔数偶然碰撞）。"""
    return bool(templates) and all(
        verify_aes_key(aes_key_ascii, ct) for ct in templates)


def aligned_aes_size(aes_size):
    """PKCS7 对齐：不足 16 的倍数补到下一个 16 倍数；刚好 16 倍数时补一整块。"""
    rem = (aes_size % 16 + 16) % 16
    return aes_size + (16 - rem)


def decrypt_v2_file(path, aes_key, xor_key):
    """完整解密 V2 文件，返回 (bytes, 格式) 或 (None, None)。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None, None
    if len(data) < 15 or data[:6] != V2_MAGIC:
        return None, None
    aes_size, xor_size = struct.unpack_from("<LL", data, 6)
    aligned = aligned_aes_size(aes_size)
    off = 15
    if off + aligned > len(data):
        return None, None
    try:
        dec_aes = Padding.unpad(
            AES.new(aes_key[:16], AES.MODE_ECB).decrypt(data[off:off + aligned]),
            AES.block_size)
    except ValueError:
        return None, None
    off += aligned
    raw_end = len(data) - xor_size
    raw = data[off:raw_end] if off < raw_end else b""
    xored = bytes(b ^ xor_key for b in data[raw_end:])
    result = dec_aes + raw + xored
    if result[:3] == b"\xFF\xD8\xFF":
        return result, "jpg"
    if result[:4] == b"\x89PNG":
        return result, "png"
    if result[:3] == b"GIF":
        return result, "gif"
    if result[:4] == b"RIFF" and result[8:12] == b"WEBP":
        return result, "webp"
    if result[:4] == b"wxgf":
        return result, "hevc"
    return None, None


def is_complete_image(data, fmt):
    """严格校验：完整图片必须带正确结尾标记（JPEG=FF D9，PNG=IEND）。"""
    if not data:
        return False
    if fmt == "jpg":
        return data[-2:] == b"\xFF\xD9"
    if fmt == "png":
        return data[-8:] == b"\x49\x45\x4E\x44\xAE\x42\x60\x82"
    if fmt == "gif":
        return data[-1:] == b"\x3B"
    return False


def full_decrypt_verify(files, aes_key, xor_key):
    """完整解密多个 V2 文件做最终确认，统计头部有效 / 完整结尾。"""
    v2 = [p for p in files if is_v2(p)]
    ok_head = ok_full = 0
    for p in v2[:40]:
        res, fmt = decrypt_v2_file(p, aes_key, xor_key)
        if res:
            ok_head += 1
            if is_complete_image(res, fmt):
                ok_full += 1
    return ok_head, ok_full, len(v2)


def derive_via_kvcomm(data_root, files, log, account_dir=None):
    """主路径：kvcomm code + wxid 派生密钥，多模板交叉验证。

    密钥是每个账号独立的，模板必须取自同一账号的缓存，
    所以按账号目录分别收集模板、分别验证。
    """
    kvcomm_dirs = find_kvcomm_dirs()
    if not kvcomm_dirs:
        log("[1] 未找到 kvcomm 缓存目录，走内存扫描回退")
        return None
    log("[1] kvcomm 目录: %s" % ", ".join(kvcomm_dirs))

    codes = set()
    for d in kvcomm_dirs:
        codes |= collect_kvcomm_codes(d)
    codes = sorted(codes)
    if not codes:
        log("[1] kvcomm 目录中没有 key_<code>_*.statistic 文件，走内存扫描回退")
        return None
    log("[1] 找到 code 候选: %s" % codes)

    # 按账号组织：账号目录 -> (wxid 候选, 该账号自己的 V2 文件)
    account_groups = []
    if account_dir:
        acc_path = os.path.join(data_root, account_dir)
        if os.path.isdir(acc_path):
            account_groups.append(
                (account_dir, [account_dir, normalize_wxid(account_dir)],
                 collect_v2_files(data_root, account_dir)))
    else:
        try:
            entries = sorted(os.listdir(data_root))
        except OSError:
            entries = []
        for entry in entries:
            acc_path = os.path.join(data_root, entry)
            if not os.path.isdir(acc_path):
                continue
            if not (entry.startswith("wxid_")
                    or os.path.isdir(os.path.join(acc_path, "db_storage"))):
                continue
            acc_files = collect_v2_files(data_root, entry)
            if not any(is_v2(p) for p in acc_files):
                continue
            account_groups.append(
                (entry, [entry, normalize_wxid(entry)], acc_files))

    for acc_name, wxids, acc_files in account_groups:
        templates = get_v2_templates(acc_files)
        if not templates:
            continue
        log("[1] 账号 %s：V2 模板 %d 个" % (acc_name, len(templates)))
        for code in codes:
            for wxid in wxids:
                xor_key, aes_key = derive_image_keys(code, wxid)
                if verify_aes_key_against_all(aes_key, templates):
                    ok_head, ok_full, total = full_decrypt_verify(
                        acc_files, aes_key.encode("ascii")[:16], xor_key)
                    log("[OK] kvcomm 推导命中: code=%d wxid=%s"
                        % (code, wxid))
                    log("     xor_key=0x%02x  aes_key=%s" % (xor_key, aes_key))
                    log("     完整解密验证: 头部有效 %d/%d，完整结尾 %d 张"
                        % (ok_head, min(total, 40), ok_full))
                    return {
                        "aes_key": aes_key,
                        "xor_key": xor_key,
                        "uin": code,
                        "wxid": wxid,
                        "account_dir": acc_name,
                        "source": "kvcomm",
                    }
    log("[1] 所有账号的 (code × wxid) 组合都未通过验证，走内存扫描回退")
    return None


# ════════════════════════════════════════════════════════════
# 回退路径：内存扫描
# ════════════════════════════════════════════════════════════

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80

RE_KEY32 = re.compile(rb"(?<![a-zA-Z0-9])[a-zA-Z0-9]{32}(?![a-zA-Z0-9])")
RE_KEY16 = re.compile(rb"(?<![a-zA-Z0-9])[a-zA-Z0-9]{16}(?![a-zA-Z0-9])")


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.ReadProcessMemory.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
]
kernel32.VirtualQueryEx.argtypes = [
    wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def find_weixin_pids():
    snap = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snap in (-1, ctypes.c_void_p(-1).value):
        return []
    pids = []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == "weixin.exe":
                pids.append(entry.th32ProcessID)
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    return pids


def try_key(key_bytes, ciphertext):
    try:
        dec = AES.new(key_bytes[:16], AES.MODE_ECB).decrypt(ciphertext)
    except (ValueError, TypeError):
        return None
    return any(dec.startswith(m) for m in IMAGE_MAGICS)


def is_rw_protect(protect):
    return bool(protect & (PAGE_READWRITE | PAGE_WRITECOPY |
                           PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY))


def enumerate_regions(h_process):
    rw, other = [], []
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()
    while addr < 0x7FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(
                h_process, ctypes.c_void_p(addr),
                ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT
                and mbi.Protect != PAGE_NOACCESS
                and not (mbi.Protect & PAGE_GUARD)
                and 0 < mbi.RegionSize <= 50 * 1024 * 1024):
            reg = (mbi.BaseAddress, mbi.RegionSize)
            (rw if is_rw_protect(mbi.Protect) else other).append(reg)
        nxt = addr + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return rw, other


def scan_region(h_process, base_addr, region_size, ciphertext, stats):
    buf = ctypes.create_string_buffer(region_size)
    got = ctypes.c_size_t(0)
    if not kernel32.ReadProcessMemory(
            h_process, ctypes.c_void_p(base_addr), buf,
            region_size, ctypes.byref(got)):
        return None
    data = buf.raw[:got.value]
    if len(data) < 16:
        return None
    for m in RE_KEY32.finditer(data):
        stats["k32"] += 1
        key = m.group()
        if try_key(key[:16], ciphertext):
            return key[:16].decode("ascii")
        if try_key(key, ciphertext):
            return key.decode("ascii")
    for m in RE_KEY16.finditer(data):
        stats["k16"] += 1
        key = m.group()
        if try_key(key, ciphertext):
            return key.decode("ascii")
    return None


def scan_memory_for_aes_key(pid, ciphertext, log):
    h = kernel32.OpenProcess(
        PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        log("  无法打开进程 %d（请以管理员身份运行）" % pid)
        return None
    try:
        rw, other = enumerate_regions(h)
        stats = {"k32": 0, "k16": 0}
        for phase, regions in (("可读写内存", rw), ("全部内存", other)):
            log("  扫描 %s（%d 个区域）..." % (phase, len(regions)))
            for ba, rs in regions:
                hit = scan_region(h, ba, rs, ciphertext, stats)
                if hit:
                    return hit
        log("  未命中（候选 32位:%d，16位:%d）" % (stats["k32"], stats["k16"]))
        return None
    finally:
        kernel32.CloseHandle(h)


def scan_via_memory(data_root, files, log):
    """回退路径：内存扫描（需微信运行且已在朋友圈打开过图片）。"""
    templates = get_v2_templates(files)
    if not templates:
        log("[2] 没有 V2 模板文件，无法验证（请先在朋友圈点开 2-3 张图片）")
        return None
    ct = templates[0]
    pids = find_weixin_pids()
    if not pids:
        log("[2] 微信未运行")
        return None
    for pid in pids:
        log("[2] 扫描进程 %d ..." % pid)
        key = scan_memory_for_aes_key(pid, ct, log)
        if key:
            # 用所有模板交叉验证，再完整解密确认
            if not verify_aes_key_against_all(key, templates):
                log("[2] 内存命中的密钥未通过多模板验证，继续")
                continue
            xor_key = None
            ok_head, ok_full, total = full_decrypt_verify(
                files, key.encode("ascii")[:16], xor_key)
            log("[OK] 内存扫描命中: aes_key=%s" % key)
            log("     完整解密验证: 头部有效 %d/%d" % (ok_head, min(total, 40)))
            return {
                "aes_key": key,
                "xor_key": xor_key,
                "uin": None,
                "wxid": None,
                "source": "memory_scan",
            }
    log("[2] 内存扫描未找到密钥")
    return None


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════

DATA_ROOTS = [
    os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
]


def main():
    ap = argparse.ArgumentParser(description="微信4.x 朋友圈图片密钥提取")
    ap.add_argument("--datadir", help="微信数据目录")
    ap.add_argument("--account-dir", help="指定账号目录名（如 wxid_xxx_abcd）")
    ap.add_argument("--out", help="密钥输出 json 路径")
    args = ap.parse_args()

    def log(msg):
        print(msg, flush=True)

    data_root = args.datadir
    if not data_root:
        for r in DATA_ROOTS:
            if os.path.isdir(r):
                data_root = r
                break
    if not data_root or not os.path.isdir(data_root):
        log("找不到微信数据目录，请用 --datadir 指定")
        return 1
    out_path = os.path.abspath(args.out or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "图片密钥.json"))

    log("数据目录: %s" % data_root)
    log("")
    log("※ 提示：请确认已在微信朋友圈点开浏览过 2-3 张图片，")
    log("  并保持其中一张图片处于打开状态，再运行本脚本。")
    log("")

    files = collect_v2_files(data_root, args.account_dir)
    v2_count = sum(1 for p in files if is_v2(p))
    log("V2 缓存文件: %d 个" % v2_count)
    if not v2_count:
        log("没有 V2 缓存文件（请先在朋友圈点开 2-3 张图片）")
        return 1

    result = derive_via_kvcomm(data_root, files, log, args.account_dir)
    if not result:
        log("")
        log("[2] === 回退：内存扫描 ===")
        result = scan_via_memory(data_root, files, log)
    if not result:
        log("")
        log("获取失败。请检查：")
        log("  1. 微信已登录且朋友圈打开过 2-3 张图片，当前保持一张打开")
        log("  2. 以管理员身份重新运行")
        return 2

    data = dict(result)
    data["found_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log("")
    log("密钥已保存: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
