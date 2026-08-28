"""宠物好感度与道具背包。

新增：
- user_pets.affinity：好感度 0-100（喂食/互动累积）
- pet_products.kind：1=活体宠物 2=道具（食物等可重复购买）
- pet_products.affinity_gain：喂食加好感数值
- user_pet_items：道具背包（user_id + product_id 唯一，qty 计数）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0046"
down_revision: str = "0045"
branch_labels: None
depends_on = None


def upgrade() -> None:
    op.add_column("user_pets", sa.Column("affinity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pet_products", sa.Column("kind", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("pet_products", sa.Column("affinity_gain", sa.Integer(), nullable=False, server_default="5"))
    op.create_index("ix_pet_products_kind", "pet_products", ["kind"])
    op.create_table(
        "user_pet_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("pet_products.id"), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "product_id", name="uq_user_pet_item"),
    )
    op.create_index("ix_user_pet_items_user_id", "user_pet_items", ["user_id"])
    op.create_index("ix_user_pet_items_product_id", "user_pet_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_user_pet_items_product_id", table_name="user_pet_items")
    op.drop_index("ix_user_pet_items_user_id", table_name="user_pet_items")
    op.drop_table("user_pet_items")
    op.drop_index("ix_pet_products_kind", table_name="pet_products")
    op.drop_column("pet_products", "affinity_gain")
    op.drop_column("pet_products", "kind")
    op.drop_column("user_pets", "affinity")
