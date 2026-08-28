"""0060 用户额外宠物领养位

新增 users.pet_extra_slots：用户通过购买商城"宠物领养位"商品（kind=4）累加，
可在基础上限(MAX_OWNED_PETS=2)之上再多养宠物。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pet_extra_slots", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "pet_extra_slots")