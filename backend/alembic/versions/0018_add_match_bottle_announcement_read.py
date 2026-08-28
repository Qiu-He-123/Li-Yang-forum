"""add match system: gender + announcement_read + bottles + bottle_picks + match_queue + match_sessions

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-28

新增：
- User.gender 字段（性别：male/female/unknown）
- announcement_reads 表（公告已读记录，登录后弹窗用）
- bottles 表（漂流瓶）
- bottle_picks 表（漂流瓶拾取记录，防重复匹配）
- match_queue 表（实时匹配队列）
- match_sessions 表（实时匹配临时会话）
- match_messages 表（临时聊天消息）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. User.gender 字段
    op.add_column("users", sa.Column("gender", sa.String(20), nullable=True, server_default="unknown"))

    # 2. 公告已读记录表
    op.create_table(
        "announcement_reads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("announcement_id", sa.Integer(), sa.ForeignKey("announcement.id"), index=True, nullable=False),
        sa.Column("read_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "announcement_id", name="uq_ann_read_user_ann"),
    )

    # 3. 漂流瓶表
    op.create_table(
        "bottles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("image_urls", sa.Text(), server_default="[]"),
        # 必选标签
        sa.Column("grade", sa.String(20), index=True, nullable=False),       # 高一/高二/高三
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), index=True, nullable=False),
        sa.Column("gender", sa.String(20), nullable=False, server_default="unknown"),  # 作者性别
        # 可选兴趣标签（JSON 数组字符串）
        sa.Column("tags", sa.Text(), server_default="[]"),
        # 状态：active(可拾取) / picked(已被拾取) / expired(过期)
        sa.Column("status", sa.String(20), server_default="active", index=True),
        sa.Column("picked_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("picked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 4. 漂流瓶拾取记录（防重复匹配：同一用户不能拾取同一作者两次）
    op.create_table(
        "bottle_picks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("picker_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("bottle_id", sa.Integer(), sa.ForeignKey("bottles.id"), index=True, nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("picker_id", "author_id", name="uq_bottle_pick_picker_author"),
    )

    # 5. 实时匹配队列
    op.create_table(
        "match_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("gender", sa.String(20), nullable=False, server_default="unknown"),       # 自己性别
        sa.Column("target_gender", sa.String(20), nullable=False, server_default="any"),    # 期望对方性别：male/female/any
        sa.Column("grades", sa.Text(), server_default="[]"),        # JSON 期望年级
        sa.Column("school_ids", sa.Text(), server_default="[]"),    # JSON 期望校区
        sa.Column("tags", sa.Text(), server_default="[]"),          # JSON 兴趣标签
        sa.Column("status", sa.String(20), server_default="waiting", index=True),  # waiting/matched/cancelled/timeout
        sa.Column("matched_with", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 6. 实时匹配会话
    op.create_table(
        "match_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_a", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("user_b", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("status", sa.String(20), server_default="active", index=True),  # active/ended/expired
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("mutual_follow", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 7. 临时聊天消息
    op.create_table(
        "match_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("match_sessions.id"), index=True, nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("match_messages")
    op.drop_table("match_sessions")
    op.drop_table("match_queue")
    op.drop_table("bottle_picks")
    op.drop_table("bottles")
    op.drop_table("announcement_reads")
    op.drop_column("users", "gender")
