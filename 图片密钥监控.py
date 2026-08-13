"""图片密钥后台监控（独立进程，不随服务器重启而中断）。

服务器运行期间：
- 每 1 秒检测微信是否运行、朋友圈页面是否打开（未打开显示红色标签）
- 每 10 秒检测朋友圈图片能否解密；失败时弹出「解密图片」窗口引导补密钥
- 主窗口下方显示图片密钥文件信息
整个过程不影响服务器运行，不需要重启服务器。

密钥说明（微信 4.x 新算法）：图片密钥按账号从本地 kvcomm 缓存推导，
微信重启不影响密钥；唯一前提是该账号先在朋友圈点开浏览过 2-3 张图片。
"""

import ctypes
import json
import os
import subprocess
import sys
import tkinter as tk
import tkinter.messagebox as messagebox
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT_DIR = ROOT / "微信同步客户端"
sys.path.insert(0, str(CLIENT_DIR))

import sns_reader  # noqa: E402
import client_common  # noqa: E402

CONFIG = CLIENT_DIR / "config.json"
IMAGE_KEY_TOOL = ROOT / "获取微信朋友圈" / "获取图片密钥.py"

IMAGE_INTERVAL_MS = max(3000, int(os.environ.get("LY_MONITOR_INTERVAL", "10000")))
WECHAT_INTERVAL_MS = 1000

_user32 = ctypes.windll.user32


def load_config() -> dict:
    if CONFIG.is_file():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _verify(datadir: str, image_key: dict) -> tuple[bool, str]:
    try:
        return sns_reader.verify_image_key(datadir, image_key, expect_wxid=datadir)
    except Exception as exc:
        return False, f"图片解密验证异常：{exc}"


def image_decrypt_ok(cfg: dict) -> tuple[bool, str]:
    image_key = sns_reader.load_image_key(cfg.get("images_key"))
    if not image_key:
        return False, "缺少 图片密钥.json"
    datadir = cfg.get("datadir")
    if datadir:
        ok, msg = _verify(datadir, image_key)
        if ok:
            return True, msg
    exp = sns_reader._load_exporter()
    data_root = datadir or exp.find_data_root()
    last_msg = msg if datadir else "未找到图片缓存"
    if data_root:
        for acc, _p in exp.find_sns_db_candidates(data_root):
            ok, msg = _verify(acc, image_key)
            if ok:
                return True, f"{msg}（账号：{Path(acc).name}）"
            last_msg = msg
    # 现有密钥全部无效：按新算法（kvcomm）自动重新推导当前账号的密钥并保存
    if datadir:
        derived = sns_reader.derive_image_key_for_account(
            sns_reader.data_root_of(datadir), datadir
        )
        if derived:
            ok, msg = _verify(datadir, derived)
            if ok:
                client_common.save_image_key_file(Path(datadir).name, derived)
                return True, msg + "（已按新算法自动推导并保存）"
            last_msg = msg
    return False, last_msg


def wechat_running() -> bool:
    for name in ("Weixin.exe", "WeChat.exe"):
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                capture_output=True,
                text=True,
                timeout=8,
            ).stdout
            if name.lower() in out.lower():
                return True
        except Exception:
            continue
    return False


def _window_titles_of(pid: int) -> list[str]:
    titles: list[str] = []
    top_hwnds: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        pid_out = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if pid_out.value == pid:
            top_hwnds.append(hwnd)
            if _user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                _user32.GetWindowTextW(hwnd, buf, 512)
                if buf.value:
                    titles.append(buf.value)
        return True

    _user32.EnumWindows(_cb, 0)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _ccb(hwnd, _lparam):
        buf = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, buf, 512)
        if buf.value:
            titles.append(buf.value)
        return True

    for hwnd in top_hwnds:
        _user32.EnumChildWindows(hwnd, _ccb, 0)
    return titles


