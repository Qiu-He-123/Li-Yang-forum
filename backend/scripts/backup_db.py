#!/usr/bin/env python3
"""备份数据库并上传到 GitHub Releases（私有备份仓库 Qiu-He-123/liyang-backups）。

用法（在 backend 目录下）:
    .venv\\Scripts\\python scripts\\backup_db.py          # 备份 + 上传 GitHub
    .venv\\Scripts\\python scripts\\backup_db.py --no-upload   # 只生成本地备份

配置来自 backend/.env（或环境变量）:
    DATABASE_URL           数据库连接，sqlite:///... 或 mysql+pymysql://...
    BACKUP_DIR             本地备份目录，默认 backend/backups
    BACKUP_KEEP            保留最近多少个备份（GitHub 和本地），默认 30
    BACKUP_GITHUB_REPO     GitHub 备份仓库，默认 Qiu-He-123/liyang-backups
    GITHUB_TOKEN           GitHub 访问令牌（需有该仓库 Contents 读写权限）
    BACKUP_PASSPHRASE      可选：设置后用 openssl AES-256 加密备份文件
    BACKUP_MYSQL_CMD       可选：自定义 mysqldump 命令模板，
                           {db} 会被替换为库名，{password} 被替换为 BACKUP_MYSQL_PASSWORD
    BACKUP_MYSQL_PASSWORD  可选：配合上面模板里的 {password} 使用

说明：
  - SQLite 用官方 backup API 生成一致性快照（不会因为正在写入而损坏）。
  - 上传走 GitHub Releases API，不污染备份仓库的 git 历史，旧备份自动清理。
"""

import base64
import datetime
import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import httpx

API = "https://api.github.com"
REPO_DEFAULT = "Qiu-He-123/liyang-backups"
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def load_env():
    """读取 backend/.env 到环境变量（已有环境变量优先，不覆盖）。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cfg(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def resolve_sqlite_path(db_url: str) -> Path:
    """把 sqlite:///... 转成文件路径；相对路径以 backend/ 为基准。"""
    path = urllib.parse.urlparse(db_url).path
    if path.startswith("/"):
        path = path[1:]  # sqlite:///./x.db 和 sqlite:///D:/x.db 都会多一个前导 /
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def dump_sqlite(db_path: Path, out_path: Path):
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(out_path))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def dump_mysql(db_url: str, out_path: Path):
    u = urllib.parse.urlparse(db_url)
    db = u.path.lstrip("/")
    override = cfg("BACKUP_MYSQL_CMD")
    if override:
        cmd = (
            override.replace("{db}", db)
            .replace("{password}", cfg("BACKUP_MYSQL_PASSWORD"))
        )
        with out_path.open("wb") as f:
            subprocess.run(cmd, shell=True, stdout=f, check=True)
        return
    env = os.environ.copy()
    if u.password:
        env["MYSQL_PWD"] = u.password
    cmd = [
        "mysqldump",
        f"--host={u.hostname or '127.0.0.1'}",
        f"--port={u.port or 3306}",
        f"--user={u.username or 'root'}",
        "--single-transaction",
        "--routines",
        "--triggers",
        db,
    ]
    with out_path.open("wb") as f:
        subprocess.run(cmd, env=env, stdout=f, check=True)


def compress(src: Path) -> Path:
    gz = src.with_name(src.name + ".gz")
    with src.open("rb") as fin, gzip.open(gz, "wb") as fout:
        shutil.copyfileobj(fin, fout, 1024 * 1024)
    src.unlink()
    return gz


def encrypt(path: Path, passphrase: str) -> Path:
    """openssl AES-256 加密；两个环境都需要有 openssl（Linux 自带）。"""
    enc = path.with_name(path.name + ".enc")
    subprocess.run(
        [
            "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
            "-salt", "-pass", f"pass:{passphrase}",
            "-in", str(path), "-out", str(enc),
        ],
        check=True,
    )
    path.unlink()
    return enc


def gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ly-community-backup",
    }


