"""0066 用户 QQ 号全局唯一

QQ 号可作为登录标识（账号 或 QQ 号均可登录），必须全局唯一。
在 users.qq 上添加唯一索引，数据库层面强制"QQ号不可重复"。
SQLite 中 NULL 不参与唯一约束冲突，未填 QQ 的用户不受影响。
"""
from alembic import op
import sqlalchemy as sa

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_users_qq", "users", ["qq"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_users_qq", table_name="users")