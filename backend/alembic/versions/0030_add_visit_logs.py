"""add visit logs for website access statistics

Revision ID: 0030

新增 visit_logs 表：每次前端打开页面记录一行（IP / UA / 路径），
支撑后台「数据看板」的访问次数与独立 IP 统计。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0030"
down_revision: str = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ip", sa.String(length=45), nullable=False, index=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("visit_logs")
