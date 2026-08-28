"""新增游戏成绩表（首页排行-游戏排行数据源）。

新增：
- game_records：每个用户每款小游戏的最佳战绩（higher-better 的分值）
  user_id + game_key 唯一，避免重复记录，提交时取较大值覆盖。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0051"
down_revision: str = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持 ALTER 加约束，唯一约束内联在建表语句里
    op.create_table(
        "game_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("game_key", sa.String(32), nullable=False),
        sa.Column("best_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "game_key", name="uq_game_record_user_game"),
    )


def downgrade() -> None:
    op.drop_table("game_records")
