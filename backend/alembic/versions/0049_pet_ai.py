"""0049 宠物 AI 对话

- pet_products 新增字段：
  - ai_enabled (BOOL) 该宠物是否启用 AI 对话
  - ai_persona (TEXT) 人设 prompt（后台可编辑）
  - ai_wake_enabled (BOOL) 是否允许 AI 主动找你
- 新表：
  - pet_ai_logs 调用日志（后台"查看调用信息"）
  - pet_ai_states 每用户每宠物 AI 运行状态 + 主动唤醒调度
  - pet_ai_decision_logs 模型"自主规划下次找你时间"决策历史
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pet_products") as batch_op:
        batch_op.add_column(sa.Column("ai_enabled", sa.Boolean, nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("ai_persona", sa.Text, nullable=True))
        batch_op.add_column(sa.Column("ai_wake_enabled", sa.Boolean, nullable=False, server_default="0"))

    op.create_table(
        "pet_ai_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pet_id", sa.Integer, sa.ForeignKey("pet_products.id"), nullable=False, index=True),
        sa.Column("pet_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("trigger", sa.String(20), nullable=False, server_default="chat", index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success", index=True),
        sa.Column("tool_used", sa.String(40), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_estimate", sa.Float, nullable=False, server_default="0"),
        sa.Column("brief", sa.Text, nullable=True),
        sa.Column("err", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pet_ai_logs_user_pet", "pet_ai_logs", ["user_id", "pet_id"])

    op.create_table(
        "pet_ai_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pet_id", sa.Integer, sa.ForeignKey("pet_products.id"), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("state_until", sa.DateTime, nullable=True),
        sa.Column("last_active_at", sa.DateTime, nullable=True),
        sa.Column("next_active_at", sa.DateTime, nullable=True),
        sa.Column("pending", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("active_msg", sa.Text, nullable=True),
        sa.Column("active_date", sa.String(10), nullable=True),
        sa.Column("active_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("quiet_until", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "pet_id", name="uq_pet_ai_state_once"),
    )

    op.create_table(
        "pet_ai_decision_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pet_id", sa.Integer, sa.ForeignKey("pet_products.id"), nullable=False, index=True),
        sa.Column("pet_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("delay_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("topic", sa.Text, nullable=True),
        sa.Column("adopted", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("invalidated", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("pet_ai_decision_logs")
    op.drop_table("pet_ai_states")
    op.drop_index("ix_pet_ai_logs_user_pet", table_name="pet_ai_logs")
    op.drop_table("pet_ai_logs")
    with op.batch_alter_table("pet_products") as batch_op:
        batch_op.drop_column("ai_wake_enabled")
        batch_op.drop_column("ai_persona")
        batch_op.drop_column("ai_enabled")