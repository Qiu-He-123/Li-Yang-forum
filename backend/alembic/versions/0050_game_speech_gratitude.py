"""游戏动作触发宠物说话 + 感谢名单。

新增：
- pet_products.game_speech：陪我玩「动作→宠物说话」JSON 常量（自定义宠物可选填，与人设同块编辑）
- gratitude_list：感谢名单表（后台可编辑，前端列表 + 详情页）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0050"
down_revision: str = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 游戏触发说话常量（宠物维度，与 ai_persona 放一起）
    op.add_column(
        "pet_products",
        sa.Column("game_speech", sa.Text(), nullable=True))
    # 2. 感谢名单表
    op.create_table(
        "gratitude_list",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("bio", sa.String(200), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gratitude_list_sort_order", "gratitude_list", ["sort_order"])


def downgrade() -> None:
    op.drop_index("ix_gratitude_list_sort_order", table_name="gratitude_list")
    op.drop_table("gratitude_list")
    op.drop_column("pet_products", "game_speech")