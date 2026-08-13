"""立洋社区服务器启动器（分步向导）。

流程：
  第 1 步 选择微信号（昵称（微信号））
  第 2 步 数据库密钥页：能解密朋友圈数据库 → 自动跳过；失败 → 引导运行密钥工具重抓 db_key
  第 3 步 图片密钥页：能解密图片缓存 → 自动跳过；失败 → 引导点开两三张图片 + 解密图片
  第 4 步 启动服务器（迁移 + 后端 + 前端 + 可选同步客户端 + 浏览器）

服务器启动后，由独立的 图片密钥监控.py 常驻检测；微信闪退/重登导致图片解不开时
会弹出解密图片窗口，不需要重启服务器。
"""

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path

# 控制台统一 UTF-8，避免中文/符号在 GBK 控制台报编码错误
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
CLIENT_DIR = ROOT / "微信同步客户端"
sys.path.insert(0, str(CLIENT_DIR))

import sns_reader  # noqa: E402
import client_common  # noqa: E402

CONFIG = CLIENT_DIR / "config.json"
IMAGE_KEY_TOOL = ROOT / "获取微信朋友圈" / "获取图片密钥.py"
# 数据库密钥工具来自独立的 ai群聊 项目；换电脑后按相对位置探测：
# 优先同级目录（仓库旁的 ai群聊），其次仓库内，找不到则由向导提示
_DB_KEY_TOOL_CANDIDATES = [
    ROOT.parent / "ai群聊" / "取聊天记录_自研" / "聊天记录导出工具" / "key_grabber_ui.py",
    ROOT / "工具" / "key_grabber_ui.py",
]
DB_KEY_TOOL = next((p for p in _DB_KEY_TOOL_CANDIDATES if p.is_file()), _DB_KEY_TOOL_CANDIDATES[0])
MONITOR_PY = ROOT / "图片密钥监控.py"


def load_config() -> dict:
    if not CONFIG.is_file():
        example = CLIENT_DIR / "config.example.json"
        if example.is_file():
            shutil.copy2(example, CONFIG)
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else {}
    except (ValueError, OSError):
        cfg = {}
    # 兼容旧配置：补全 data_root
    if not cfg.get("data_root"):
        datadir = cfg.get("datadir") or ""
        if datadir and os.path.isdir(os.path.join(datadir, "db_storage")):
            cfg["data_root"] = str(Path(datadir).parent)
        else:
            cfg["data_root"] = datadir
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_key_hex(cfg: dict) -> str:
    key_file = cfg.get("key_file", "")
    if not key_file or not os.path.isfile(key_file):
        return ""
    try:
        return Path(key_file).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _self_identity(account_path: str, key_hex: str) -> tuple[str | None, str | None]:
    try:
        contacts = sns_reader.read_contacts(account_path, key_hex)
    except Exception:
        return None, None
    name = os.path.basename(account_path)
    self_wxid = name.rsplit("_", 1)[0] if name.startswith("wxid_") and "_" in name else name
    row = next((c for c in contacts if c.get("wxid") == self_wxid), None)
    if not row:
        return None, None
    nickname = (row.get("remark") or "").strip() or (row.get("nickname") or "").strip() or None
    return nickname, (row.get("wechat_id") or "").strip() or None


def account_label(acc: dict) -> str:
    if acc.get("nickname"):
        ident = acc.get("wechat_id") or acc["wxid_display"]
        return f"{acc['nickname']}（{ident}）"
    return acc["wxid_display"]


def resolve_data_root(cfg: dict) -> str:
    """微信数据根目录：优先 data_root；若指向账号目录（含 db_storage）则取其父级，保证列出全部账号。"""
    for key in ("data_root", "datadir"):
        dr = cfg.get(key) or ""
        if not dr or not os.path.isdir(dr):
            continue
        if os.path.isdir(os.path.join(dr, "db_storage")):
            return str(Path(dr).parent)
        return dr
    return ""


