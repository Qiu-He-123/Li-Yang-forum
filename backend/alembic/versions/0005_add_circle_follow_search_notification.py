"""add circle/follow/search/notification fields and tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-26

新增字段：
- posts: title, is_original, view_count, share_count, last_reply_at
- users: grade, following_count, followers_count
- notifications: type, sender_id, reference_type, reference_id, read_at

新增表：
- categories: 圈子
- user_categories: 用户加入圈子关系
- follows: 用户关注关系
- search_histories: 搜索历史
- hot_searches: 热搜词

注意：SQLite 下 add_column 必须用 batch_alter_table。
所有新增字段必须有 server_default，确保旧数据兼容。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============ posts 新增字段 ============
    with op.batch_alter_table("posts") as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("is_original", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("share_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("last_reply_at", sa.DateTime(), nullable=True))

    # ============ users 新增字段 ============
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("grade", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("following_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("followers_count", sa.Integer(), nullable=False, server_default="0"))

    # ============ notifications 新增字段 ============
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("type", sa.String(length=20), nullable=False, server_default="system"))
        batch_op.add_column(sa.Column("sender_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reference_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("reference_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_notifications_type", ["type"])
        batch_op.create_index("ix_notifications_sender_id", ["sender_id"])

    # ============ categories 圈子表 ============
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("icon", sa.String(length=20), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=False, server_default="#007aff"),
        sa.Column("post_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("categories") as batch_op:
        batch_op.create_index("ix_categories_name", ["name"], unique=True)
        batch_op.create_index("ix_categories_slug", ["slug"], unique=True)

    # ============ user_categories 用户-圈子关系 ============
    op.create_table(
        "user_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category_id"),
    )
    with op.batch_alter_table("user_categories") as batch_op:
        batch_op.create_index("ix_user_categories_user_id", ["user_id"])
        batch_op.create_index("ix_user_categories_category_id", ["category_id"])

    # ============ follows 关注关系 ============
    op.create_table(
        "follows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("follower_id", sa.Integer(), nullable=False),
        sa.Column("followee_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["followee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("follower_id", "followee_id"),
    )
    with op.batch_alter_table("follows") as batch_op:
        batch_op.create_index("ix_follows_follower_id", ["follower_id"])
        batch_op.create_index("ix_follows_followee_id", ["followee_id"])

    # ============ search_histories 搜索历史 ============
    op.create_table(
        "search_histories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("search_histories") as batch_op:
        batch_op.create_index("ix_search_histories_user_id", ["user_id"])

    # ============ hot_searches 热搜 ============
    op.create_table(
        "hot_searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keyword"),
    )
    with op.batch_alter_table("hot_searches") as batch_op:
        batch_op.create_index("ix_hot_searches_keyword", ["keyword"], unique=True)


def downgrade() -> None:
    # 热搜
    with op.batch_alter_table("hot_searches") as batch_op:
        batch_op.drop_index("ix_hot_searches_keyword")
    op.drop_table("hot_searches")

    # 搜索历史
    with op.batch_alter_table("search_histories") as batch_op:
        batch_op.drop_index("ix_search_histories_user_id")
    op.drop_table("search_histories")

    # 关注
    with op.batch_alter_table("follows") as batch_op:
        batch_op.drop_index("ix_follows_followee_id")
        batch_op.drop_index("ix_follows_follower_id")
    op.drop_table("follows")

    # 用户-圈子关系
    with op.batch_alter_table("user_categories") as batch_op:
        batch_op.drop_index("ix_user_categories_category_id")
        batch_op.drop_index("ix_user_categories_user_id")
    op.drop_table("user_categories")

    # 圈子
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_index("ix_categories_slug")
        batch_op.drop_index("ix_categories_name")
    op.drop_table("categories")

    # notifications 字段
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_index("ix_notifications_sender_id")
        batch_op.drop_index("ix_notifications_type")
        batch_op.drop_column("read_at")
        batch_op.drop_column("reference_id")
        batch_op.drop_column("reference_type")
        batch_op.drop_column("sender_id")
        batch_op.drop_column("type")

    # users 字段
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("followers_count")
        batch_op.drop_column("following_count")
        batch_op.drop_column("grade")

    # posts 字段
    with op.batch_alter_table("posts") as batch_op:
        batch_op.drop_column("last_reply_at")
        batch_op.drop_column("share_count")
        batch_op.drop_column("view_count")
        batch_op.drop_column("is_original")
        batch_op.drop_column("title")
