"""0067 全局推送管理配置

新增 push_global_settings 表，管理员可全局控制每个通知类型：
- show_badge: 该类型是否计入未读红点
- notify_enabled: 该类型是否允许向用户弹出推送
默认全开，不影响存量行为。
"""
from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_global_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ntype", sa.String(20), nullable=False),
        sa.Column("show_badge", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ntype", name="uq_push_global_settings_ntype"),
    )
    op.create_index("ix_push_global_settings_ntype", "push_global_settings", ["ntype"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_push_global_settings_ntype", table_name="push_global_settings")
    op.drop_table("push_global_settings")