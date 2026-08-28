"""add captcha tickets and download tokens

Revision ID: 0035

新增：
- captcha_tickets：图形验证码票据（一次性、5 分钟过期、绑定 IP）
- download_tokens：APK 下载放行令牌（验证码通过后签发，一次性、2 分钟过期、绑定 IP）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0035"
down_revision: str = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "captcha_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("answer", sa.String(length=16), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_captcha_tickets_ticket_id", "captcha_tickets", ["ticket_id"], unique=True)
    op.create_index("ix_captcha_tickets_created_at", "captcha_tickets", ["created_at"])

    op.create_table(
        "download_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_download_tokens_token", "download_tokens", ["token"], unique=True)
    op.create_index("ix_download_tokens_created_at", "download_tokens", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_download_tokens_created_at", table_name="download_tokens")
    op.drop_index("ix_download_tokens_token", table_name="download_tokens")
    op.drop_table("download_tokens")
    op.drop_index("ix_captcha_tickets_created_at", table_name="captcha_tickets")
    op.drop_index("ix_captcha_tickets_ticket_id", table_name="captcha_tickets")
    op.drop_table("captcha_tickets")
