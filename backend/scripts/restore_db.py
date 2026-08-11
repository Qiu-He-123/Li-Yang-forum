#!/usr/bin/env python3
"""从 GitHub 备份仓库（或本地文件）恢复数据库。

用法（在 backend 目录下）:
    .venv\\Scripts\\python scripts\\restore_db.py --latest     # 恢复最近一次 GitHub 备份
    .venv\\Scripts\\python scripts\\restore_db.py --tag backup-20260811_030000
    .venv\\Scripts\\python scripts\\restore_db.py --file 备份文件路径

配置与 backup_db.py 相同（DATABASE_URL / GITHUB_TOKEN / BACKUP_PASSPHRASE /
BACKUP_MYSQL_RESTORE_CMD）。

警告: 恢复会覆盖当前数据库。执行前请先停掉后端服务；脚本会自动保留一份
当前数据库到同目录（.pre-restore-时间戳）。
"""

import argparse
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

from backup_db import API, BASE_DIR, cfg, gh_headers, load_env, resolve_sqlite_path


def download_asset(repo: str, token: str, tag: str | None, dest_dir: Path) -> Path:
    headers = gh_headers(token)
    url = f"{API}/repos/{repo}/releases/tags/{tag}" if tag else f"{API}/repos/{repo}/releases/latest"
    r = httpx.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    rel = r.json()
    assets = rel.get("assets") or []
    if not assets:
        sys.exit(f"错误: 备份 {rel['tag_name']} 没有可下载的文件")
    asset = assets[0]
    out = dest_dir / asset["name"]
    with httpx.stream(
        "GET",
        asset["url"],
        headers={**headers, "Accept": "application/octet-stream"},
        timeout=600,
    ) as resp:
        resp.raise_for_status()
        with out.open("wb") as f:
            for chunk in resp.iter_bytes(1024 * 1024):
                f.write(chunk)
    print(f"已下载: {out.name}（来自 {rel['tag_name']}）")
    return out


def prepare(file_path: Path) -> Path:
    """解密(.enc) + 解压(.gz)，返回可用的 .sqlite3 或 .sql 文件。"""
    p = file_path
    if p.name.endswith(".enc"):
        passphrase = cfg("BACKUP_PASSPHRASE")
        if not passphrase:
            sys.exit("错误: 备份已加密，请先在 backend/.env 设置 BACKUP_PASSPHRASE")
        plain = p.with_name(p.name[:-4])
        subprocess.run(
            [
                "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                "-pass", f"pass:{passphrase}", "-in", str(p), "-out", str(plain),
            ],
            check=True,
        )
        p = plain
    if p.name.endswith(".gz"):
        out = p.with_name(p.name[:-3])
        with gzip.open(p, "rb") as fin, out.open("wb") as fout:
            shutil.copyfileobj(fin, fout, 1024 * 1024)
        p = out
    return p


def restore_sqlite(file_path: Path):
    db_url = cfg("DATABASE_URL")
    if not db_url or not db_url.startswith("sqlite"):
        sys.exit("错误: 当前 DATABASE_URL 不是 SQLite，请确认配置")
    target = resolve_sqlite_path(db_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        bak = target.with_name(
            target.name + f".pre-restore-{datetime.datetime.now():%Y%m%d_%H%M%S}"
        )
        shutil.copy2(target, bak)
        print(f"原数据库已保留为: {bak}")
    shutil.copy2(file_path, target)
    con = sqlite3.connect(str(target))
    try:
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    if check != "ok":
        sys.exit(f"错误: 恢复后数据库完整性校验失败（{check}）")
    print(f"已恢复 SQLite 数据库: {target}（完整性校验通过）")


def restore_mysql(file_path: Path):
    u = urllib.parse.urlparse(cfg("DATABASE_URL"))
    db = u.path.lstrip("/")
    override = cfg("BACKUP_MYSQL_RESTORE_CMD")
    if override:
        cmd = (
            override.replace("{db}", db)
            .replace("{password}", cfg("BACKUP_MYSQL_PASSWORD"))
            .replace("{file}", f'"{file_path}"')
        )
        subprocess.run(cmd, shell=True, check=True)
    else:
        env = os.environ.copy()
        if u.password:
            env["MYSQL_PWD"] = u.password
        with file_path.open("rb") as fin:
            subprocess.run(
                [
                    "mysql",
                    f"--host={u.hostname or '127.0.0.1'}",
                    f"--port={u.port or 3306}",
                    f"--user={u.username or 'root'}",
                    db,
                ],
                env=env,
                stdin=fin,
                check=True,
            )
    print(f"已恢复 MySQL 数据库: {db}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_env()
    ap = argparse.ArgumentParser(description="恢复数据库备份")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="恢复 GitHub 上最近一次备份")
    group.add_argument("--tag", help="恢复指定 tag 的备份，如 backup-20260811_030000")
    group.add_argument("--file", help="使用本地备份文件")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="ly_restore_"))
    try:
        if args.file:
            src = Path(args.file)
            if not src.exists():
                sys.exit(f"错误: 文件不存在: {src}")
        else:
            token = cfg("GITHUB_TOKEN")
            if not token:
                sys.exit("错误: 需要 GITHUB_TOKEN 才能从 GitHub 下载备份")
            repo = cfg("BACKUP_GITHUB_REPO", "Qiu-He-123/liyang-backups")
            src = download_asset(repo, token, args.tag, tmp)
        prepared = prepare(src)
        if prepared.name.endswith(".sqlite3"):
            restore_sqlite(prepared)
        elif prepared.name.endswith(".sql"):
            restore_mysql(prepared)
        else:
            sys.exit(f"错误: 无法识别备份文件类型: {prepared.name}")
        print("恢复完成。请重启后端服务。")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
