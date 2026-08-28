"""0050 宠物 AI 赠送金币/好感度（按月额度）

- pet_ai_states 新增字段，记录当前自然月的赠送累计：
  - gift_month (VARCHAR(7), YYYY-MM)
  - gift_coins_granted (INT) 本月已赠送金币
  - gift_affinity_granted (INT) 本月已赠送好感度
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pet_ai_states") as batch_op:
        batch_op.add_column(sa.Column("gift_month", sa.String(7), nullable=True))
        batch_op.add_column(sa.Column("gift_coins_granted", sa.Integer, nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("gift_affinity_granted", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("pet_ai_states") as batch_op:
        batch_op.drop_column("gift_affinity_granted")
        batch_op.drop_column("gift_coins_granted")
        batch_op.drop_column("gift_month")