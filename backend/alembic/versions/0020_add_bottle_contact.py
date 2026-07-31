"""add bottle.contact column and migrate picked status to active

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-28

新增：
- bottles.contact 字段（联系方式，拾取成功后对拾取者可见）

变更：
- bottles.status: 将旧的 'picked' 状态迁移回 'active'（一个瓶子可被多人拾取）
- 新增 'recalled' 状态（作者主动收回）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 contact 字段
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.add_column(
            sa.Column("contact", sa.String(100), nullable=True, server_default=None)
        )

    # 2. 将旧的 'picked' 状态迁移回 'active'（一个瓶子可被多人拾取）
    op.execute("UPDATE bottles SET status='active' WHERE status='picked'")


def downgrade() -> None:
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.drop_column("contact")