def ensure_repo_ready(repo: str, token: str):
    """确认仓库存在且至少有一个 commit（GitHub 不允许在空仓库建 Release）。"""
    r = httpx.get(f"{API}/repos/{repo}", headers=gh_headers(token), timeout=30)
    r.raise_for_status()
    commits = httpx.get(f"{API}/repos/{repo}/commits", headers=gh_headers(token), timeout=30)
    if commits.status_code in (404, 409) or not commits.json():
        body = base64.b64encode(
            "# 数据库备份仓库（自动生成）\n\n请勿把本仓库设为公开。\n".encode("utf-8")
        ).decode("ascii")
        init = httpx.put(
            f"{API}/repos/{repo}/contents/README.md",
            headers=gh_headers(token),
            json={"message": "init backup repo", "content": body},
            timeout=30,
        )
        init.raise_for_status()


def upload(file_path: Path, repo: str, token: str, tag: str, keep: int):
    headers = gh_headers(token)
    r = httpx.post(
        f"{API}/repos/{repo}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": tag,
            "body": f"数据库备份 {tag}",
            "draft": False,
            "prerelease": False,
        },
        timeout=60,
    )
    r.raise_for_status()
    upload_url = r.json()["upload_url"].split("{")[0]
    with file_path.open("rb") as f:
        data = f.read()
    up = httpx.post(
        upload_url,
        headers={**headers, "Content-Type": "application/octet-stream"},
        params={"name": file_path.name},
        content=data,
        timeout=600,
    )
    up.raise_for_status()
    print(f"已上传: {file_path.name} -> https://github.com/{repo}/releases/tag/{tag}")

    # 清理旧备份，只保留最近 keep 个
    lst = httpx.get(
        f"{API}/repos/{repo}/releases",
        headers=headers,
        params={"per_page": 100},
        timeout=30,
    ).json()
    # ponytail: 只取前 100 个 release，够用；备份仓库积累到几百个再考虑分页
    for old in sorted(lst, key=lambda x: x["created_at"], reverse=True)[keep:]:
        rid = old["id"]
        httpx.delete(f"{API}/repos/{repo}/releases/{rid}", headers=headers, timeout=30)
        httpx.delete(
            f"{API}/repos/{repo}/git/refs/tags/{old['tag_name']}",
            headers=headers,
            timeout=30,
        )
        print(f"已清理旧备份: {old['tag_name']}")


def prune_local(backup_dir: Path, keep: int):
    files = sorted(backup_dir.glob("ly_community_*"), key=lambda p: p.name, reverse=True)
    for old in files[keep:]:
        old.unlink()
        print(f"已清理本地旧备份: {old.name}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_env()
    upload_enabled = "--no-upload" not in sys.argv
    keep = int(cfg("BACKUP_KEEP", "30") or 30)
    backup_dir = Path(cfg("BACKUP_DIR", str(BASE_DIR / "backups")))
    if not backup_dir.is_absolute():
        backup_dir = BASE_DIR / backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_url = cfg("DATABASE_URL")
    if not db_url:
        sys.exit("错误: 缺少 DATABASE_URL 配置（backend/.env）")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = Path(tempfile.mkdtemp(prefix="ly_backup_"))
    try:
        if db_url.startswith("sqlite"):
            db_path = resolve_sqlite_path(db_url)
            if not db_path.exists():
                sys.exit(f"错误: SQLite 数据库不存在: {db_path}")
            raw = tmp / f"ly_community_{ts}.sqlite3"
            dump_sqlite(db_path, raw)
            print(f"SQLite 快照完成: {db_path}")
        elif db_url.startswith("mysql"):
            raw = tmp / f"ly_community_{ts}.sql"
            dump_mysql(db_url, raw)
            print("mysqldump 完成")
        else:
            sys.exit(f"错误: 不支持的数据库类型: {db_url}")

        final = compress(raw)
        passphrase = cfg("BACKUP_PASSPHRASE")
        if passphrase:
            final = encrypt(final, passphrase)
            print("已用 AES-256 加密")

        dest = backup_dir / final.name
        shutil.move(str(final), str(dest))
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"本地备份完成: {dest}（{size_mb:.2f} MB）")
        prune_local(backup_dir, keep)

        if not upload_enabled:
            print("已跳过 GitHub 上传（--no-upload）")
            return
        token = cfg("GITHUB_TOKEN")
        if not token:
            sys.exit("错误: 未配置 GITHUB_TOKEN，无法上传 GitHub（本地备份已保留）")
        repo = cfg("BACKUP_GITHUB_REPO", REPO_DEFAULT)
        ensure_repo_ready(repo, token)
        upload(dest, repo, token, f"backup-{ts}", keep)
        print("备份完成 ✔")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
