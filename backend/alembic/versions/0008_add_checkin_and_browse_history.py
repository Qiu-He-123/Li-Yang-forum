"""Add check_ins and browse_histories tables.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27

新增表：
- check_ins          每日签到记录
- browse_histories   用户浏览帖子历史
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # check_ins 表
    try:
        op.create_table(
            "check_ins",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("check_in_date", sa.DateTime(), nullable=False, index=True),
            sa.Column("consecutive_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reward_points", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "check_in_date", name="uq_check_ins_user_date"),
        )
    except Exception:
        pass  # 表已存在

    # browse_histories 表
    try:
        op.create_table(
            "browse_histories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False, index=True),
            sa.Column("viewed_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("user_id", "post_id", name="uq_browse_histories_user_post"),
        )
    except Exception:
        pass  # 表已存在


def downgrade() -> None:
    try:
        op.drop_table("browse_histories")
    except Exception:
        pass
    try:
        op.drop_table("check_ins")
    except Exception:
        pass
