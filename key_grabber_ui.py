#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""微信数据库密钥获取工具（图形界面版）。

流程指引：检测微信目录 -> 点击"自动获取密钥" -> 程序自动重启微信并挂断点 ->
提示"请登录微信" -> 捕获密钥 -> 校验数据库 -> 显示结果。
底层使用自研 INT3 代码断点方案（capture_key_hwbp.run_capture），
不扫描内存、不加载任何第三方 DLL。
"""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

try:
    import capture_key_hwbp as core
except ImportError:
    core = None


APP_TITLE = "微信聊天记录提取工具"


class KeyGrabberUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("720x560")
        self.root.minsize(640, 480)

        self.q = queue.Queue()
        self.busy = False
        self.manual_dir = None

        self._build_ui()
        self._detect_env()
        self.root.after(100, self._poll)

    # ---------- 界面 ----------
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        head = ttk.Frame(self.root)
        head.pack(fill="x", **pad)
        ttk.Label(head, text=APP_TITLE, font=("Microsoft YaHei UI", 15, "bold")) \
            .pack(anchor="w")
        ttk.Label(head, text="自动获取微信数据库密钥（INT3 代码断点方案，不扫描内存）",
                  foreground="#666666").pack(anchor="w")

        info = ttk.LabelFrame(self.root, text="环境信息")
        info.pack(fill="x", **pad)
        self.var_ver = tk.StringVar(value="检测中...")
        self.var_exe = tk.StringVar(value="")
        self.var_data = tk.StringVar(value="")
        ttk.Label(info, text="微信版本: ").grid(row=0, column=0, sticky="e", padx=8, pady=2)
        ttk.Label(info, textvariable=self.var_ver).grid(row=0, column=1, sticky="w")
        ttk.Label(info, text="安装目录: ").grid(row=1, column=0, sticky="e", padx=8, pady=2)
        ttk.Label(info, textvariable=self.var_exe).grid(row=1, column=1, sticky="w")
        ttk.Label(info, text="数据目录: ").grid(row=2, column=0, sticky="e", padx=8, pady=2)
        ttk.Label(info, textvariable=self.var_data).grid(row=2, column=1, sticky="w")
        info.columnconfigure(1, weight=1)

        status = ttk.LabelFrame(self.root, text="当前状态")
        status.pack(fill="x", **pad)
        self.var_status = tk.StringVar(value="就绪。点击下方按钮开始。")
        self.lbl_status = tk.Label(
            status, textvariable=self.var_status, font=("Microsoft YaHei UI", 12),
            wraplength=660, justify="left", anchor="w", fg="#333333")
        self.lbl_status.pack(fill="x", padx=8, pady=10)

        keybox = ttk.LabelFrame(self.root, text="数据库密钥")
        keybox.pack(fill="x", **pad)
        self.var_key = tk.StringVar(value="")
        self.ent_key = ttk.Entry(keybox, textvariable=self.var_key,
                                 state="readonly", font=("Consolas", 11))
        self.ent_key.pack(fill="x", padx=8, pady=6)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        self.btn_dir = ttk.Button(btns, text="选择微信目录…", command=self._choose_dir)
        self.btn_dir.pack(side="left")
        self.btn_grab = ttk.Button(btns, text="自动获取密钥", command=self._start)
        self.btn_grab.pack(side="left", padx=8)
        self.btn_copy = ttk.Button(btns, text="复制密钥", command=self._copy_key,
                                   state="disabled")
        self.btn_copy.pack(side="left", padx=8)
        ttk.Button(btns, text="退出", command=self.root.destroy).pack(side="right")

        logbox = ttk.LabelFrame(self.root, text="操作日志")
        logbox.pack(fill="both", expand=True, **pad)
        self.txt_log = scrolledtext.ScrolledText(logbox, height=9,
                                                 state="disabled",
                                                 font=("Consolas", 9))
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=6)

    def _log(self, text, color=None):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text + "\n")
        if color:
            self.txt_log.tag_add("c", "end-2l", "end-1c")
            self.txt_log.tag_configure("c", foreground=color)
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _set_status(self, text, color="#333333"):
        self.var_status.set(text)
        self.lbl_status.configure(fg=color)

    # ---------- 环境检测 ----------
    def _detect_env(self):
        def work():
            ver, exe = core.find_weixin_exe() if core else (None, None)
            data_root = None
            if core:
                for r in core.DATA_ROOTS:
                    if os.path.isdir(r):
                        data_root = r
                        break
            self.q.put(("env", (ver, exe, data_root)))
        threading.Thread(target=work, daemon=True).start()

    def _apply_env(self, ver, exe, data_root):
        if ver and exe:
            self.var_ver.set(ver)
            self.var_exe.set(os.path.dirname(exe))
        else:
            self.var_ver.set("未找到微信（请检查安装）")
            self.var_exe.set("")
        self.var_data.set(data_root or "未找到（请检查文档目录）")
        if not ver:
            self._set_status("未检测到微信，请点“选择微信目录…”手动指定。", "#c00000")

    def _choose_dir(self):
        d = filedialog.askdirectory(title="选择微信安装目录")
        if not d:
            return
        ver, exe = core.find_weixin_exe(manual_dir=d)
        if not exe:
            messagebox.showerror(
                "无效目录",
                "所选目录中没有找到微信。\n"
                "需要包含 Weixin.exe，以及带 Weixin.dll 的版本子目录（如 4.1.12.53）。")
            return
        self.manual_dir = d
        self.var_ver.set(ver)
        self.var_exe.set(os.path.dirname(exe))
        self._log("已手动指定微信目录: %s（版本 %s）" % (d, ver))
        self._set_status("微信目录已指定，点击“自动获取密钥”开始。", "#1f4e79")

    # ---------- 抓取流程 ----------
    def _start(self):
        if self.busy:
            return
        if core is None:
            self._set_status("缺少核心模块 capture_key_hwbp.py", "#c00000")
            return
        self.busy = True
        self.btn_grab.configure(state="disabled")
        self.btn_copy.configure(state="disabled")
        self.var_key.set("")
        self._log("======== 开始获取密钥 ========")
        self._set_status("正在检测微信安装目录...", "#1f4e79")

        def progress(msg):
            self.q.put(("progress", msg))

        def work():
            code, key, account = core.run_capture(progress=progress, timeout=300,
                                                  weixin_dir=self.manual_dir)
            self.q.put(("done", (code, key, account)))

        threading.Thread(target=work, daemon=True).start()

    def _handle_progress(self, msg):
        self._log(msg)
        if "正在关闭微信" in msg:
            self._set_status("正在关闭微信...", "#1f4e79")
        elif "正在重新启动微信" in msg:
            self._set_status("正在重新启动微信...", "#1f4e79")
        elif "正在附加" in msg:
            self._set_status("正在附加进程并挂断点...", "#1f4e79")
        elif "断点已挂好" in msg:
            self._set_status("断点已就绪。请登录微信（自动恢复登录或扫码均可）...",
                             "#b45f06")
        elif "捕获到密钥" in msg:
            self._set_status("已捕获到密钥，正在校验数据库...", "#1f4e79")
        elif "校验" in msg and "通过" in msg:
            self._set_status("密钥校验通过！", "#006100")

    def _handle_done(self, code, key, account):
        self.busy = False
        self.btn_grab.configure(state="normal")
        if code == 0 and key:
            self.var_key.set(key)
            self.btn_copy.configure(state="normal")
            self._set_status("获取成功！密钥已写入 db_key.txt（账号目录: %s）"
                             % (account or "未知"), "#006100")
            self._log("完成：密钥已保存到 db_key.txt", "#006100")
        elif code == 2:
            self._set_status("超时未捕获到密钥。请再点一次，这次登录微信。",
                             "#c00000")
        elif code == 3:
            self._set_status("密钥捕获成功但数据库校验失败（可能版本不匹配），"
                             "详见操作日志。",
                             "#c00000")
        else:
            self._set_status("无法开始（未找到微信或版本过低），详见操作日志。",
                             "#c00000")

    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "env":
                    self._apply_env(*payload)
                elif kind == "progress":
                    self._handle_progress(payload)
                elif kind == "done":
                    self._handle_done(*payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _copy_key(self):
        key = self.var_key.get()
        if key:
            self.root.clipboard_clear()
            self.root.clipboard_append(key)
            self._log("密钥已复制到剪贴板")


def main():
    if "--check" in sys.argv:
        # 打包后自检：把环境信息写入当前目录 exe_selftest.txt
        lines = []
        lines.append("entry: ok")
        if core is None:
            lines.append("core: MISSING")
        else:
            lines.append("core: ok")
        try:
            import frida
            lines.append("frida: %s" % frida.__version__)
        except Exception as e:
            lines.append("frida ERR: %s" % e)
        try:
            from Crypto.Cipher import AES  # noqa
            lines.append("crypto: ok")
        except Exception as e:
            lines.append("crypto ERR: %s" % e)
        if core is not None:
            ver, exe = core.find_weixin_exe()
            lines.append("wechat: %s | %s" % (ver or "not found", exe or ""))
            ok, why = core.version_ok(ver) if ver else (False, "no wechat")
            lines.append("version_ok: %s | %s" % (ok, why))
            rva = core.RVA_TABLE.get(ver, 0)
            lines.append("rva: 0x%X" % rva)
        try:
            out = os.path.join(os.getcwd(), "exe_selftest.txt")
            with open(out, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            lines.append("write ERR: %s" % e)
        return 0
    if core is None:
        print("缺少 capture_key_hwbp.py，请将本文件放在同一目录")
        return 1
    root = tk.Tk()
    KeyGrabberUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
