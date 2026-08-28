"""宠物商城 + 组局系统。

新增：
- pet_categories：商品分类（含种子数据：猫粮/狗粮/零食/玩具/日用/医疗）
- pet_products：商品（含 3D 模型 model_3d_url 字段）
- gatherings：组局（线上开黑/线下活动，发起人自动占一个名额）
- gathering_participants：组局报名记录（一人一局一次）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0043"
down_revision: str = "0042"
branch_labels = None
depends_on = None

# 分类种子数据（id 固定，便于与管理端选择器对齐）
_SEED_CATEGORIES = [
    (1, "猫粮", "🐱", 1),
    (2, "狗粮", "🐕", 2),
    (3, "零食", "🍖", 3),
    (4, "玩具", "🎾", 4),
    (5, "日用", "🏠", 5),
    (6, "医疗", "💊", 6),
]


def upgrade() -> None:
    op.create_table(
        "pet_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("icon", sa.String(length=20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pet_categories_name", "pet_categories", ["name"], unique=True)

    op.create_table(
        "pet_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("pet_categories.id"), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("original_price", sa.Float(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("model_3d_url", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sales", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pet_products_name", "pet_products", ["name"])
    op.create_index("ix_pet_products_category_id", "pet_products", ["category_id"])
    op.create_index("ix_pet_products_status", "pet_products", ["status"])

    # 种子分类
    categories_tbl = sa.table(
        "pet_categories",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        categories_tbl,
        [{"id": i, "name": n, "icon": icon, "sort_order": sort} for i, n, icon, sort in _SEED_CATEGORIES],
    )

    op.create_table(
        "gatherings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="online"),
        sa.Column("category", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("max_people", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("joined_people", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("images", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="recruiting"),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gatherings_title", "gatherings", ["title"])
    op.create_index("ix_gatherings_type", "gatherings", ["type"])
    op.create_index("ix_gatherings_start_time", "gatherings", ["start_time"])
    op.create_index("ix_gatherings_status", "gatherings", ["status"])
    op.create_index("ix_gatherings_host_id", "gatherings", ["host_id"])

    op.create_table(
        "gathering_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gathering_id", sa.Integer(), sa.ForeignKey("gatherings.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gathering_id", "user_id", name="uq_gathering_user_once"),
    )
    op.create_index("ix_gathering_participants_gathering_id", "gathering_participants", ["gathering_id"])
    op.create_index("ix_gathering_participants_user_id", "gathering_participants", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_gathering_participants_user_id", table_name="gathering_participants")
    op.drop_index("ix_gathering_participants_gathering_id", table_name="gathering_participants")
    op.drop_table("gathering_participants")

    op.drop_index("ix_gatherings_host_id", table_name="gatherings")
    op.drop_index("ix_gatherings_status", table_name="gatherings")
    op.drop_index("ix_gatherings_start_time", table_name="gatherings")
    op.drop_index("ix_gatherings_type", table_name="gatherings")
    op.drop_index("ix_gatherings_title", table_name="gatherings")
    op.drop_table("gatherings")

    op.drop_index("ix_pet_products_status", table_name="pet_products")
    op.drop_index("ix_pet_products_category_id", table_name="pet_products")
    op.drop_index("ix_pet_products_name", table_name="pet_products")
    op.drop_table("pet_products")

    op.drop_index("ix_pet_categories_name", table_name="pet_categories")
    op.drop_table("pet_categories")
