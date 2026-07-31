"""add circle_views table for tracking viewed circles

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.create_table(
            "circle_views",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("circle_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False, index=True),
            sa.Column("viewed_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("user_id", "circle_id", name="uq_circle_views_user_circle"),
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_table("circle_views")
    except Exception:
        pass
