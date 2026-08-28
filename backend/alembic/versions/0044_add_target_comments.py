"""通用留言板（组局/活动留言）。

新增：
- target_comments：组局/活动等非帖子内容的留言与回复
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0044"
down_revision: str = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "target_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("target_comments.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_target_comments_target_type", "target_comments", ["target_type"])
    op.create_index("ix_target_comments_target_id", "target_comments", ["target_id"])
    op.create_index("ix_target_comments_user_id", "target_comments", ["user_id"])
    op.create_index("ix_target_comments_parent_id", "target_comments", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_target_comments_parent_id", table_name="target_comments")
    op.drop_index("ix_target_comments_user_id", table_name="target_comments")
    op.drop_index("ix_target_comments_target_id", table_name="target_comments")
    op.drop_index("ix_target_comments_target_type", table_name="target_comments")
    op.drop_table("target_comments")