def wechat_pids() -> list[int]:
    pids = []
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
        ).stdout
        for line in out.splitlines():
            if "Weixin.exe" in line or "WeChat.exe" in line:
                parts = line.split('","')
                if len(parts) >= 2:
                    try:
                        pids.append(int(parts[1].strip('"')))
                    except ValueError:
                        pass
    except Exception:
        pass
    return pids


def moments_page_open() -> bool:
    for pid in wechat_pids():
        for title in _window_titles_of(pid):
            if "朋友圈" in title:
                return True
    return False


def image_key_info(cfg: dict) -> str:
    path = cfg.get("images_key") or "（未配置）"
    ik = sns_reader.load_image_key(cfg.get("images_key"))
    if not ik:
        return f"图片密钥文件：{path}\n状态：缺失或格式错误"
    aes = str(ik.get("aes_key") or "")
    masked = f"{aes[:6]}…{aes[-4:]}" if len(aes) > 10 else aes
    xor = ik.get("xor_key")
    xor_txt = f"0x{xor:02X}" if isinstance(xor, int) else str(xor)
    return f"图片密钥文件：{path}\nAES: {masked}    XOR: {xor_txt}"


class MonitorWindow:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.popup_open = False
        self.last_ok: bool | None = None

        self.root = tk.Tk()
        self.root.title("立洋社区 - 微信朋友圈监控")
        self.root.geometry("560x360")
        self.root.resizable(False, False)

        tk.Label(
            self.root,
            text="微信朋友圈监控（服务器运行中）",
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(pady=(14, 6))

        info = tk.Frame(self.root)
        info.pack(fill="x", padx=20, pady=4)
        tk.Label(info, text="微信状态", font=("Microsoft YaHei UI", 10), fg="#666", width=10, anchor="w").grid(row=0, column=0, sticky="w")
        self.wechat_label = tk.Label(info, text="检测中…", font=("Microsoft YaHei UI", 10, "bold"), fg="#666")
        self.wechat_label.grid(row=0, column=1, sticky="w")

        tk.Label(info, text="朋友圈页面", font=("Microsoft YaHei UI", 10), fg="#666", width=10, anchor="w").grid(row=1, column=0, sticky="w")
        self.moments_label = tk.Label(info, text="检测中…", font=("Microsoft YaHei UI", 10, "bold"), fg="#666")
        self.moments_label.grid(row=1, column=1, sticky="w")

        tk.Label(info, text="图片解密", font=("Microsoft YaHei UI", 10), fg="#666", width=10, anchor="w").grid(row=2, column=0, sticky="w")
        self.image_label = tk.Label(info, text="检测中…", font=("Microsoft YaHei UI", 10, "bold"), fg="#666")
        self.image_label.grid(row=2, column=1, sticky="w")

        self.key_info = tk.Label(
            self.root,
            text=image_key_info(cfg),
            justify="left",
            font=("Microsoft YaHei UI", 9),
            fg="#555",
        )
        self.key_info.pack(padx=20, pady=6, anchor="w")

        tk.Label(
            self.root,
            text="微信状态/朋友圈页面每 1 秒检测，图片解密每 10 秒检测；失败会弹出补密钥窗口，不影响服务器。",
            font=("Microsoft YaHei UI", 9),
            fg="#888",
        ).pack(pady=2)

        btns = tk.Frame(self.root)
        btns.pack(pady=10)
        tk.Button(btns, text="立即检测", command=self.check_now, width=12, bg="#d9ead3").pack(side="left", padx=6)
        tk.Button(btns, text="解密图片", command=self.run_image_tool, width=12, bg="#fff3cd").pack(side="left", padx=6)
        tk.Button(btns, text="退出监控", command=self.root.destroy, width=12, bg="#f4cccc").pack(side="left", padx=6)

        self.check_wechat()
        self.check_now()
        self.root.after(WECHAT_INTERVAL_MS, self._tick_wechat)
        self.root.after(IMAGE_INTERVAL_MS, self._tick_image)
        auto_close = os.environ.get("LY_MONITOR_AUTOCLOSE_MS")
        if auto_close:
            self.root.after(int(auto_close), self.root.destroy)
        self.root.mainloop()

    # ---------- 微信状态（1 秒） ----------
    def check_wechat(self):
        running = wechat_running()
        if not running:
            self.wechat_label.config(text="✗ 微信未运行/未登录", fg="#c62828")
            self.moments_label.config(text="朋友圈未打开", fg="#c62828")
            return
        self.wechat_label.config(text="✓ 微信已登录（运行中）", fg="#2e7d32")
        if moments_page_open():
            self.moments_label.config(text="✓ 朋友圈已打开", fg="#2e7d32")
        else:
            self.moments_label.config(text="✗ 朋友圈未打开", fg="#c62828")

    def _tick_wechat(self):
        self.check_wechat()
        self.root.after(WECHAT_INTERVAL_MS, self._tick_wechat)

    # ---------- 图片解密（10 秒） ----------
    def check_now(self) -> tuple[bool, str]:
        ok, msg = image_decrypt_ok(self.cfg)
        self.last_ok = ok
        if ok:
            self.image_label.config(text=f"✓ 解密正常（{msg}）", fg="#2e7d32")
        else:
            self.image_label.config(text=f"✗ 解密失败：{msg}", fg="#c62828")
            self.show_popup()
        return ok, msg

    def _tick_image(self):
        self.check_now()
        self.root.after(IMAGE_INTERVAL_MS, self._tick_image)

    # ---------- 弹窗 ----------
    def show_popup(self):
        if self.popup_open:
            return
        self.popup_open = True
        win = tk.Toplevel(self.root)
        win.title("解密朋友圈图片")
        win.geometry("540x380")
        win.resizable(False, False)
        win.grab_set()

        def close():
            self.popup_open = False
            win.destroy()

        tk.Label(
            win,
            text="朋友圈图片无法解密（密钥与账号不匹配或缺少缓存）",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg="#c62828",
        ).pack(pady=(18, 8))
        tk.Label(
            win,
            text=(
                "请按以下步骤恢复：\n\n"
                "1. 打开微信并登录（保持登录）\n"
                "2. 进入「朋友圈」，点开浏览 2-3 张图片（保持一张打开）\n"
                "3. 点「解密图片」运行密钥工具\n"
                "4. 完成后点「重新检测」\n\n"
                "注：微信重启不会导致密钥失效，只有密钥与账号不匹配或缺少缓存时才需重抓。\n\n"
                "服务器不受影响，无需重启。"
            ),
            justify="left",
            font=("Microsoft YaHei UI", 10),
        ).pack(padx=24, pady=6)
        btns = tk.Frame(win)
        btns.pack(pady=14)
        tk.Button(btns, text="解密图片", command=self.run_image_tool, width=14, bg="#fff3cd").pack(side="left", padx=6)
        tk.Button(btns, text="重新检测", command=lambda: (close(), self.check_now()), width=12, bg="#d9ead3").pack(side="left", padx=6)
        tk.Button(btns, text="稍后再说", command=close, width=10, bg="#f0f0f0").pack(side="left", padx=6)

    def run_image_tool(self):
        if not IMAGE_KEY_TOOL.is_file():
            messagebox.showerror("提示", f"找不到图片密钥工具：\n{IMAGE_KEY_TOOL}")
            return
        subprocess.Popen([sys.executable, str(IMAGE_KEY_TOOL)])


if __name__ == "__main__":
    cfg = client_common.load_effective_config()
    if "--check" in sys.argv:
        ok, msg = image_decrypt_ok(cfg)
        print(("OK " if ok else "FAIL"), msg)
        print("wechat_running:", wechat_running())
        print("moments_page_open:", moments_page_open())
        print(image_key_info(cfg).replace("\n", " | "))
        sys.exit(0 if ok else 1)
    MonitorWindow(cfg)
