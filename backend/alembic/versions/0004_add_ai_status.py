"""add ai_status column to posts and comments

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26

功能改造：发帖/评论改为「先落库（pending）→ 立即返回 → 后台异步审核 → 更新状态」。
- posts.ai_status: pending / approved / rejected / manual_review
- comments.ai_status: 同上

注意：SQLite 下 add_column 必须用 batch_alter_table，否则报
"Can't invoke function 'add_column', as the proxy object has not yet been established"。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 给 posts 加 ai_status 字段；老数据默认 approved（不再重审）
    with op.batch_alter_table("posts") as batch_op:
        batch_op.add_column(
            sa.Column("ai_status", sa.String(length=20), nullable=False, server_default="approved")
        )
    op.create_index("ix_posts_ai_status", "posts", ["ai_status"])

    # 给 comments 加 ai_status 字段；老数据默认 approved
    with op.batch_alter_table("comments") as batch_op:
        batch_op.add_column(
            sa.Column("ai_status", sa.String(length=20), nullable=False, server_default="approved")
        )
    op.create_index("ix_comments_ai_status", "comments", ["ai_status"])


def downgrade() -> None:
    op.drop_index("ix_comments_ai_status", table_name="comments")
    with op.batch_alter_table("comments") as batch_op:
        batch_op.drop_column("ai_status")
    op.drop_index("ix_posts_ai_status", table_name="posts")
    with op.batch_alter_table("posts") as batch_op:
        batch_op.drop_column("ai_status")
