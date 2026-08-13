"""add video_share_text to posts

Revision ID: 0040

- posts：新增 video_share_text（抖音/快手原始分享文本，用于直链过期后重新解析）
  发布视频帖时保存，直链失效时前端可调 /videos/refresh-link 重新解析换新直链
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0040"
down_revision: str = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("video_share_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "video_share_text")
