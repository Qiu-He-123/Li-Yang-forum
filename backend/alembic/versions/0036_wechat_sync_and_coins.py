"""wechat sync and coins

Revision ID: 0036

新增：
- users.coins / users.onboarding_done：金币余额 + 新手引导标记
- badges.price：金币购买价格（0=不可购买）
- posts.source / wechat_moment_id / is_pinned / pinned_at / pinned_until / source_created_at
- wechat_friends：微信好友快照（绑定匹配用）
- wechat_bindings：用户-微信绑定（含自动同步开关与历史分界线 sync_enabled_at）
- wechat_moments：朋友圈原始动态（tid 去重）
- coin_transactions：金币流水
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0036"
down_revision: str = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("coins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("onboarding_done", sa.Boolean(), nullable=False, server_default="0"))

    op.add_column("badges", sa.Column("price", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("posts", sa.Column("source", sa.String(length=20), nullable=False, server_default="normal"))
    op.add_column("posts", sa.Column("wechat_moment_id", sa.Integer(), nullable=True))
    op.add_column("posts", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("posts", sa.Column("pinned_at", sa.DateTime(), nullable=True))
    op.add_column("posts", sa.Column("pinned_until", sa.DateTime(), nullable=True))
    op.add_column("posts", sa.Column("source_created_at", sa.DateTime(), nullable=True))
    op.create_index("ix_posts_source", "posts", ["source"])
    op.create_index("ix_posts_wechat_moment_id", "posts", ["wechat_moment_id"])
    op.create_index("ix_posts_is_pinned", "posts", ["is_pinned"])
    op.create_index("ix_posts_pinned_until", "posts", ["pinned_until"])
    op.create_index("ix_posts_source_created_at", "posts", ["source_created_at"])

    op.create_table(
        "wechat_friends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("wxid", sa.String(length=64), nullable=False),
        sa.Column("wechat_id", sa.String(length=64), nullable=True),
        sa.Column("nickname", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("remark", sa.String(length=100), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wechat_friends_wxid", "wechat_friends", ["wxid"], unique=True)
    op.create_index("ix_wechat_friends_wechat_id", "wechat_friends", ["wechat_id"])

    op.create_table(
        "wechat_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wxid", sa.String(length=64), nullable=False),
        sa.Column("wechat_id", sa.String(length=64), nullable=True),
        sa.Column("nickname", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sync_enabled_at", sa.DateTime(), nullable=True),
        sa.Column("bound_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("unbound_at", sa.DateTime(), nullable=True),
        sa.Column("unbound_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wechat_bindings_user_id", "wechat_bindings", ["user_id"], unique=True)
    op.create_index("ix_wechat_bindings_wxid", "wechat_bindings", ["wxid"], unique=True)

    op.create_table(
        "wechat_moments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tid", sa.String(length=64), nullable=False),
        sa.Column("wxid", sa.String(length=64), nullable=False),
        sa.Column("author_name", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(), nullable=True),
        sa.Column("media_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wechat_moments_tid", "wechat_moments", ["tid"], unique=True)
    op.create_index("ix_wechat_moments_wxid", "wechat_moments", ["wxid"])
    op.create_index("ix_wechat_moments_create_time", "wechat_moments", ["create_time"])

    op.create_table(
        "coin_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_coin_transactions_user_id", "coin_transactions", ["user_id"])
    op.create_index("ix_coin_transactions_type", "coin_transactions", ["type"])


def downgrade() -> None:
    op.drop_index("ix_coin_transactions_type", table_name="coin_transactions")
    op.drop_index("ix_coin_transactions_user_id", table_name="coin_transactions")
    op.drop_table("coin_transactions")
    op.drop_index("ix_wechat_moments_create_time", table_name="wechat_moments")
    op.drop_index("ix_wechat_moments_wxid", table_name="wechat_moments")
    op.drop_index("ix_wechat_moments_tid", table_name="wechat_moments")
    op.drop_table("wechat_moments")
    op.drop_index("ix_wechat_bindings_wxid", table_name="wechat_bindings")
    op.drop_index("ix_wechat_bindings_user_id", table_name="wechat_bindings")
    op.drop_table("wechat_bindings")
    op.drop_index("ix_wechat_friends_wechat_id", table_name="wechat_friends")
    op.drop_index("ix_wechat_friends_wxid", table_name="wechat_friends")
    op.drop_table("wechat_friends")
    op.drop_index("ix_posts_source_created_at", table_name="posts")
    op.drop_index("ix_posts_pinned_until", table_name="posts")
    op.drop_index("ix_posts_is_pinned", table_name="posts")
    op.drop_index("ix_posts_wechat_moment_id", table_name="posts")
    op.drop_index("ix_posts_source", table_name="posts")
    op.drop_column("posts", "source_created_at")
    op.drop_column("posts", "pinned_until")
    op.drop_column("posts", "pinned_at")
    op.drop_column("posts", "is_pinned")
    op.drop_column("posts", "wechat_moment_id")
    op.drop_column("posts", "source")
    op.drop_column("badges", "price")
    op.drop_column("users", "onboarding_done")
    op.drop_column("users", "coins")
