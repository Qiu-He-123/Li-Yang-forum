"""0047 宠物进化系统 + 好感防刷 + 互动冷却

- user_pets 新增字段：
  - level (INT) 宠物等级 1-6（由好感度阶段决定，冗余存储方便查询）
  - evolved (BOOLEAN) 是否已超级进化（好感满100 + 使用进化道具后为 True）
  - evolved_at (DATETIME) 进化时间
  - nickname (VARCHAR 20) 宠物昵称（进化后可自定义）
  - last_pet_at / last_feed_at / last_play_at (DATETIME) 各互动类型最后时间，服务端冷却
  - daily_affinity_date (VARCHAR 10) 每日好感上限计数日期（YYYY-MM-DD）
  - daily_affinity_gained (INT) 当日已获好感数
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_pets") as batch_op:
        batch_op.add_column(sa.Column("level", sa.Integer, nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("evolved", sa.Boolean, nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("evolved_at", sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column("nickname", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("last_pet_at", sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column("last_feed_at", sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column("last_play_at", sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column("daily_affinity_date", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("daily_affinity_gained", sa.Integer, nullable=False, server_default="0"))

    # 根据现有 affinity 回填 level
    op.execute(
        "UPDATE user_pets SET level = "
        "CASE "
        "WHEN affinity >= 80 THEN 5 "
        "WHEN affinity >= 60 THEN 4 "
        "WHEN affinity >= 40 THEN 3 "
        "WHEN affinity >= 20 THEN 2 "
        "ELSE 1 END"
    )


def downgrade() -> None:
    with op.batch_alter_table("user_pets") as batch_op:
        batch_op.drop_column("daily_affinity_gained")
        batch_op.drop_column("daily_affinity_date")
        batch_op.drop_column("last_play_at")
        batch_op.drop_column("last_feed_at")
        batch_op.drop_column("last_pet_at")
        batch_op.drop_column("nickname")
        batch_op.drop_column("evolved_at")
        batch_op.drop_column("evolved")
        batch_op.drop_column("level")
