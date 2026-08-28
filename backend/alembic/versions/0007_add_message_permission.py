"""Add message_permission column to users table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27

私信权限字段：
- everyone       所有人可发
- mutual_only    仅互关可发
- stranger_once  陌生人每天可发 1 条（默认）
- no_stranger    不接受陌生人消息
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.add_column(
            "users",
            sa.Column(
                "message_permission",
                sa.String(20),
                nullable=False,
                server_default="stranger_once",
            ),
        )
    except Exception:
        pass  # 列已存在


def downgrade() -> None:
    try:
        op.drop_column("users", "message_permission")
    except Exception:
        pass
