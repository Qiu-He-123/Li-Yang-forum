"""Add FriendRequest table and extend Message table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FriendRequest 表
    op.create_table(
        "friend_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("message", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_id", "to_id"),
    )
    op.create_index("ix_friend_requests_from_id", "friend_requests", ["from_id"])
    op.create_index("ix_friend_requests_to_id", "friend_requests", ["to_id"])
    op.create_index("ix_friend_requests_status", "friend_requests", ["status"])

    # Message 表扩展字段（如果列已存在则跳过）
    try:
        op.add_column("messages", sa.Column("msg_type", sa.String(20), nullable=False, server_default="text"))
    except Exception:
        pass  # 列已存在
    try:
        op.add_column("messages", sa.Column("conversation_id", sa.String(64), nullable=True))
    except Exception:
        pass
    try:
        op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    except Exception:
        pass


def downgrade() -> None:
    op.drop_index("ix_friend_requests_status", table_name="friend_requests")
    op.drop_index("ix_friend_requests_to_id", table_name="friend_requests")
    op.drop_index("ix_friend_requests_from_id", table_name="friend_requests")
    op.drop_table("friend_requests")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_column("messages", "conversation_id")
    op.drop_column("messages", "msg_type")
