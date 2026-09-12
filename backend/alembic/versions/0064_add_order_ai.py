"""0064 订单 AI（接单大厅对话助手）表结构

- order_ai_sessions 用户会话（每日 token 额度滚动 + 跨会话保留聊天记录）
- order_ai_messages  对话消息（user / assistant / tool 卡片）
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_ai_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("daily_date", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("daily_token", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_order_ai_session_user"),
    )
    op.create_table(
        "order_ai_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("order_ai_sessions.id"), nullable=False, index=True),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="assistant"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_ai_messages")
    op.drop_table("order_ai_sessions")