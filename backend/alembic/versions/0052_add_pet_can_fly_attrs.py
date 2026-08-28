"""宠物商品新增 can_fly（可飞行）+ attrs（道具按类型定制数值 JSON）。

新增：
- pet_products.can_fly：布尔，宠物是否能飞行（自动触发"上抛悬空再落回"行为）
- pet_products.attrs：Text，道具按类型定制的数值字段（好感/饱腹/心情/玩耍/体力/健康等）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0052"
down_revision: str = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pet_products", sa.Column("can_fly", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("pet_products", sa.Column("attrs", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pet_products", "attrs")
    op.drop_column("pet_products", "can_fly")