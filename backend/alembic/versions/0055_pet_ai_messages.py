"""0055 宠物 AI（DeepSeek 引擎）对话核心表

新增：
- pet_ai_messages  宠物 AI 聊天记录（user/assistant/tool 多段消息）
- pet_ai_state     每用户每宠物 AI 运行时状态（Token 用量/主动调度/赠送额度/睡觉）

说明：旧版 pet_ai_states / pet_ai_logs / pet_ai_decision_logs（豆包引擎）已随重构弃用，
本迁移不改动这些历史表，仅新建重构后的表。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pet_ai_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pet_id", sa.Integer, sa.ForeignKey("pet_products.id"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="user", index=True),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("meta", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "pet_ai_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pet_id", sa.Integer, sa.ForeignKey("pet_products.id"), nullable=False, index=True),
        sa.Column("sleeping_until", sa.DateTime, nullable=True),
        sa.Column("daily_date", sa.String(10), nullable=True),
        sa.Column("daily_token", sa.Integer, nullable=False, server_default="0"),
        sa.Column("daily_proactive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime, nullable=True),
        sa.Column("next_proactive_at", sa.DateTime, nullable=True),
        sa.Column("last_gift_date", sa.String(10), nullable=True),
        sa.Column("last_gift_coins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_affinity_date", sa.String(10), nullable=True),
        sa.Column("last_affinity_add", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_affinity_sub", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "pet_id", name="uq_pet_ai_state_user_pet"),
    )


def downgrade() -> None:
    op.drop_table("pet_ai_state")
    op.drop_table("pet_ai_messages")
