"""add match_queue.tag_required column for three-state tag matching

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-28

新增：
- match_queue.tag_required 字段（JSON 数组字符串，存储"必须有"的标签）
- 用于实现三态标签匹配：无所谓 / 尽量有 / 必须有
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table 兼容 SQLite
    with op.batch_alter_table("match_queue") as batch_op:
        batch_op.add_column(
            sa.Column("tag_required", sa.Text(), server_default="[]", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("match_queue") as batch_op:
        batch_op.drop_column("tag_required")
