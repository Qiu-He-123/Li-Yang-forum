"""add warning_score system: User.warning_score + warning_logs + warning_config

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. User 表新增 warning_score 字段
    try:
        op.add_column("users", sa.Column("warning_score", sa.Integer(), nullable=False, server_default="0"))
    except Exception:
        pass

    # 2. 警告值变动记录表
    try:
        op.create_table(
            "warning_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            # 变化量：正数增加（违规），负数减少（签到/发帖/管理员调整）
            sa.Column("delta", sa.Integer(), nullable=False),
            # 变动后的警告值
            sa.Column("score_after", sa.Integer(), nullable=False, default=0),
            # 变动原因描述
            sa.Column("reason", sa.String(200), nullable=False),
            # 来源：violation(违规) / checkin(签到) / post(发帖审核通过) / comment(评论审核通过) / admin_adjust(管理员调整) / system(系统)
            sa.Column("source", sa.String(20), nullable=False, default="system", index=True),
            # 关联对象类型和 ID（如 post/comment）
            sa.Column("related_type", sa.String(20), nullable=True),
            sa.Column("related_id", sa.Integer(), nullable=True),
            # 操作管理员 ID（仅 admin_adjust 有值）
            sa.Column("operator_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
    except Exception:
        pass

    # 3. 警告值配置表（单行配置，id 固定为 1）
    try:
        op.create_table(
            "warning_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            # 警告阈值：达到此值发警告通知但不封号
            sa.Column("warn_threshold", sa.Integer(), nullable=False, server_default="30"),
            # 临时封号阈值：达到此值封号 temp_ban_hours 小时
            sa.Column("temp_ban_threshold", sa.Integer(), nullable=False, server_default="60"),
            # 临时封号时长（小时）
            sa.Column("temp_ban_hours", sa.Integer(), nullable=False, server_default="24"),
            # 永久封号阈值：达到此值永久封号
            sa.Column("perm_ban_threshold", sa.Integer(), nullable=False, server_default="100"),
            # 每次违规基础增加值
            sa.Column("violation_base_score", sa.Integer(), nullable=False, server_default="20"),
            # 签到减少警告值
            sa.Column("checkin_reduce", sa.Integer(), nullable=False, server_default="2"),
            # 发帖审核通过减少警告值
            sa.Column("post_reduce", sa.Integer(), nullable=False, server_default="1"),
            # 评论审核通过减少警告值
            sa.Column("comment_reduce", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        )
        # 插入默认配置
        op.execute(
            "INSERT INTO warning_config (id, warn_threshold, temp_ban_threshold, temp_ban_hours, "
            "perm_ban_threshold, violation_base_score, checkin_reduce, post_reduce, comment_reduce) "
            "VALUES (1, 30, 60, 24, 100, 20, 2, 1, 1)"
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_table("warning_config")
    except Exception:
        pass
    try:
        op.drop_table("warning_logs")
    except Exception:
        pass
    try:
        op.drop_column("users", "warning_score")
    except Exception:
        pass
