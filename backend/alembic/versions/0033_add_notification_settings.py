"""add notification settings

Revision ID: 0033

新增 notification_settings 表：每个用户一行的通知偏好开关（点赞/评论/@我/粉丝/系统/私信），
供手机端通知服务与网页端通知设置页面读取。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0033"
down_revision: str = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("like", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("comment", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("mention", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("follow", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("dm", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_notification_settings_user_id"),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
