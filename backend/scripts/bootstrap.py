# -*- coding: utf-8 -*-
"""环境自检与自动修复（被 重启服务器.bat / 启动立洋社区.bat 调用）。

缺啥补啥：Python -> venv -> 后端依赖 -> 前端依赖 -> 前端构建 -> 数据库迁移。
版本低了自动升级；真缺（没装 Python/Node）就明确提示怎么装，绝不只报错不解决。

编码：脚本强制 UTF-8 输出（配合 bat 里的 chcp 65001 + PYTHONUTF8=1），
避免中文在 GBK 控制台乱码；不使用 ANSI 颜色码（cmd 下会显示成垃圾字符）。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 强制 UTF-8 输出，避免中文在 GBK 控制台/管道里乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
PY_MIN = (3, 10)


def line(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def _find_python() -> list[str] | None:
    """找可用的 Python 命令：优先 py -3 启动器（可靠、避开微软商店假 python），其次 python。"""
    for cmd in (["py", "-3"], ["python"]):
        try:
            r = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and "Python" in (r.stdout + r.stderr):
                return cmd
        except Exception:
            continue
    return None


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    try:
        return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode == 0
    except FileNotFoundError:
        return False


def main() -> int:
    line("环境自检与自动修复")
    problems = 0

    # ---------- 1) Python ----------
    py = _find_python()
    if not py:
        print("[缺失] 未检测到可用的 Python（py 启动器或 python 均不可用）！")
        print("       请到 https://www.python.org/downloads/ 下载 3.10+ 版本")
        print("       安装时勾选「Add python.exe to PATH」和「py launcher」，然后重新运行本脚本。")
        problems += 1
    else:
        ver = subprocess.run(
            [*py, "-c", "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True, text=True,
        ).stdout.strip()
        try:
            v = tuple(int(x) for x in ver.split("."))
            if v < PY_MIN:
                print(f"[版本过低] Python {ver}，需要 {PY_MIN[0]}.{PY_MIN[1]}+")
                print("       请到 https://www.python.org/downloads/ 升级，旧版不用卸载（本脚本会用新版）。")
                problems += 1
            else:
                print(f"[OK] Python {ver}")
        except ValueError:
            print(f"[异常] 无法解析 Python 版本：{ver!r}")
            problems += 1

    # ---------- 2) venv ----------
    line("虚拟环境 backend/.venv")
    if not VENV_PY.is_file():
        print("[修复] 正在创建虚拟环境…")
        if py and run([*py, "-m", "venv", str(BACKEND / ".venv")]):
            print("[完成] 虚拟环境已创建")
        else:
            print("[失败] 创建虚拟环境失败，请确认 Python 安装完整（含 venv 组件）")
            problems += 1
    else:
        print("[OK] 虚拟环境已存在")

    # ---------- 3) 后端依赖（缺啥装啥，版本低了自动升级） ----------
    if VENV_PY.is_file():
        line("后端依赖（pip 自动安装/升级）")
        req_files = [BACKEND / "requirements.txt", ROOT / "工具" / "微信密钥工具" / "requirements.txt"]
        for req in req_files:
            if not req.is_file():
                continue
            print(f"[修复] 安装/升级依赖：{req.relative_to(ROOT)} …")
            if not run([str(VENV_PY), "-m", "pip", "install", "-r", str(req), "--disable-pip-version-check"]):
                print("      默认源失败，改用清华镜像重试…")
                run([str(VENV_PY), "-m", "pip", "install", "-r", str(req), "-i", PIP_MIRROR, "--disable-pip-version-check"])
        print("[OK] 后端依赖就绪")

    # ---------- 4) .env ----------
    if not (BACKEND / ".env").is_file():
        print("[修复] 复制 backend/.env.example -> backend/.env")
        try:
            shutil.copy2(BACKEND / ".env.example", BACKEND / ".env")
        except OSError:
            problems += 1
    print("[OK] 环境配置文件就绪")

    # ---------- 5) Node / npm ----------
    line("前端环境（node/npm）")
    npm = shutil.which("npm")
    if not npm:
        print("[缺失] 未安装 Node.js/npm！")
        print("       请到 https://nodejs.org/ 下载 LTS 版并安装（默认勾选即可），然后重新运行。")
        problems += 1
    else:
        print("[OK] npm 可用")
        if not (FRONTEND / "node_modules").is_dir():
            print("[修复] 正在安装前端依赖（npm install）…")
            if not run(["cmd", "/c", f"cd /d {FRONTEND} && npm install --registry=https://registry.npmjs.org"]):
                print("      默认源失败，改用国内镜像 npmmirror 重试…")
                run(["cmd", "/c", f"cd /d {FRONTEND} && npm install --registry=https://registry.npmmirror.com"])
            if not (FRONTEND / "node_modules").is_dir():
                print("[失败] 前端依赖安装失败，请检查网络后重试")
                problems += 1
        else:
            print("[OK] 前端依赖已存在")

        # ---------- 6) 前端构建（缺失/源码更新自动构建） ----------
        line("前端构建（生产模式产物）")
        dist_html = FRONTEND / "dist" / "index.html"
        newest = max((p.stat().st_mtime for p in (FRONTEND / "src").rglob("*") if p.is_file()), default=0)
        stale = bool(dist_html.is_file() and newest and dist_html.stat().st_mtime < newest)
        if not dist_html.is_file() or stale:
            print("[修复] 正在构建前端（npm run build，首次约需几分钟）…")
            if not run(["cmd", "/c", f"cd /d {FRONTEND} && npm run build"]):
                print("[失败] 前端构建失败，请查看上方报错（常见：TypeScript 类型错误）")
                problems += 1
        if dist_html.is_file():
            print("[OK] 前端构建产物就绪")

    # ---------- 7) 数据库迁移 ----------
    line("数据库迁移（alembic upgrade head）")
    if VENV_PY.is_file():
        if run([str(VENV_PY), "-m", "alembic", "upgrade", "head"], cwd=BACKEND):
            print("[OK] 数据库迁移完成")
        else:
            print("[失败] 数据库迁移失败，请检查 backend/.env 的 DATABASE_URL")
            problems += 1

    # ---------- 汇总 ----------
    print("\n" + "=" * 60)
    if problems == 0:
        print("  自检全部通过 ✓  可以启动服务器了")
        return 0
    print(f"  有 {problems} 项未解决，请按上方提示处理后重新运行")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
