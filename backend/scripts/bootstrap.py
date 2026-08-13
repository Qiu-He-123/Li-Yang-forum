# -*- coding: utf-8 -*-
"""环境自检与自动修复（被 重启服务器.bat / 启动立洋社区.bat 调用）。

缺啥补啥：Python -> venv -> 后端依赖 -> 前端依赖 -> 前端构建 -> 数据库迁移。
版本低了自动升级；真缺（没装 Python/Node）就明确提示怎么装，绝不只报错不解决。

编码：脚本强制 UTF-8 输出（配合 bat 里的 chcp 65001 + PYTHONUTF8=1），
避免中文在 GBK 控制台乱码；不使用 ANSI 颜色码（cmd 下会显示成垃圾字符）。
"""
import os
import re
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
# 自动补装 tcl/tk 用的安装器下载源（python.org 官方 + 华为云国内镜像）
PY_INSTALL_URLS = (
    "https://www.python.org/ftp/python/{ver}/python-{ver}-amd64.exe",
    "https://mirrors.huaweicloud.com/python/{ver}/python-{ver}-amd64.exe",
)


def line(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def _python_candidates() -> list[list[str]]:
    """候选 Python 命令：先枚举 py 启动器里的具体版本（-V:3.13 等），
    再补 py -3 / python / python3。"""
    cmds: list[list[str]] = []
    try:
        r = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                m = re.match(r"\s*-V:(\d+\.\d+)", line)
                if m:
                    cmds.append(["py", "-%s" % m.group(1)])
    except Exception:
        pass
    cmds.append(["py", "-3"])
    cmds.append(["python"])
    cmds.append(["python3"])
    return cmds


def _probe_python(cmd: list[str], need_tk: bool) -> bool:
    code = "import tkinter" if need_tk else "pass"
    try:
        r = subprocess.run([*cmd, "-c", code], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _find_python() -> list[str] | None:
    """找可用的 Python：优先带 tkinter 的（图形向导需要），
    其次任意可用 Python（无界面启动兜底，服务器本身不需要 GUI）。"""
    seen: set[str] = set()
    for cmd in _python_candidates():
        key = " ".join(cmd)
        if key in seen:
            continue
        seen.add(key)
        if _probe_python(cmd, need_tk=True):
            return cmd
    for cmd in _python_candidates():
        key = " ".join(cmd)
        if key in seen:
            continue
        seen.add(key)
        if _probe_python(cmd, need_tk=False):
            return cmd
    return None


def _best_python_version() -> str:
    """取现有可运行 Python 的版本号（如 3.13.12），用于下载同版本安装器补装 tcl/tk。"""
    for cmd in (["py", "-3"], ["python"]):
        try:
            r = subprocess.run(
                [*cmd, "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            continue
    return ""


def _install_python_with_tk(ver: str) -> bool:
    """下载 python.org 同版本安装器，静默补装 tcl/tk 组件（用户级，无需管理员）。
    已有同版本安装时相当于修复/补装组件；返回安装命令是否成功。"""
    import tempfile
    import urllib.request

    tmp = Path(tempfile.gettempdir()) / f"python-{ver}-amd64.exe"
    for url_tpl in PY_INSTALL_URLS:
        url = url_tpl.format(ver=ver)
        print(f"      下载 {url} …")
        try:
            urllib.request.urlretrieve(url, tmp)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"      下载失败：{exc}，换下一个源")
            continue
    else:
        print("      所有下载源都失败（可能无网络）")
        return False
    print("      静默安装（补装 tcl/tk，用户级，无需管理员）…")
    try:
        r = subprocess.run(
            [str(tmp), "/quiet", "InstallAllUsers=0", "PrependPath=0",
             "Include_test=0", "Include_tcltk=1", "Include_launcher=1",
             "Include_pip=1", "Shortcuts=0", "AssociateFiles=0"],
            capture_output=True, text=True, timeout=600,
        )
        return r.returncode == 0
    except Exception as exc:  # noqa: BLE001
        print(f"      安装失败：{exc}")
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


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
                if _probe_python(py, need_tk=True):
                    print("      （含 tkinter，图形向导可用）")
                else:
                    print("      [修复] 当前 Python 缺少 tkinter（图形向导需要），尝试自动补装…")
                    pv = _best_python_version()
                    if pv and _install_python_with_tk(pv):
                        py2 = _find_python()
                        if py2 and _probe_python(py2, need_tk=True):
                            py = py2
                            print(f"      [OK] Python {pv} 的 tcl/tk 已补装（图形向导可用）")
                        else:
                            print("      [警告] 补装后仍未检测到 tkinter，将用无界面方式启动服务器")
                    else:
                        print("      [警告] 自动补装 tcl/tk 失败（可能无网络/非官方安装），将用无界面方式启动服务器")
                        print("      服务器本身不需要 GUI；密钥配置可命令行完成：")
                        print("        数据库密钥: backend\\.venv\\Scripts\\python.exe 工具\\微信密钥工具\\capture_key_hwbp.py")
                        print("        图片密钥  : backend\\.venv\\Scripts\\python.exe 获取微信朋友圈\\获取图片密钥.py --datadir <微信数据根目录> --account-dir <账号名>")
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
    elif not _probe_python([str(VENV_PY)], need_tk=True) and py and _probe_python(py, need_tk=True):
        # 现有 venv 用的 Python 没装 tcl/tk，而系统里有带 tkinter 的 Python → 自动重建
        print("[修复] 虚拟环境的 Python 缺少 tkinter，改用带 tkinter 的 Python 重建虚拟环境…")
        shutil.rmtree(BACKEND / ".venv", ignore_errors=True)
        if run([*py, "-m", "venv", str(BACKEND / ".venv")]):
            print("[完成] 虚拟环境已重建")
        else:
            print("[失败] 重建虚拟环境失败")
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
