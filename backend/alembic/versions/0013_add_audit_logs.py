"""add ai audit logs table

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-28

AI审核日志表：记录每次 AI 审核的完整信息
- target_type: post / comment
- target_id: 帖子或评论 ID
- ai_provider: deepseek / openai / none
- result: approved / rejected / error
- reason / category / severity / content_snapshot
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("target_type", sa.String(length=20), nullable=False),  # post / comment
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("ai_provider", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("result", sa.String(length=20), nullable=False, server_default="approved"),
            sa.Column("reason", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("category", sa.String(length=30), nullable=False, server_default="none"),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("content_snapshot", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_target_type", "audit_logs", ["target_type"])
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_result", "audit_logs", ["result"])
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index("ix_audit_logs_result", table_name="audit_logs")
    except Exception:
        pass
    try:
        op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    except Exception:
        pass
    try:
        op.drop_index("ix_audit_logs_target_id", table_name="audit_logs")
    except Exception:
        pass
    try:
        op.drop_index("ix_audit_logs_target_type", table_name="audit_logs")
    except Exception:
        pass
    try:
        op.drop_table("audit_logs")
    except Exception:
        pass
