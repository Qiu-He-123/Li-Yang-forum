"""add rate_limit and login_failure tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-26

T7-8：登录失败锁定持久化表 login_failures
T7-9：IP 限流计数表 rate_limits
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # T7-9：IP 限流计数表
    op.create_table(
        "rate_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("window_start", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_rate_limits_key", "rate_limits", ["key"], unique=True)

    # T7-8：登录失败锁定持久化表
    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_login_failures_phone", "login_failures", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_login_failures_phone", table_name="login_failures")
    op.drop_table("login_failures")
    op.drop_index("ix_rate_limits_key", table_name="rate_limits")
    op.drop_table("rate_limits")
