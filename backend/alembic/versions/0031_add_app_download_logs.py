"""add app download logs

Revision ID: 0031

新增 app_download_logs 表：每次手机端 APK 被下载记录一行（IP / UA），
支撑后台「数据看板」的下载次数与独立 IP 统计。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0031"
down_revision: str = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_download_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ip", sa.String(length=45), nullable=False, index=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_download_logs")
