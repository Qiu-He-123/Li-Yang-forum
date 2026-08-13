# -*- coding: utf-8 -*-
"""环境自检与自动修复（被 重启服务器.bat / 启动立洋社区.bat 调用）。

缺啥补啥：Python -> venv -> 后端依赖 -> 前端依赖 -> 前端构建 -> 数据库迁移。
版本低了自动升级；真缺（没装 Python/Node）就明确提示怎么装，绝不只报错不解决。

编码：脚本强制 UTF-8 输出（配合 bat 里的 chcp 65001 + PYTHONUTF8=1），
避免中文在 GBK 控制台乱码；不使用 ANSI 颜色码（cmd 下会显示成垃圾字符）。
"""
import hashlib
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


def _reqs_fresh(marker: Path, req_files: list[Path]) -> bool:
    """依赖清单自上次成功安装后没变过 → 跳过 pip/npm 检查，大幅加速重启自检。
    （git pull 更新了 requirements/package.json 后，清单 mtime 变新 → 自动重装）"""
    if not marker.is_file():
        return False
    marker_t = marker.stat().st_mtime
    return all(r.is_file() and r.stat().st_mtime <= marker_t for r in req_files)


def _src_tree_hash(src_dir: Path) -> str:
    """对前端源码树做内容哈希：内容没变就不重建（git pull 只改 mtime 也能跳过）。"""
    h = hashlib.md5()
    for p in sorted(src_dir.rglob("*")):
        if not p.is_file():
            continue
        try:
            h.update(p.relative_to(src_dir).as_posix().encode("utf-8"))
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            continue
    return h.hexdigest()


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

    # ---------- 3) 后端依赖（缺啥装啥，版本低了自动升级；没变化就跳过） ----------
    if VENV_PY.is_file():
        line("后端依赖（pip 自动安装/升级）")
        req_files = [BACKEND / "requirements.txt", ROOT / "工具" / "微信密钥工具" / "requirements.txt"]
        deps_marker = BACKEND / ".venv" / ".deps_ok"
        if _reqs_fresh(deps_marker, req_files):
            print("[OK] 后端依赖已就绪（requirements 无变化，跳过安装检查）")
        else:
            ok_all = True
            for req in req_files:
                if not req.is_file():
                    continue
                print(f"[修复] 安装/升级依赖：{req.relative_to(ROOT)} …")
                ok1 = run([str(VENV_PY), "-m", "pip", "install", "-r", str(req), "--disable-pip-version-check"])
                if not ok1:
                    print("      默认源失败，改用清华镜像重试…")
                    ok1 = run([str(VENV_PY), "-m", "pip", "install", "-r", str(req), "-i", PIP_MIRROR, "--disable-pip-version-check"])
                if not ok1:
                    ok_all = False
                    print(f"[失败] 依赖安装失败：{req.relative_to(ROOT)}（网络或镜像问题，可重试）")
            if ok_all:
                try:
                    deps_marker.write_text("ok\n", encoding="utf-8")
                except OSError:
                    pass
                print("[OK] 后端依赖就绪")
            else:
                problems += 1

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
        npm_marker = FRONTEND / "node_modules" / ".npm_ok"
        npm_manifests = [FRONTEND / "package.json", FRONTEND / "package-lock.json"]
        npm_installed = False
        if (FRONTEND / "node_modules").is_dir() and _reqs_fresh(npm_marker, npm_manifests):
            print("[OK] 前端依赖已就绪（package.json 无变化，跳过安装检查）")
        else:
            print("[修复] 正在安装/更新前端依赖（npm install）…")
            ok_npm = run(["cmd", "/c", f"cd /d {FRONTEND} && npm install --registry=https://registry.npmjs.org"])
            if not ok_npm:
                print("      默认源失败，改用国内镜像 npmmirror 重试…")
                ok_npm = run(["cmd", "/c", f"cd /d {FRONTEND} && npm install --registry=https://registry.npmmirror.com"])
            if ok_npm and (FRONTEND / "node_modules").is_dir():
                try:
                    npm_marker.parent.mkdir(parents=True, exist_ok=True)
                    npm_marker.write_text("ok\n", encoding="utf-8")
                except OSError:
                    pass
                npm_installed = True
            else:
                print("[失败] 前端依赖安装失败，请检查网络后重试")
                problems += 1

        # ---------- 6) 前端构建（缺失/源码内容变化/依赖更新才构建） ----------
        line("前端构建（生产模式产物）")
        dist_html = FRONTEND / "dist" / "index.html"
        hash_file = FRONTEND / "dist" / ".src_hash"
        src_hash = _src_tree_hash(FRONTEND / "src")
        prev_hash = hash_file.read_text(encoding="utf-8").strip() if hash_file.is_file() else ""
        need_build = (not dist_html.is_file()) or npm_installed or (prev_hash != src_hash)
        if need_build:
            # build:fast = vite build（跳过 vue-tsc 类型检查，构建快数倍；全量检查可手动 npm run build）
            print("[修复] 正在构建前端（vite build 快速模式）…")
            if not run(["cmd", "/c", f"cd /d {FRONTEND} && npm run build:fast"]):
                print("[失败] 前端构建失败，请查看上方报错")
                problems += 1
            else:
                try:
                    hash_file.parent.mkdir(parents=True, exist_ok=True)
                    hash_file.write_text(src_hash, encoding="utf-8")
                except OSError:
                    pass
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
