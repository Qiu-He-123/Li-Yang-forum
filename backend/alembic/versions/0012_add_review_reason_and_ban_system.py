"""add review reject reason and ban management system

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-28

阶段五：内容审核反馈 + 封号管理系统
- posts 新增 reject_reason 列：管理员审核未通过时填写原因
- comments 新增 reject_reason 列：同上
- users 新增 ban_until / ban_reason / violation_count 列：封号管理
- 新增 ban_records 表：封号记录（时长、原因、状态、是否可申诉）
- 新增 appeals 表：用户申诉解封（理由、状态、审核结果）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ posts 新增 reject_reason ============
    try:
        with op.batch_alter_table("posts") as batch_op:
            batch_op.add_column(sa.Column("reject_reason", sa.String(length=200), nullable=True))
    except Exception:
        pass

    # ============ comments 新增 reject_reason ============
    try:
        with op.batch_alter_table("comments") as batch_op:
            batch_op.add_column(sa.Column("reject_reason", sa.String(length=200), nullable=True))
    except Exception:
        pass

    # ============ users 新增封号字段 ============
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("ban_until", sa.DateTime(), nullable=True))
    except Exception:
        pass
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("ban_reason", sa.String(length=200), nullable=True))
    except Exception:
        pass
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("violation_count", sa.Integer(), nullable=False, server_default="0"))
    except Exception:
        pass

    # ============ ban_records 封号记录表 ============
    try:
        op.create_table(
            "ban_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("admin_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(length=200), nullable=False),
            sa.Column("duration_hours", sa.Integer(), nullable=False, server_default="0"),  # 0=永久封禁
            sa.Column("ban_until", sa.DateTime(), nullable=True),  # NULL=永久
            sa.Column("banned_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("unbanned_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),  # active/expired/revoked
            sa.Column("appealable", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["admin_id"], ["admin.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    except Exception:
        pass
    try:
        op.create_index("ix_ban_records_user_id", "ban_records", ["user_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_ban_records_status", "ban_records", ["status"])
    except Exception:
        pass

    # ============ appeals 申诉表 ============
    try:
        op.create_table(
            "appeals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("ban_record_id", sa.Integer(), nullable=True),  # 关联封号记录（可为空：一般申诉）
            sa.Column("reason", sa.Text(), nullable=False),  # 申诉理由
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),  # pending/approved/rejected
            sa.Column("reviewed_by", sa.Integer(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("review_comment", sa.Text(), nullable=True),  # 审核回复
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["ban_record_id"], ["ban_records.id"]),
            sa.ForeignKeyConstraint(["reviewed_by"], ["admin.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    except Exception:
        pass
    try:
        op.create_index("ix_appeals_user_id", "appeals", ["user_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_appeals_status", "appeals", ["status"])
    except Exception:
        pass


def downgrade() -> None:
    # 删除 appeals 表
    try:
        op.drop_index("ix_appeals_status", table_name="appeals")
    except Exception:
        pass
    try:
        op.drop_index("ix_appeals_user_id", table_name="appeals")
    except Exception:
        pass
    try:
        op.drop_table("appeals")
    except Exception:
        pass

    # 删除 ban_records 表
    try:
        op.drop_index("ix_ban_records_status", table_name="ban_records")
    except Exception:
        pass
    try:
        op.drop_index("ix_ban_records_user_id", table_name="ban_records")
    except Exception:
        pass
    try:
        op.drop_table("ban_records")
    except Exception:
        pass

    # 删除 users 封号字段
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("violation_count")
    except Exception:
        pass
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("ban_reason")
    except Exception:
        pass
    try:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("ban_until")
    except Exception:
        pass

    # 删除 comments reject_reason
    try:
        with op.batch_alter_table("comments") as batch_op:
            batch_op.drop_column("reject_reason")
    except Exception:
        pass

    # 删除 posts reject_reason
    try:
        with op.batch_alter_table("posts") as batch_op:
            batch_op.drop_column("reject_reason")
    except Exception:
        pass
