"""宠物领养系统。

新增：
- pet_products.anim_json：帧动画配置（DyberPet 像素宠物）
- user_pets：用户已领养宠物表（每人每只限 1，金币购买）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0045"
down_revision: str = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pet_products", sa.Column("anim_json", sa.Text(), nullable=True))
    op.create_table(
        "user_pets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("pet_products.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "product_id", name="uq_user_pet_once"),
    )
    op.create_index("ix_user_pets_user_id", "user_pets", ["user_id"])
    op.create_index("ix_user_pets_product_id", "user_pets", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_user_pets_product_id", table_name="user_pets")
    op.drop_index("ix_user_pets_user_id", table_name="user_pets")
    op.drop_table("user_pets")
    op.drop_column("pet_products", "anim_json")
