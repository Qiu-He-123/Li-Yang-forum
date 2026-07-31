"""add circle apply (user-created bars) tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-27

阶段四：用户自创建吧（参考百度贴吧）
- categories 新增 creator_id / status / reject_reason / audit_at 列
  - creator_id: 创建者用户 id（系统初始化的圈子为 NULL）
  - status: pending(待审核) / approved(已通过) / rejected(已拒绝)，老数据默认 approved
  - reject_reason: 拒绝原因
  - audit_at: 审核时间
- 新增 category_admins 表：吧主（圈子管理员）关系
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ categories 新增字段 ============
    # SQLite 下 add_column 必须用 batch_alter_table
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.add_column(sa.Column("creator_id", sa.Integer(), nullable=True))
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.add_column(
                sa.Column("status", sa.String(length=20), nullable=False, server_default="approved")
            )
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.add_column(sa.Column("reject_reason", sa.String(length=200), nullable=True))
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.add_column(sa.Column("audit_at", sa.DateTime(), nullable=True))
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.add_column(sa.Column("audited_by", sa.Integer(), nullable=True))
    except Exception:
        pass

    # 索引
    try:
        op.create_index("ix_categories_creator_id", "categories", ["creator_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_categories_status", "categories", ["status"])
    except Exception:
        pass

    # ============ category_admins 吧主表 ============
    try:
        op.create_table(
            "category_admins",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False, server_default="owner"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("category_id", "user_id", name="uq_category_admins_category_user"),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    except Exception:
        pass
    try:
        op.create_index("ix_category_admins_category_id", "category_admins", ["category_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_category_admins_user_id", "category_admins", ["user_id"])
    except Exception:
        pass


def downgrade() -> None:
    # 删除吧主表
    try:
        op.drop_index("ix_category_admins_user_id", table_name="category_admins")
    except Exception:
        pass
    try:
        op.drop_index("ix_category_admins_category_id", table_name="category_admins")
    except Exception:
        pass
    try:
        op.drop_table("category_admins")
    except Exception:
        pass

    # 删除 categories 新增索引和字段
    try:
        op.drop_index("ix_categories_status", table_name="categories")
    except Exception:
        pass
    try:
        op.drop_index("ix_categories_creator_id", table_name="categories")
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.drop_column("audit_at")
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.drop_column("audited_by")
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.drop_column("reject_reason")
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.drop_column("status")
    except Exception:
        pass
    try:
        with op.batch_alter_table("categories") as batch_op:
            batch_op.drop_column("creator_id")
    except Exception:
        pass
