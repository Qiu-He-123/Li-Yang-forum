#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 4.x 数据库密钥捕获（INT3 代码断点版，全部自研，无第三方 DLL）。

原理：
  1. 微信登录时会在内部函数 setCipherKey 中写入数据库密钥，
     调用约定下 rdx -> struct { +0x8: 密钥指针, +0x10: 长度=32 }。
  2. 每个微信版本该函数的偏移（RVA）不同，开发期对每个版本离线定位一次，
 维护【版本 -> RVA】表；未收录版本启动时对安装目录里的 Weixin.dll
 文件做一次离线定位（不扫描进程内存）。
  3. 断点采用 INT3(0xCC) + VEH 方案：把 setCipherKey 首字节临时改为 0xCC，
     登录首次调用时触发异常，回调里读 RDX+8 拿到密钥后立即还原字节，
     代码页恢复原样，对微信运行无影响。
  4. 密钥校验用真实数据库做 HMAC，绝不与任何示例/已知值比对。

流程：一键 = 杀掉微信 -> 重新启动 -> 附加 -> 挂断点 ->
      登录（自动恢复或扫码）-> 异常回调读 RDX+8 -> HMAC 校验 -> 写入 db_key.txt。

用法：
  python capture_key_hwbp.py            # 默认：重启微信并等待登录
  python capture_key_hwbp.py --attach   # 附加到当前正在运行的微信（不重启）
  python capture_key_hwbp.py --timeout 300
"""

import argparse
import json
import os
import struct
import subprocess
import sys
import time

try:
    import frida
except ImportError:
    print("缺少 frida，请先: pip install frida")
    sys.exit(1)

try:
    from db_decrypt import derive_keys, page_hmac
except ImportError:
    derive_keys = None
    page_hmac = None


HERE = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(HERE, "db_key.txt")

# 版本 -> setCipherKey RVA（已收录版本直接用；未收录版本启动时读安装文件定位）
RVA_TABLE = {
    "4.1.12.53": 0x5DEA60,
}

# setCipherKey 特征序列（4.1.2 起跨版本稳定）
SETCIPHERKEY_SIG = bytes.fromhex(
    "245048C74500FEFFFFFF4489CF4489C34989D64889CE4889")
# 特征命中点前 15 字节应为函数序言尾部
SETCIPHERKEY_PRE = bytes.fromhex("55415741565657534883EC58488D6C")


def locate_rva(dll_path):
    """读取安装目录里的 Weixin.dll 文件，定位 setCipherKey 的 RVA。
    只对未收录版本执行一次文件扫描，不扫描进程内存。"""
    if not dll_path or not os.path.isfile(dll_path):
        return None
    try:
        with open(dll_path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    try:
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        nsec = struct.unpack_from("<H", data, pe + 6)[0]
        optsize = struct.unpack_from("<H", data, pe + 20)[0]
        sec_off = pe + 24 + optsize
        secs = []
        for i in range(nsec):
            off = sec_off + i * 40
            vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", data, off + 8)
            secs.append((vaddr, vsize, roff, rsize))
    except (struct.error, IndexError):
        return None

    def fo2rva(fo):
        for vaddr, vsize, roff, rsize in secs:
            if roff <= fo < roff + rsize:
                return vaddr + (fo - roff)
        return None

    sig = SETCIPHERKEY_SIG
    pre = SETCIPHERKEY_PRE
    start = 0
    while True:
        i = data.find(sig, start)
        if i < 0:
            break
        if i >= len(pre) and data[i - len(pre):i] == pre:
            return fo2rva(i - 15)
        start = i + 1
    return None


def version_ok(ver):
    """版本门槛：只支持微信 4.x。返回 (允许, 提示)。"""
    try:
        parts = [int(x) for x in ver.split(".")]
    except ValueError:
        return False, "无法解析微信版本: %s" % ver
    if not parts:
        return False, "无法解析微信版本: %s" % ver
    if parts[0] < 4:
        return False, "微信版本过低（当前 %s），本工具仅支持 4.x 及以上版本" % ver
    return True, ""


# 兜底扫描位置（注册表优先，GUI 支持手动选择）
INSTALL_ROOTS = [
    r"C:\Program Files\Tencent\Weixin",
    r"C:\Program Files (x86)\Tencent\Weixin",
    os.path.expandvars(r"%LOCALAPPDATA%\Tencent\Weixin"),
]

# 微信数据目录（账号下 *.db）
DATA_ROOTS = [
    os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files\All Users"),
    os.path.expandvars(r"%USERPROFILE%\Documents\wcf"),
]

AGENT = r"""
"use strict";

