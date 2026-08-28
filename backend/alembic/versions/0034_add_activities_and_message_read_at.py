"""add activities and message read_at

Revision ID: 0034

新增活动板块：activities 表（活动信息）+ activity_participants 表（报名）；
私聊消息表增加 read_at 字段用于已读回执。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0034"
down_revision: str = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("read_at", sa.DateTime(), nullable=True))

    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=100), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("organizer", sa.String(length=100), nullable=True),
        sa.Column("contact", sa.String(length=100), nullable=True),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("participant_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "activity_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_participants_activity_user"),
    )


def downgrade() -> None:
    op.drop_table("activity_participants")
    op.drop_table("activities")
    op.drop_column("messages", "read_at")
