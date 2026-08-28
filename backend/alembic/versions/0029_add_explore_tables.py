"""explore-exploit recommendation tables

Revision ID: 0029

1. post_explore_stats：帖子探索统计（曝光 / 点击 / 互动奖励），
   支撑热门流 ε-Greedy + Thompson 采样反馈闭环
2. feed_impression_logs：探索曝光日志（后台效果分析 / 审计）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: str = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_explore_stats",
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), primary_key=True),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "feed_impression_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False, index=True),
        sa.Column("target_id", sa.Integer(), nullable=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("scene", sa.String(length=20), nullable=False, server_default="post_feed", index=True),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("feed_impression_logs")
    op.drop_table("post_explore_stats")
