"""add updated_at to wechat sync and coin tables

Revision ID: 0037

修复：0036 建 wechat_friends / wechat_bindings / wechat_moments / coin_transactions
时只建了 created_at，缺少 TimestampMixin 的 updated_at 列，
导致 SQLAlchemy SELECT 时报 "no such column: ...updated_at"。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0037"
down_revision: str = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("wechat_friends", "wechat_bindings", "wechat_moments", "coin_transactions"):
        op.add_column(
            table,
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    for table in ("wechat_friends", "wechat_bindings", "wechat_moments", "coin_transactions"):
        op.drop_column(table, "updated_at")
