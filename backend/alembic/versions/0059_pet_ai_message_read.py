"""0059 宠物 AI 消息已读标记

新增 pet_ai_messages.is_read：宠物 AI 发给用户的消息默认未读，
用于消息中心宠物会话红点（替代原先写入系统通知的方式）。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pet_ai_messages",
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("pet_ai_messages", "is_read")