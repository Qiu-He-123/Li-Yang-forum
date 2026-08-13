"""启动自检 + 引导窗口。

每次启动后端/同步客户端前运行：检查朋友圈数据库能否解密、图片密钥是否有效。
任一环节失败会弹窗引导：登录微信 → 打开朋友圈 → 点开两张图片 → 重新抓取密钥。
"""

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path

import sns_reader

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"

GUIDE_TEXT = (
    "请按以下步骤操作：\n"
    "1. 打开微信 PC 版并登录社区运营账号（保持登录，不要退出）\n"
    "2. 进入「朋友圈」页面，点开浏览 2-3 张图片（保持一张打开）\n"
    "3. 运行「获取微信朋友圈\\获取图片密钥.py」抓取图片密钥（微信重启不影响密钥）\n"
    "4. 确认 db_key.txt 存在（聊天记录导出工具生成的 32 字节 hex 密钥）\n"
    "5. 回到本窗口点击「重新检测」\n"
)


def ensure_config() -> dict:
    if CONFIG.is_file():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    example = HERE / "config.example.json"
    if example.is_file():
        shutil.copy2(example, CONFIG)
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {}


def run_checks(cfg: dict) -> list[tuple[str, bool, str]]:
    results = []

    key_file = cfg.get("key_file", "")
    key_hex = ""
    if key_file and os.path.isfile(key_file):
        try:
            key_hex = Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            key_hex = ""
        ok = len(key_hex) == 64
        results.append(("数据库密钥 db_key.txt", ok, "OK" if ok else "密钥内容不是 32 字节 hex"))
    else:
        results.append(("数据库密钥 db_key.txt", False, "文件不存在"))

    data_root, _account, sns_src = (
        sns_reader.find_sns_db(cfg.get("datadir"), key_hex) if key_hex else (None, None, None)
    )
    results.append(
        (
            "朋友圈数据库 sns.db",
            sns_src is not None,
            os.path.basename(sns_src) if sns_src else "未找到或密钥不匹配（请确认微信已登录）",
        )
    )

    image_key = sns_reader.load_image_key(cfg.get("images_key"))
    results.append(
        ("图片密钥 图片密钥.json", image_key is not None, "OK" if image_key else "文件缺失或格式错误")
    )

    if image_key and data_root:
        ok, msg = sns_reader.verify_image_key(data_root, image_key, expect_wxid=data_root)
        results.append(("图片解密验证", ok, msg))
    else:
        results.append(("图片解密验证", False, "需要先补齐图片密钥"))

    try:
        import requests  # noqa: F401
        results.append(("依赖 requests", True, "OK"))
    except ImportError:
        results.append(("依赖 requests", False, "请运行 pip install requests"))

    token_ok = bool(cfg.get("device_token")) and "请先运行" not in str(cfg.get("device_token"))
    results.append(
        (
            "设备令牌 device_token",
            token_ok,
            "OK" if token_ok else "请运行 backend/scripts/init_wechat_sync.py 查看",
        )
    )
    return results


class CheckWindow:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.root = tk.Tk()
        self.root.title("立洋社区 - 微信朋友圈同步启动自检")
        self.root.geometry("660x560")
        self.root.resizable(False, False)

        tk.Label(
            self.root,
            text="启动自检：确认朋友圈解密链路可用",
            font=("Microsoft YaHei UI", 13, "bold"),
        ).pack(pady=(14, 4))
        self.list_frame = tk.Frame(self.root)
        self.list_frame.pack(fill="both", padx=18)

        self.status_label = tk.Label(self.root, text="", font=("Microsoft YaHei UI", 11))
        self.status_label.pack(pady=6)

        self.guide = tk.Label(
            self.root,
            text=GUIDE_TEXT,
            justify="left",
            font=("Microsoft YaHei UI", 10),
            fg="#7a3b12",
        )
        self.guide.pack(pady=4, padx=18, anchor="w")

        btns = tk.Frame(self.root)
        btns.pack(pady=12)
        tk.Button(btns, text="重新检测", command=self.rerun, width=12, bg="#f0f0f0").pack(side="left", padx=6)
        tk.Button(btns, text="启动同步客户端", command=self.start_client, width=16, bg="#d9ead3").pack(side="left", padx=6)
        tk.Button(btns, text="退出", command=self.root.destroy, width=8, bg="#f4cccc").pack(side="left", padx=6)

        self.rerun()
        self.root.mainloop()

    def rerun(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        results = run_checks(self.cfg)
        all_ok = True
        for name, ok, msg in results:
            color = "#2e7d32" if ok else "#c62828"
            tk.Label(
                self.list_frame,
                text=f"{'✓' if ok else '✗'}  {name}：{msg}",
                anchor="w",
                font=("Microsoft YaHei UI", 10),
                fg=color,
            ).pack(fill="x", pady=1)
            all_ok = all_ok and ok
        self.status_label.config(
            text="全部通过，可以启动同步客户端" if all_ok else "存在未通过的项，请按下方步骤处理",
            fg="#2e7d32" if all_ok else "#c62828",
            font=("Microsoft YaHei UI", 11, "bold"),
        )

    def start_client(self):
        results = run_checks(self.cfg)
        if any(not ok for _n, ok, _m in results):
            self.status_label.config(text="仍有未通过项，请先处理后再启动", fg="#c62828")
            return
        self.root.destroy()
        subprocess.Popen([sys.executable, str(HERE / "client.py")], cwd=str(HERE))


if __name__ == "__main__":
    ensure_config()
    import client_common
    CheckWindow(client_common.load_effective_config())