const RVA = %(rva)d;
let target = null;
let done = false;
let originalByte = 0;

function init() {
  const mod = Process.getModuleByName("Weixin.dll");
  target = mod.base.add(RVA);
  originalByte = target.readU8();
  // INT3 代码断点：把 setCipherKey 首字节临时改为 0xCC
  Memory.protect(target, 1, "rwx");
  target.writeU8(0xCC);

  Process.setExceptionHandler(function (details) {
    const ctx = details.context;
    try {
      if (details.type === "breakpoint" && ctx.rip.equals(target)) {
        let captured = false;
        if (!done) {
          const rdx = ctx.rdx;
          const keyPtr = rdx.add(8).readPointer();
          const size = rdx.add(0x10).readU32();
          if (size === 32) {
            const arr = Array.from(new Uint8Array(keyPtr.readByteArray(32)));
            const hex = arr.map(b => b.toString(16).padStart(2, "0")).join("");
            done = true;
            captured = true;
            send({
              type: "key",
              hex: hex,
              tid: details.threadId,
              rdx: rdx.toString(),
              keyPtr: keyPtr.toString()
            });
          }
        }
        // 断点必须先还原再继续执行，否则同一指令会再次触发
        target.writeU8(originalByte);
        if (!done && !captured) {
          // 结构异常（罕见）：下一次调用前重新挂上断点
          setTimeout(() => {
            if (!done) target.writeU8(0xCC);
          }, 0);
        }
        return true; // 已处理，恢复执行
      }
    } catch (e) {
      send({ type: "err", msg: String(e) });
    }
    return false;
  });

  send({ type: "ready", base: mod.base.toString(), target: target.toString(),
         patched: true });
}

