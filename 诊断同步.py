# -*- coding: utf-8 -*-
"""同步链路诊断：在哪台机器上跑，就用哪台机器的 python 跑。

用法（在仓库根目录）：
    backend\\.venv\\Scripts\\python.exe 诊断同步.py

逐项打印：账号发现 -> 数据目录 -> sns.db 定位 -> 密钥校验 -> 绑定/自动同步 ->
朋友圈数据量，一眼看出"为什么没同步 / 图片为什么出不来"。
"""
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.services import wechat_local, wechat_sync_service  # noqa: E402


def main() -> int:
    print("=" * 62)
    print("  同步链路诊断")
    print("=" * 62)

    # 1) 账号发现
    print("\n[1] 账号发现（wechat_local.list_accounts）")
    accounts = wechat_local.list_accounts()
    if not accounts:
        print("    ❌ 没有任何账号！")
        print("       原因：微信同步客户端/账号配置 下没有带 db_key.txt 的账号目录，")
        print("       且常见微信数据目录里也没扫到 wxid_* 账号。")
        print("       解决：运行 启动服务器.py 向导，完成 选账号/数据库密钥/图片密钥 三步。")
        return 1
    for acc in accounts:
        print(f"    - {acc['account_id']}")

    # 2) 每个账号：数据目录 + sns.db + 密钥
    print("\n[2] 数据目录与 sns.db")
    ok_any = False
    for acc in accounts:
        datadir = acc.get("datadir") or "(空)"
        sns = wechat_local.resolve_sns_db(acc)
        key_len = len((acc.get("key_hex") or "").strip())
        key_ok = "?"
        if sns and key_len >= 32:
            try:
                key_ok = "✅" if wechat_local.check_key(sns, acc["key_hex"]) else "❌密钥不匹配"
            except Exception:
                key_ok = "❌密钥校验异常"
            ok_any = True
        elif sns and key_len < 32:
            key_ok = "❌缺密钥(db_key.txt)"
        print(f"    - {acc['account_id']}")
        print(f"      datadir : {datadir}")
        print(f"      sns.db  : {sns or '❌ 未找到（微信数据目录不对/微信未登录）'}")
        print(f"      密钥     : {key_ok}")

    # 3) 绑定与自动同步
    print("\n[3] 绑定与自动同步")
    with SessionLocal() as db:
        rows = db.execute(text(
            "SELECT user_id, wxid, nickname, sync_enabled, status, unbound_at FROM wechat_bindings"
        )).fetchall()
        if not rows:
            print("    ❌ 没有任何绑定！用户还没绑定微信 → 不会同步")
        else:
            for r in rows:
                print(
                    f"    - user={r[0]} wxid={r[1]} 昵称={r[2] or ''} "
                    f"自动同步={'✅开' if r[3] else '❌关'} status={r[4]} unbound={r[5] is not None}"
                )
        has_auto = wechat_sync_service.has_auto_sync_binding(db)
        print(f"    有开启自动同步的绑定: {'✅ 是' if has_auto else '❌ 否（不会自动入库）'}")
        moments = db.execute(text("SELECT COUNT(*) FROM wechat_moments")).fetchone()[0]
        print(f"    朋友圈库(wechat_moments)现有 {moments} 条")
        posts = db.execute(
            text("SELECT COUNT(*) FROM posts WHERE source LIKE 'wechat%'")
        ).fetchone()[0]
        print(f"    已发布的微信帖子 {posts} 条")

    # 4) sns.db 变化检测（自动同步的触发依据）
    print("\n[4] sns.db 变化检测（自动同步每 N 秒看这个）")
    mt = wechat_sync_service.sns_mtimes()
    for acc_id, m in mt.items():
        print(f"    - {acc_id}: {m if m else '❌ None（找不到 sns.db → 永远不会触发同步！）'}")

    print("\n" + "=" * 62)
    if ok_any and has_auto:
        print("  链路基本正常；若仍不同步，请确认微信端在刷新朋友圈、且新动态时间")
        print("  晚于「开启自动同步」的时间点。")
    else:
        print("  上方 ❌ 项就是问题所在，按提示处理。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
