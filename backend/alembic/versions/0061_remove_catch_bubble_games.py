"""0061 移除「接零食/戳泡泡」游戏

对应前端 PetPlay.vue 下线 catch/bubble 两款内置小游戏，
从 games 表删除对应种子数据（已在既有库中存在的行）。
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM games WHERE slug IN ('catch', 'bubble')")


def downgrade() -> None:
    # 不重新插入：种子数据在 0057 中定义，回滚不重建
    pass