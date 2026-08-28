"""add is_private to images

Revision ID: 0023
P0-1：私密图片（学生证/校园卡等敏感照片）与公开图片分离，
防止敏感照片通过公开静态目录 /uploads 泄露。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: str = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "images",
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("images") as batch_op:
        batch_op.drop_column("is_private")