def scan_accounts(data_root: str, cfg: dict) -> list[dict]:
    out = []
    exp = sns_reader._load_exporter()
    if not data_root or not os.path.isdir(data_root):
        return out
    shared_key_hex = get_key_hex(cfg)
    for acc, p in exp.find_sns_db_candidates(data_root):
        ok = False
        acc_key_path = client_common.account_key_path(os.path.basename(acc))
        key_hex = ""
        if acc_key_path.is_file():
            try:
                key_hex = acc_key_path.read_text(encoding="utf-8").strip()
            except OSError:
                key_hex = ""
        if not key_hex:
            key_hex = shared_key_hex
        if key_hex:
            try:
                ok = exp.check_key(p, key_hex)
            except Exception:
                ok = False
        name = os.path.basename(acc)
        wxid_display = name.rsplit("_", 1)[0] if name.startswith("wxid_") and "_" in name else name
        nickname, wechat_id = (None, None)
        if ok:
            nickname, wechat_id = _self_identity(acc, key_hex)
        item = {
            "name": name,
            "path": acc,
            "sns_db": p,
            "key_ok": ok,
            "nickname": nickname,
            "wechat_id": wechat_id,
            "wxid_display": wxid_display,
        }
        item["label"] = account_label(item)
        out.append(item)
    return out


def db_decrypt_ok(cfg: dict, account_path: str) -> bool:
    key_hex = get_key_hex(cfg)
    if not key_hex:
        return False
    exp = sns_reader._load_exporter()
    sns_src = os.path.join(account_path, "db_storage", "sns", "sns.db")
    try:
        return os.path.isfile(sns_src) and exp.check_key(sns_src, key_hex)
    except Exception:
        return False


def image_decrypt_ok(cfg: dict, account_path: str) -> tuple[bool, str]:
    image_key = sns_reader.load_image_key(cfg.get("images_key"))
    if not image_key:
        return False, "缺少 图片密钥.json"
    try:
        return sns_reader.verify_image_key(account_path, image_key, expect_wxid=account_path)
    except Exception as exc:
        return False, f"图片解密验证异常：{exc}"


def ensure_image_key_usable(cfg: dict, acc: dict) -> tuple[bool, str]:
    """图片密钥能否使用：先验证现有密钥；不行就按新算法（kvcomm）自动重新推导并保存。"""
    ik = sns_reader.load_image_key(cfg.get("images_key"))
    if ik:
        ok, msg = sns_reader.verify_image_key(acc["path"], ik, expect_wxid=acc["path"])
        if ok:
            return True, msg
    else:
        msg = "缺少图片密钥"
    derived = sns_reader.derive_image_key_for_account(
        sns_reader.data_root_of(acc["path"]), acc["path"]
    )
    if derived:
        ok2, msg2 = sns_reader.verify_image_key(
            acc["path"], derived, expect_wxid=acc["path"]
        )
        if ok2:
            client_common.save_image_key_file(acc["name"], derived)
            return True, msg2 + "（已按新算法自动推导并保存）"
    return False, msg


