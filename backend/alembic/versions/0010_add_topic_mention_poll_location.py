"""Add topic/mention/poll/location tables for phase 2.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27

新增表：
- topics            话题表
- mentions          帖子 @ 提及关系表
- polls             投票表
- poll_options      投票选项表
- poll_votes        投票记录表
- topic_follows     用户关注话题表

修改表：
- posts 新增 topic_id（外键 topics.id）和 location 列
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 创建 topics 表
    try:
        op.create_table(
            "topics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False, unique=True),
            sa.Column("creator_id", sa.Integer(), nullable=True),
            sa.Column("post_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("description", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_topics_name"),
            sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        )
        op.create_index("ix_topics_name", "topics", ["name"])
        op.create_index("ix_topics_creator_id", "topics", ["creator_id"])
    except Exception:
        pass  # 表已存在

    # 2. 创建 mentions 表
    try:
        op.create_table(
            "mentions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("mentioned_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("post_id", "mentioned_user_id", name="uq_mentions_post_user"),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
            sa.ForeignKeyConstraint(["mentioned_user_id"], ["users.id"]),
        )
        op.create_index("ix_mentions_post_id", "mentions", ["post_id"])
        op.create_index("ix_mentions_mentioned_user_id", "mentions", ["mentioned_user_id"])
    except Exception:
        pass

    # 3. 创建 polls 表
    try:
        op.create_table(
            "polls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("post_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("multi_vote", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("deadline", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.UniqueConstraint("post_id", name="uq_polls_post_id"),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        )
        op.create_index("ix_polls_post_id", "polls", ["post_id"])
    except Exception:
        pass

    # 4. 创建 poll_options 表
    try:
        op.create_table(
            "poll_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("poll_id", sa.Integer(), nullable=False),
            sa.Column("content", sa.String(length=100), nullable=False),
            sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
            sa.ForeignKeyConstraint(["poll_id"], ["polls.id"]),
        )
        op.create_index("ix_poll_options_poll_id", "poll_options", ["poll_id"])
    except Exception:
        pass

    # 5. 创建 poll_votes 表
    try:
        op.create_table(
            "poll_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("option_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("option_id", "user_id", name="uq_poll_votes_option_user"),
            sa.ForeignKeyConstraint(["option_id"], ["poll_options.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        )
        op.create_index("ix_poll_votes_option_id", "poll_votes", ["option_id"])
        op.create_index("ix_poll_votes_user_id", "poll_votes", ["user_id"])
    except Exception:
        pass

    # 6. 创建 topic_follows 表
    try:
        op.create_table(
            "topic_follows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("topic_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "topic_id", name="uq_topic_follows_user_topic"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        )
        op.create_index("ix_topic_follows_user_id", "topic_follows", ["user_id"])
        op.create_index("ix_topic_follows_topic_id", "topic_follows", ["topic_id"])
    except Exception:
        pass

    # 7. 给 posts 表添加 topic_id 和 location 列
    try:
        op.add_column("posts", sa.Column("topic_id", sa.Integer(), nullable=True))
    except Exception:
        pass
    try:
        op.add_column("posts", sa.Column("location", sa.String(length=100), nullable=True))
    except Exception:
        pass
    try:
        op.create_index("ix_posts_topic_id", "posts", ["topic_id"])
    except Exception:
        pass
    try:
        op.create_foreign_key("fk_posts_topic_id_topics", "posts", "topics", ["topic_id"], ["id"])
    except Exception:
        pass


def downgrade() -> None:
    # 删除 posts 表的新列
    try:
        op.drop_constraint("fk_posts_topic_id_topics", "posts", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_index("ix_posts_topic_id", table_name="posts")
    except Exception:
        pass
    try:
        op.drop_column("posts", "location")
    except Exception:
        pass
    try:
        op.drop_column("posts", "topic_id")
    except Exception:
        pass

    for table in ("topic_follows", "poll_votes", "poll_options", "polls", "mentions", "topics"):
        try:
            op.drop_table(table)
        except Exception:
            pass
