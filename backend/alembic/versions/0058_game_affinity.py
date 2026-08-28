"""0058 每游戏每日金币/好感上限

新增：
- games 表增加 affinity_daily_limit（每日通过该游戏可获得的好感度上限，默认 20）
- game_affinity_records 表：按 (user_id, game_key, date) 记录每天通过各游戏获得的好感度
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) games 增加好感度上限列
    op.add_column("games", sa.Column("affinity_daily_limit", sa.Integer, nullable=False, server_default="20"))

    # 2) 好感度逐游戏每日累计表
    op.create_table(
        "game_affinity_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("game_key", sa.String(32), nullable=False, index=True),
        sa.Column("date", sa.String(10), nullable=False, server_default="", index=True),
        sa.Column("amount", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "game_key", "date", name="uq_game_affinity_user_game_date"),
    )


def downgrade() -> None:
    op.drop_table("game_affinity_records")
    op.drop_column("games", "affinity_daily_limit")