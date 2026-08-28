"""0054 用户行为记录（宠物 AI 主动问话上下文）

新增 user_activities 表：前端上报用户在应用内的关键动作，
供宠物 AI 发起主动消息时看到当前上下文、自然接话。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_activities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("action", sa.String(40), nullable=False, index=True),
        sa.Column("detail", sa.Text, nullable=False, default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("user_activities")