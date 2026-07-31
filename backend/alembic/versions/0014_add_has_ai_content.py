"""add has_ai_content column to posts

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-28

帖子新增 has_ai_content 字段：用户声明帖子是否包含AI生成内容
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.add_column("posts", sa.Column("has_ai_content", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_column("posts", "has_ai_content")
    except Exception:
        pass
