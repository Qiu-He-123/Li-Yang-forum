"""每日竞猜系统（今日竞猜 + 押注 + 选项统计）。

Revision ID: 0042
新增：
- guesses：每日竞猜主题（is_active 指示当天是否在首页焦点区弹窗展示）
- guess_options：选项，含 total_points / total_users 统计
- guess_bets：用户押注（唯一约束：每人每天1次押注或今日不押注）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0042"
down_revision: str = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=False),
        sa.Column("winning_option_id", sa.Integer(), nullable=True),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("date_key", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("settled_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guesses_is_active", "guesses", ["is_active"])
    op.create_index("ix_guesses_deadline", "guesses", ["deadline"])
    op.create_index("ix_guesses_date_key", "guesses", ["date_key"])

    op.create_table(
        "guess_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guess_id", sa.Integer(), sa.ForeignKey("guesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_guess_options_guess_id", "guess_options", ["guess_id"])

    op.create_table(
        "guess_bets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("guess_id", sa.Integer(), sa.ForeignKey("guesses.id"), nullable=False),
        sa.Column("option_id", sa.Integer(), sa.ForeignKey("guess_options.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("settled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "guess_id", name="uq_user_guess_once"),
    )
    op.create_index("ix_guess_bets_user_id", "guess_bets", ["user_id"])
    op.create_index("ix_guess_bets_guess_id", "guess_bets", ["guess_id"])
    op.create_index("ix_guess_bets_result", "guess_bets", ["result"])


def downgrade() -> None:
    op.drop_index("ix_guess_bets_result", table_name="guess_bets")
    op.drop_index("ix_guess_bets_guess_id", table_name="guess_bets")
    op.drop_index("ix_guess_bets_user_id", table_name="guess_bets")
    op.drop_table("guess_bets")

    op.drop_index("ix_guess_options_guess_id", table_name="guess_options")
    op.drop_table("guess_options")

    op.drop_index("ix_guesses_date_key", table_name="guesses")
    op.drop_index("ix_guesses_deadline", table_name="guesses")
    op.drop_index("ix_guesses_is_active", table_name="guesses")
    op.drop_table("guesses")
