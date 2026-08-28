"""0048 宠物饱食度 + 点击互动计数

- user_pets 新增字段：
  - satiety (INT) 饱食度 0-100（默认100，每4小时衰减10点，低于30进入饿虚状态）
  - last_satiety_decay (DATETIME) 上次饱食度衰减时间
  - interact_count (INT) 点击互动计数（用于假随机掉落 pity 机制）
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_pets") as batch_op:
        batch_op.add_column(sa.Column("satiety", sa.Integer, nullable=False, server_default="100"))
        batch_op.add_column(sa.Column("last_satiety_decay", sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column("interact_count", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("user_pets") as batch_op:
        batch_op.drop_column("interact_count")
        batch_op.drop_column("last_satiety_decay")
        batch_op.drop_column("satiety")