def _decrypt_preview(account_path: str, images_key_path: str) -> tuple[bytes | None, str]:
    """真实解密一张最新 V2 朋友圈图片，返回 (PNG bytes, 源缓存路径)。
    用于在"图片解密成功"页面下方展示实际解出来的图片。
    """
    import io as _io

    image_key = sns_reader.load_image_key(images_key_path)
    if not image_key:
        return None, "缺少图片密钥，无法生成预览"
    try:
        from PIL import Image as PILImage
    except ImportError:
        return None, "缺少 Pillow，无法生成预览（不影响流程）"
    samples = sns_reader.find_v2_cache_images(account_path, limit=5)
    if not samples:
        return None, "该账号暂无 V2 图片缓存，无法生成预览"
    mod_path = ROOT / "获取微信朋友圈" / "下载朋友圈图片.py"
    spec = importlib.util.spec_from_file_location("sns_media_preview", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    aes_raw = image_key.get("aes_key", "")
    aes_key = bytes.fromhex(aes_raw) if len(aes_raw) == 32 else aes_raw.encode("ascii")[:16]
    xor_key = image_key.get("xor_key")
    for sample in samples:
        try:
            result, fmt = mod.decrypt_dat_file(sample, aes_key, xor_key)
            if not (result and fmt and mod.is_complete_image(result, fmt)):
                continue
            img = PILImage.open(_io.BytesIO(result))
            img.thumbnail((240, 240), PILImage.LANCZOS)
            buf = _io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue(), sample
        except Exception:
            continue
    return None, "解密结果未能生成预览"


def gate_checks(cfg: dict, account_path: str) -> list[tuple[str, bool, str]]:
    results = []
    key_hex = get_key_hex(cfg)
    if not key_hex:
        results.append(("数据库密钥 db_key.txt", False, "缺少 db_key.txt"))
    else:
        exp = sns_reader._load_exporter()
        sns_src = os.path.join(account_path, "db_storage", "sns", "sns.db")
        ok = os.path.isfile(sns_src) and exp.check_key(sns_src, key_hex)
        results.append(("朋友圈数据库解密", ok, "OK" if ok else "解密失败，密钥不匹配"))
    image_key = sns_reader.load_image_key(cfg.get("images_key"))
    results.append(
        ("图片密钥文件", image_key is not None, "OK" if image_key else "缺少 图片密钥.json")
    )
    if image_key:
        ok, msg = sns_reader.verify_image_key(account_path, image_key, expect_wxid=account_path)
        results.append(("图片解密验证", ok, msg))
    else:
        results.append(("图片解密验证", False, "需要先补齐图片密钥"))
    return results


def run_headless(cfg: dict) -> int:
    accounts = scan_accounts(resolve_data_root(cfg), cfg)
    print(f"找到 {len(accounts)} 个微信账号：")
    for i, acc in enumerate(accounts, 1):
        mark = "✅ 密钥匹配" if acc["key_ok"] else "❌ 需要解密"
        print(f"  {i}. {acc['label']}   [{mark}]")
        if acc["key_ok"]:
            for name, ok, msg in gate_checks(_account_cfg(cfg, acc), acc["path"]):
                print(f"     {'OK ' if ok else 'FAIL'} {name} - {msg}")
    return 0


def _account_cfg(cfg: dict, acc: dict) -> dict:
    """按账号的配置：密钥优先用账号目录里已保存的副本。"""
    out = dict(cfg)
    kf = client_common.account_key_path(acc["name"])
    if kf.is_file():
        out["key_file"] = str(kf)
    ikf = client_common.account_image_key_path(acc["name"])
    if ikf.is_file():
        out["images_key"] = str(ikf)
    out["datadir"] = acc["path"]
    return out


def _fetch_device_token(backend: Path) -> str:
    """调用后端脚本生成/读取设备令牌，返回 64 位 hex 或空串。"""
    py = backend / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        return ""
    try:
        result = subprocess.run(
            [str(py), "scripts/init_wechat_sync.py"],
            cwd=str(backend),
            capture_output=True,
            text=True,
            timeout=60,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                return line
    except Exception:
        pass
    return ""


GUIDE_DB = (
    "朋友圈数据库暂时解不开（db_key 不匹配或缺失）。\n\n"
    "请按以下步骤重抓数据库密钥：\n"
    "1. 保持微信登录（或准备重新登录）\n"
    "2. 点下方「运行密钥工具」，工具会自动重启微信并捕获密钥\n"
    "3. 工具提示登录微信后扫码/登录，等待捕获完成\n"
    "4. 捕获成功后会自动检测并进入下一步，无需手动操作\n"
)

GUIDE_IMAGE = (
    "图片缓存暂时解不开（密钥与当前账号不匹配，或该账号还没有图片缓存）。\n\n"
    "请按以下步骤恢复：\n"
    "1. 确认微信已登录该账号\n"
    "2. 打开「朋友圈」，点开浏览 2-3 张图片（保持一张打开）\n"
    "3. 点「解密图片」运行密钥工具\n"
    "4. 解密成功后会自动进入下一步，无需手动操作\n\n"
    "注：微信重启不会导致密钥失效，无需因重启而重抓。"
)


class StartupWindow:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.accounts: list[dict] = []
        self.test_mode = os.environ.get("LY_TEST_GUI") == "1"

        self.root = tk.Tk()
        self.selected = tk.StringVar()
        self.root.title("立洋社区 - 启动服务器（向导）")
        self.root.geometry("780x640")
        self.root.resizable(False, False)

        self.container = tk.Frame(self.root)
        self.container.pack(fill="both", expand=True)
        self.page_frames: list[tk.Frame] = []
        self._build_pages()
        self.show_page(0)
        self.rerun_accounts()

        auto_close = os.environ.get("LY_AUTOCLOSE_MS")
        if auto_close:
            self.root.after(int(auto_close), self.root.destroy)
        if self.test_mode:
            self.root.after(500, self._auto_test)
        self.root.mainloop()

    def _auto_test(self):
        """测试模式：自动选中密钥匹配的账号并走完向导，最后报告到达的页面。"""
        if not self.accounts:
            print("TEST FAIL: no accounts")
            self.root.destroy()
            return
        idx = next((i for i, a in enumerate(self.accounts) if a["key_ok"]), 0)
        self.selected.set(str(idx))
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.step1_next()
        self.root.after(3800, self._finish_test)

    def _finish_test(self):
        current = -1
        for i, f in enumerate(self.page_frames):
            if f.winfo_ismapped():
                current = i
        print(f"TEST wizard reached page index {current} (expect 3)")
        if current == 3:
            print("TEST OK")
        self.root.destroy()

    # ---------- 页面框架 ----------
    def _new_page(self, title: str) -> tk.Frame:
        page = tk.Frame(self.container)
        tk.Label(page, text=title, font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(18, 4))
        return page

    def _page_body(self, page: tk.Frame) -> tk.Frame:
        body = tk.Frame(page)
        body.pack(fill="both", expand=True, padx=24, pady=8)
        return body

    def _page_buttons(self, page: tk.Frame, buttons: list[tuple[str, callable, str]]) -> None:
        bar = tk.Frame(page)
        bar.pack(pady=12)
        for text, cmd, bg in buttons:
            tk.Button(bar, text=text, command=cmd, width=14, bg=bg).pack(side="left", padx=6)

    def show_page(self, index: int) -> None:
        for i, f in enumerate(self.page_frames):
            f.pack_forget()
        self.page_frames[index].pack(fill="both", expand=True)

    def _clear(self, frame: tk.Frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    # ---------- 第 1 步：选择微信号 ----------
    def _build_pages(self):
        p1 = self._new_page("第 1 步：选择要解密的微信号")
        self.page_frames.append(p1)
        self.listbox = tk.Listbox(p1, height=9, font=("Consolas", 10))
        self.listbox.pack(fill="x", padx=24, pady=6)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.p1_tip = tk.Label(p1, text="", font=("Microsoft YaHei UI", 10), fg="#666")
        self.p1_tip.pack(pady=4)
        self._page_buttons(
            p1,
            [
                ("手动选择目录", self.pick_data_root, "#e8f0fe"),
                ("刷新账号", self.rerun_accounts, "#f0f0f0"),
                ("下一步", self.step1_next, "#d9ead3"),
                ("退出", self.root.destroy, "#f4cccc"),
            ],
        )

        p2 = self._new_page("第 2 步：朋友圈数据库密钥")
        self.page_frames.append(p2)
        self.p2_status = tk.Label(p2, text="", font=("Microsoft YaHei UI", 12, "bold"))
        self.p2_status.pack(pady=6)
        self.p2_body = self._page_body(p2)
        self._page_buttons(
            p2,
            [("运行密钥工具", self.run_db_tool, "#fff3cd"), ("重新检测", self.step2_check, "#d9ead3"), ("返回", lambda: self.show_page(0), "#f0f0f0")],
        )

        p3 = self._new_page("第 3 步：朋友圈图片密钥")
        self.page_frames.append(p3)
        self.p3_status = tk.Label(p3, text="", font=("Microsoft YaHei UI", 12, "bold"))
        self.p3_status.pack(pady=6)
        self.p3_body = self._page_body(p3)
        self._page_buttons(
            p3,
            [("解密图片", self.run_image_tool, "#fff3cd"), ("重新检测", self.step3_check, "#d9ead3"), ("返回", lambda: self.show_page(1), "#f0f0f0")],
        )

        p4 = self._new_page("第 4 步：启动服务器")
        self.page_frames.append(p4)
        self.p4_body = self._page_body(p4)
        self.client_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            p4, text="同时启动微信同步客户端", variable=self.client_var, font=("Microsoft YaHei UI", 10)
        ).pack(pady=4)
        self._page_buttons(
            p4,
            [("启动服务器", self.start_server, "#d9ead3"), ("返回", lambda: self.show_page(2), "#f0f0f0"), ("退出", self.root.destroy, "#f4cccc")],
        )

    def rerun_accounts(self):
        self.accounts = scan_accounts(resolve_data_root(self.cfg), self.cfg)
        self.listbox.delete(0, tk.END)
        self.selected.set("")
        self.p1_tip.config(text="")
        if not self.accounts:
            self.listbox.insert(tk.END, "（未找到任何微信账号数据，可点「手动选择目录」指定微信数据位置）")
            return
        for acc in self.accounts:
            mark = "✅ 密钥匹配" if acc["key_ok"] else "❌ 需要解密"
            saved = "（已配置）" if client_common.account_config_path(acc["name"]).is_file() else ""
            self.listbox.insert(tk.END, f"{acc['label']}   [{mark}] {saved}")
        self.p1_tip.config(
            text=f"微信数据目录：{resolve_data_root(self.cfg)}　共 {len(self.accounts)} 个账号，请选择社区运营账号"
        )

    def pick_data_root(self):
        chosen = filedialog.askdirectory(
            title="选择微信数据目录（xwechat_files）",
            initialdir=resolve_data_root(self.cfg) or os.path.expanduser("~"),
        )
        if not chosen:
            return
        self.cfg["data_root"] = chosen
        save_config(self.cfg)
        self.rerun_accounts()

    def _on_select(self, _event):
        sel = self.listbox.curselection()
        if sel:
            self.selected.set(str(sel[0]))

    def _selected_account(self) -> dict | None:
        if not self.selected.get():
            messagebox.showerror("提示", "请先选择微信号")
            return None
        return self.accounts[int(self.selected.get())]

    def step1_next(self):
        acc = self._selected_account()
        if not acc:
            return
        self.cfg["datadir"] = acc["path"]
        self.cfg["current_account"] = acc["name"]
        save_config(self.cfg)
        # 每个账号独立保存，互不覆盖：密钥也复制到账号目录
        key_file = client_common.account_key_path(acc["name"])
        if acc["key_ok"] and not key_file.is_file():
            key_hex = get_key_hex(self.cfg)
            if key_hex:
                key_file.parent.mkdir(parents=True, exist_ok=True)
                key_file.write_text(key_hex + "\n", encoding="utf-8")
        # 图片密钥同样按账号单独保存：当前密钥能解开该账号缓存才复制
        acc_img = client_common.account_image_key_path(acc["name"])
        img_src = self.cfg.get("images_key") or ""
        if not acc_img.is_file() and img_src and os.path.isfile(img_src):
            try:
                ik = sns_reader.load_image_key(img_src)
                if ik:
                    img_ok, _m = sns_reader.verify_image_key(acc["path"], ik, expect_wxid=acc["path"])
                    if img_ok:
                        acc_img.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(img_src, acc_img)
            except Exception:
                pass
        overrides = {
            "datadir": acc["path"],
            "state_file": "state.json",
        }
        if key_file.is_file():
            overrides["key_file"] = str(key_file)
        if acc_img.is_file():
            overrides["images_key"] = str(acc_img)
        client_common.save_account_config(acc["name"], overrides)
        self.show_page(1)
        self.step2_check()

    # ---------- 第 2 步：数据库密钥 ----------
    def step2_check(self):
        acc = self._selected_account()
        if not acc:
            self.show_page(0)
            return
        ok = db_decrypt_ok(_account_cfg(self.cfg, acc), acc["path"])
        if ok:
            self.p2_status.config(text=f"✓ 数据库解密成功（{acc['label']}）", fg="#2e7d32")
            self._clear(self.p2_body)
            self.root.after(600, lambda: self.show_page(2) or self.step3_check())
        else:
            self.p2_status.config(text="✗ 数据库解密失败，需要重抓密钥", fg="#c62828")
            self._clear(self.p2_body)
            tk.Label(self.p2_body, text=GUIDE_DB, justify="left", font=("Microsoft YaHei UI", 10), fg="#7a3b12").pack(anchor="w")

    def run_db_tool(self):
        if not DB_KEY_TOOL.is_file():
            messagebox.showerror("提示", f"找不到数据库密钥工具：\n{DB_KEY_TOOL}")
            return
        proc = subprocess.Popen([sys.executable, str(DB_KEY_TOOL)])
        self.p2_status.config(text="密钥工具运行中，密钥生效后会自动进入下一步…", fg="#666")
        self.root.after(2000, lambda: self._poll_db_tool(proc, 120))

    def _poll_db_tool(self, proc: subprocess.Popen, remaining: int):
        acc = self._selected_account()
        if acc and db_decrypt_ok(_account_cfg(self.cfg, acc), acc["path"]):
            self.step2_check()  # 成功即自动进入下一步
            return
        if proc.poll() is not None and remaining <= 0:
            messagebox.showwarning(
                "提示",
                "密钥工具已结束但仍未捕获到有效密钥，请确认微信已登录后重试。",
            )
            return
        self.root.after(2000, lambda: self._poll_db_tool(proc, remaining - 1))

    # ---------- 第 3 步：图片密钥 ----------
    def step3_check(self):
        acc = self._selected_account()
        if not acc:
            self.show_page(0)
            return
        ok, msg = ensure_image_key_usable(_account_cfg(self.cfg, acc), acc)
        if ok:
            self._persist_image_key(acc)
            self.p3_status.config(text=f"✓ 图片解密成功（{msg}）", fg="#2e7d32")
            self._clear(self.p3_body)
            # 下方展示一张真实解出来的图片，再自动进入下一步
            acc_cfg = _account_cfg(self.cfg, acc)
            png_bytes, src = _decrypt_preview(acc["path"], acc_cfg.get("images_key") or "")
            if png_bytes:
                photo = tk.PhotoImage(data=png_bytes)
                self._preview_photo = photo  # 防止被 GC 回收
                tk.Label(self.p3_body, image=photo).pack(pady=8)
                tk.Label(
                    self.p3_body,
                    text=f"真实解密结果：{src}",
                    fg="#888",
                    font=("Microsoft YaHei UI", 9),
                ).pack()
            else:
                tk.Label(
                    self.p3_body,
                    text=f"（{src}）",
                    fg="#888",
                    font=("Microsoft YaHei UI", 9),
                ).pack(pady=6)
            self.root.after(2500, lambda: self.show_page(3))
        else:
            self.p3_status.config(text=f"✗ 图片解密失败：{msg}", fg="#c62828")
            self._clear(self.p3_body)
            tk.Label(self.p3_body, text=GUIDE_IMAGE, justify="left", font=("Microsoft YaHei UI", 10), fg="#7a3b12").pack(anchor="w")

    def _persist_image_key(self, acc: dict):
        """把验证通过的图片密钥复制到账号目录，该账号以后用自己的密钥，互不覆盖。"""
        src = _account_cfg(self.cfg, acc).get("images_key") or ""
        acc_img = client_common.account_image_key_path(acc["name"])
        if src and os.path.isfile(src):
            try:
                if not acc_img.is_file() or Path(src).resolve() != acc_img.resolve():
                    acc_img.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, acc_img)
            except OSError:
                pass
        overrides = {"datadir": acc["path"], "state_file": "state.json"}
        kf = client_common.account_key_path(acc["name"])
        if kf.is_file():
            overrides["key_file"] = str(kf)
        if acc_img.is_file():
            overrides["images_key"] = str(acc_img)
        client_common.save_account_config(acc["name"], overrides)

    def run_image_tool(self):
        if not IMAGE_KEY_TOOL.is_file():
            messagebox.showerror("提示", f"找不到图片密钥工具：\n{IMAGE_KEY_TOOL}")
            return
        proc = subprocess.Popen([sys.executable, str(IMAGE_KEY_TOOL)])
        self.p3_status.config(text="密钥工具运行中，解密成功后会自动进入下一步…", fg="#666")
        self.root.after(2000, lambda: self._poll_image_tool(proc, 120))

    def _poll_image_tool(self, proc: subprocess.Popen, remaining: int):
        acc = self._selected_account()
        if acc:
            ok, _msg = image_decrypt_ok(_account_cfg(self.cfg, acc), acc["path"])
            if ok:
                self.step3_check()  # 成功即自动进入下一步
                return
        if proc.poll() is not None and remaining <= 0:
            messagebox.showwarning(
                "提示",
                "图片密钥工具已结束但仍未解密成功。\n请先在微信「朋友圈」里点开两三张图片，再点「解密图片」重试。",
            )
            return
        self.root.after(2000, lambda: self._poll_image_tool(proc, remaining - 1))

    # ---------- 第 4 步：启动服务器 ----------
    def _render_start_page(self):
        acc = self._selected_account()
        self._clear(self.p4_body)
        lines = [f"账号：{acc['label']}", "数据库解密：✓ 通过", "图片解密：✓ 通过"]
        tk.Label(
            self.p4_body,
            text="\n".join(lines),
            justify="left",
            font=("Microsoft YaHei UI", 11),
            fg="#2e7d32",
        ).pack(anchor="w", pady=8)
        if self.test_mode:
            tk.Label(
                self.p4_body,
                text="【测试模式】不会真正启动服务器。",
                fg="#b26a00",
                font=("Microsoft YaHei UI", 11),
            ).pack(anchor="w", pady=8)

    def start_server(self):
        if self.test_mode:
            messagebox.showinfo("测试模式", "向导流程验证通过，未启动服务器。")
            self.root.destroy()
            return
        acc = self._selected_account()
        if not acc:
            return
        acc_cfg = _account_cfg(self.cfg, acc)
        if not db_decrypt_ok(acc_cfg, acc["path"]):
            messagebox.showerror("门禁未通过", "数据库解密未通过，请先完成第 2 步")
            self.show_page(1)
            return
        ok, msg = ensure_image_key_usable(acc_cfg, acc)
        if not ok:
            messagebox.showerror("门禁未通过", f"图片解密未通过：{msg}\n请先完成第 3 步")
            self.show_page(2)
            return

        backend = ROOT / "backend"
        py = backend / ".venv" / "Scripts" / "python.exe"
        if not py.is_file():
            messagebox.showerror("提示", "缺少 backend/.venv，请先运行 启动立洋社区.bat 完成安装")
            return
        mig = subprocess.run(
            [str(py), "-m", "alembic", "upgrade", "head"],
            cwd=str(backend),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if mig.returncode != 0:
            messagebox.showerror("数据库迁移失败", mig.stderr[-2000:] or mig.stdout[-2000:])
            return

        # 设备令牌：缺失/占位时自动生成并写入配置，无需手动填
        token = str(self.cfg.get("device_token") or "")
        if not token or "请先运行" in token:
            token = _fetch_device_token(backend)
            if token:
                self.cfg["device_token"] = token
                save_config(self.cfg)

        subprocess.Popen(
            ["cmd", "/k", f"cd /d {ROOT}\\backend && call .venv\\Scripts\\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header"],
            cwd=str(ROOT),
        )
        subprocess.Popen(
            ["cmd", "/k", f"cd /d {ROOT}\\frontend && npm run dev -- --host 127.0.0.1 --port 5173"],
            cwd=str(ROOT),
        )
        if self.client_var.get():
            token_ok = bool(self.cfg.get("device_token")) and "请先运行" not in str(self.cfg.get("device_token"))
            if token_ok:
                subprocess.Popen([str(py), "client.py"], cwd=str(CLIENT_DIR))
            else:
                messagebox.showwarning(
                    "提示",
                    "同步客户端未启动：设备令牌自动生成失败，请手动运行 backend/scripts/init_wechat_sync.py 查看并填入 config.json",
                )
        # 图片密钥后台监控（独立进程，不随服务器重启而中断）
        if MONITOR_PY.is_file():
            subprocess.Popen([str(py), str(MONITOR_PY)])
        self.root.destroy()
        os.startfile("http://127.0.0.1:5173/")


if __name__ == "__main__":
    cfg = load_config()
    if "--check" in sys.argv or os.environ.get("LY_CHECK") == "1":
        sys.exit(run_headless(cfg))
    StartupWindow(cfg)
