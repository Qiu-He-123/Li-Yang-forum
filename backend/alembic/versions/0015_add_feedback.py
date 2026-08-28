"""add feedback and feedback_replies tables

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.create_table(
            "feedbacks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("category", sa.String(50), nullable=False, server_default="other"),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("contact", sa.String(200), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("image_urls", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        )
    except Exception:
        pass

    try:
        op.create_table(
            "feedback_replies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("feedback_id", sa.Integer(), sa.ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("replier_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_table("feedback_replies")
    except Exception:
        pass
    try:
        op.drop_table("feedbacks")
    except Exception:
        pass
