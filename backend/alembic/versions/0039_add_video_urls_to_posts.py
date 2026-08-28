"""add video_urls to posts

Revision ID: 0039

- posts：新增 video_urls（JSON 数组），微信朋友圈视频（mp4）发布时写入，
  前端用 HTML5 <video> 渲染
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0039"
down_revision: str = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("video_urls", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("posts", "video_urls")
