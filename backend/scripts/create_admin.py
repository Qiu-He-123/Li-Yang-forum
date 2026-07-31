"""创建管理员账号的 CLI 脚本。

用法：
    python scripts/create_admin.py <username> <password> [--role super]

T2-3：移除 admin_login 中自动创建 admin/admin123456 的后门后，
首次部署必须通过本脚本初始化管理员账号。

示例：
    python scripts/create_admin.py admin MyStrongPwd@2026
    python scripts/create_admin.py ops AdminOpsPwd@2026 --role admin
"""
import argparse
import sys
from pathlib import Path

# 把 backend/ 加入 sys.path，让脚本可在任意目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Admin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="创建立洋社区管理员账号")
    parser.add_argument("username", help="管理员用户名（1-32 字符）")
    parser.add_argument("password", help="管理员密码（建议 ≥ 12 位，包含大小写+数字+符号）")
    parser.add_argument(
        "--role",
        default="super",
        choices=["super", "admin"],
        help="角色：super（超级管理员，默认）/ admin（普通管理员）",
    )
    args = parser.parse_args()

    if len(args.username) < 1 or len(args.username) > 32:
        print("[ERROR] 用户名长度需在 1-32 之间", file=sys.stderr)
        return 2
    if len(args.password) < 8:
        print("[ERROR] 密码长度至少 8 位", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        existing = db.scalar(select(Admin).where(Admin.username == args.username))
        if existing:
            print(f"[ERROR] 用户名 '{args.username}' 已存在", file=sys.stderr)
            return 1

        admin = Admin(
            username=args.username,
            password_hash=hash_password(args.password),
            role=args.role,
        )
        db.add(admin)
        db.commit()
        print(f"[OK] 管理员 '{args.username}' (role={args.role}) 创建成功，id={admin.id}")
        print("现在可以用此账号通过 /admin/login 接口登录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
