"""0065 抽奖系统 + 同伴圈 AI 助手日志表结构

抽奖（提现改抽奖）：
- lottery_accounts    用户抽奖券账户
- lottery_prizes      奖池奖品（权重 / 数量范围 / 爆率峰值 / 广告加成）
- lottery_draws       一次抽取记录
- lottery_inventory   中奖待领/兑付明细
AI 助手日志：
- ai_chat_logs        全局 AI 助手对话埋点日志
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lottery_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("ticket_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_draws", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_lottery_account_user"),
    )
    op.create_table(
        "lottery_prizes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("min_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("hot_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ad_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_ad_times", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "lottery_draws",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("prize_id", sa.Integer(), sa.ForeignKey("lottery_prizes.id"), nullable=False),
        sa.Column("prize_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("base_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ad_times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ad_qty_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "lottery_inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("draw_id", sa.Integer(), sa.ForeignKey("lottery_draws.id"), nullable=False, index=True),
        sa.Column("prize_id", sa.Integer(), sa.ForeignKey("lottery_prizes.id"), nullable=False),
        sa.Column("prize_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=255), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ai_chat_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("input", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("intent", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ai_chat_logs")
    op.drop_table("lottery_inventory")
    op.drop_table("lottery_draws")
    op.drop_table("lottery_prizes")
    op.drop_table("lottery_accounts")