(function waitModule() {
  const m = Process.findModuleByName("Weixin.dll");
  if (m) {
    try {
      init();
    } catch (e) {
      send({ type: "err", msg: String(e) });
    }
  } else {
    setTimeout(waitModule, 100);
  }
})();
"""


def registry_weixin_dir():
    """从注册表读取微信安装目录，找不到返回 None。"""
    import winreg
    candidates = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tencent\Weixin", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Weixin",
         "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Weixin",
         "InstallLocation"),
    ]
    for hive, sub, name in candidates:
        try:
            with winreg.OpenKey(hive, sub) as k:
                val, _ = winreg.QueryValueEx(k, name)
                if val and os.path.isdir(val):
                    return val
        except OSError:
            continue
    return None


def _scan_root(root):
    """在指定根目录里找微信（Weixin.exe + 版本目录），返回 (版本, exe路径)。"""
    best = None
    if not os.path.isdir(root):
        return None, None
    # 新版布局：Weixin.exe 在顶层，版本目录（如 4.1.12.53）里是 Weixin.dll
    top_exe = os.path.join(root, "Weixin.exe")
    if os.path.isfile(top_exe):
        for entry in os.listdir(root):
            dll = os.path.join(root, entry, "Weixin.dll")
            if os.path.isfile(dll):
                try:
                    ver = entry
                    if ver[0].isdigit() and ver.count(".") >= 2:
                        key = tuple(int(x) for x in ver.split("."))
                        if best is None or key > best[0]:
                            best = (key, ver, top_exe)
                except Exception:
                    continue
    # 旧版布局：Weixin.exe 直接在版本目录里
    for entry in os.listdir(root):
        exe = os.path.join(root, entry, "Weixin.exe")
        if os.path.isfile(exe):
            try:
                ver = os.path.basename(os.path.dirname(exe))
                if ver[0].isdigit() and ver.count(".") >= 2:
                    key = tuple(int(x) for x in ver.split("."))
                    if best is None or key > best[0]:
                        best = (key, ver, exe)
            except Exception:
                continue
    if best:
        return best[1], best[2]
    return None, None


def find_weixin_exe(manual_dir=None):
    """返回 (版本, exe路径)。优先手动指定目录，其次注册表，最后兜底常见位置。"""
    if manual_dir:
        return _scan_root(manual_dir)
    reg = registry_weixin_dir()
    if reg:
        r = _scan_root(reg)
        if r != (None, None):
            return r
    for root in INSTALL_ROOTS:
        r = _scan_root(root)
        if r != (None, None):
            return r
    return None, None


def find_weixin_pid():
    try:
        import psutil
        best = None
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            if (p.info["name"] or "").lower() == "weixin.exe":
                if best is None or p.info["memory_info"].rss > best[1]:
                    best = (p.info["pid"], p.info["memory_info"].rss)
        return best[0] if best else None
    except ImportError:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True).stdout
        for line in out.strip().splitlines():
            parts = line.split(",")
            if len(parts) >= 2:
                return int(parts[1].strip('"'))
    return None


def kill_weixin():
    subprocess.run(["taskkill", "/IM", "Weixin.exe", "/F", "/T"],
                   capture_output=True)
    for _ in range(60):
        if find_weixin_pid() is None:
            return True
        time.sleep(0.1)
    return False


def start_weixin(exe):
    return subprocess.Popen([exe], cwd=os.path.dirname(exe))


def attach_loop(pid, timeout):
    """进程刚启动时 Frida 可能尚未就绪，轮询附加。"""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            return frida.attach(pid)
        except Exception as e:
            last_err = e
            time.sleep(0.05)
    raise RuntimeError("附加微信失败: %s" % last_err)


def find_db_candidates(limit=8):
    """在微信数据目录里找 .db 文件（用于密钥校验），按大小排序取前几个。"""
    found = []
    for root in DATA_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn.lower().endswith(".db") and not fn.lower().endswith(".db.dec.db"):
                    p = os.path.join(dirpath, fn)
                    try:
                        found.append((os.path.getsize(p), p))
                    except OSError:
                        pass
    found.sort()
    return [p for _s, p in found[:limit]]


def verify_key(db_path, key_hex):
    """用真实数据库第 1 页 HMAC 校验密钥。返回 (ok, msg)。"""
    if derive_keys is None:
        return False, "缺少 db_decrypt 模块，无法校验"
    try:
        key = bytes.fromhex(key_hex)
    except ValueError:
        return False, "密钥不是合法 hex"
    if len(key) != 32:
        return False, "密钥长度不是 32 字节"
    try:
        with open(db_path, "rb") as f:
            data = f.read(4096)
    except OSError as e:
        return False, str(e)
    if len(data) < 4096:
        return False, "文件过小"
    if data[:16] == b"SQLite format 3\x00":
        return False, "该库已是明文，无法用于校验"
    salt = data[:16]
    enc_key, mac_key = derive_keys(key, salt)
    expect = page_hmac(data, mac_key, 16, 1)
    reserve = (16 + 64 + 15) // 16 * 16
    stored = data[4096 - reserve + 16: 4096 - reserve + 16 + 64]
    if expect != stored:
        return False, "HMAC 校验失败（密钥不匹配）"
    return True, "HMAC 校验通过"


def account_dir_of(db_path):
    """从数据库路径反推账号目录（xwechat_files/<wxid>）。"""
    p = db_path
    while True:
        parent = os.path.dirname(p)
        if parent == p:
            return None
        if os.path.basename(parent).startswith("wxid_"):
            return os.path.basename(parent)
        p = parent


def run_capture(progress=None, timeout=240, attach_mode=False, rva=None,
                weixin_dir=None):
    """完整抓取流程。progress(msg) 接收阶段指引。
    返回 (exit_code, key_hex, account_dir)。"""
    if progress is None:
        progress = lambda s: print(s, flush=True)

    ver, exe = find_weixin_exe(manual_dir=weixin_dir)
    if not exe:
        progress("未找到微信安装目录")
        return 1, None, None
    ok, why = version_ok(ver)
    if not ok:
        progress(why)
        return 1, None, None
    rva = rva if rva is not None else RVA_TABLE.get(ver)
    if rva is None:
        dll = None
        base_dir = os.path.dirname(exe)
        for cand in (os.path.join(base_dir, ver, "Weixin.dll"),
                     os.path.join(base_dir, "Weixin.dll")):
            if os.path.isfile(cand):
                dll = cand
                break
        rva = locate_rva(dll)
        if rva is None:
            progress("版本 %s 未收录，且未能从安装目录定位断点地址。"
                     "请更新工具，或把该版本号告知作者" % ver)
            return 1, None, None
        progress("版本 %s 未收录，已从安装文件定位断点地址 0x%X"
                 % (ver, rva))
    progress("微信版本: %s" % ver)
    progress("setCipherKey RVA: 0x%X" % rva)

    if attach_mode:
        pid = find_weixin_pid()
        if not pid:
            progress("没有正在运行的微信")
            return 1, None, None
        progress("附加到运行中的微信 PID %d（登录后再附加可能已错过密钥，最好重新登录）"
                 % pid)
        session = attach_loop(pid, 10)
    else:
        progress("正在关闭微信...")
        kill_weixin()
        time.sleep(0.3)
        progress("正在重新启动微信...")
        start_weixin(exe)
        pid = None
        for _ in range(300):
            pid = find_weixin_pid()
            if pid:
                break
            time.sleep(0.05)
        if not pid:
            progress("微信未能启动")
            return 1, None, None
        progress("微信已启动 PID %d，正在附加并安装硬件断点..." % pid)
        session = attach_loop(pid, 15)

    script = session.create_script(AGENT % {"rva": rva})
    result = {"key": None, "err": None}

    def on_message(msg, _data):
        if msg.get("type") == "send":
            p = msg["payload"]
            t = p.get("type")
            if t == "ready":
                progress("[断点] 已就绪：%s 目标 %s（INT3 已写入）"
                         % (p.get("base"), p.get("target")))
            elif t == "stats":
                pass  # 进度噪音，忽略
            elif t == "key":
                result["key"] = p["hex"]
                progress("[捕获] 密钥: %s" % p["hex"])
            elif t == "err":
                progress("[错误] %s" % p.get("msg"))
        elif msg.get("type") == "error":
            progress("脚本错误: %s" % msg.get("stack", msg))
            result["err"] = str(msg.get("stack", msg))

    script.on("message", on_message)
    script.load()

    progress("断点已挂好，请登录微信（自动恢复登录或扫码均可）...")
    deadline = time.time() + timeout
    while time.time() < deadline and result["key"] is None:
        time.sleep(0.2)

    script.unload()
    session.detach()

    key_hex = result["key"]
    if not key_hex:
        progress("超时未捕获到密钥。可再次运行并让微信重新登录一次。")
        return 2, None, None

    # 用真实数据库校验，而不是和任何示例值比对
    candidates = find_db_candidates()
    ok = False
    msg = "未找到任何数据库文件（请检查微信数据目录）"
    account = None
    if not candidates:
        # 找不到库：仍保存密钥（供手动验证），但明确警告
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key_hex.strip() + "\n")
        progress("未找到数据库文件用于 HMAC 校验，密钥已保存到 %s"
                 "（请确认微信数据目录后自行验证）" % KEY_FILE)
        return 0, key_hex, None
    for db in candidates:
        ok, msg = verify_key(db, key_hex)
        progress("校验 %s: %s" % (db, msg))
        if ok:
            account = account_dir_of(db)
            break
    if not ok:
        progress("密钥未通过任何数据库校验（%s）。当前版本 %s 若未收录，"
                 "可能是断点地址不匹配，请更新工具或升级微信。" % (msg, ver))
        return 3, key_hex, None

    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key_hex.strip() + "\n")
    progress("密钥已写入 %s" % KEY_FILE)
    progress("账号目录: %s" % (account or "未知"))
    progress("下一步：解密数据库，提取聊天记录。")
    return 0, key_hex, account


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach", action="store_true",
                    help="附加到正在运行的微信，不重启")
    ap.add_argument("--timeout", type=int, default=240,
                    help="等待登录超时秒数（默认 240）")
    ap.add_argument("--rva", type=lambda x: int(x, 0), default=None,
                    help="覆盖 RVA（调试用）")
    ap.add_argument("--dir", default=None,
                    help="手动指定微信安装目录")
    args = ap.parse_args()
    code, _key, _account = run_capture(timeout=args.timeout,
                                       attach_mode=args.attach,
                                       rva=args.rva,
                                       weixin_dir=args.dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
