"""add announcement scope + guest one-time delivery

Revision ID: 0041
Revises: 0040

新增：
- announcement.scope：可见范围 all=所有人 / guest=仅游客(同IP只投递一次) / user=仅登录用户
- announcement_guest_views 表：游客公告投递记录，(announcement_id, ip) 唯一，
  同一 IP 对同一游客公告只展示/投递一次（发过一次就不再发）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "announcement",
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="all"),
    )
    op.create_table(
        "announcement_guest_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "announcement_id",
            sa.Integer(),
            sa.ForeignKey("announcement.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("announcement_id", "ip", name="uq_ann_guest_ann_ip"),
    )


def downgrade() -> None:
    op.drop_table("announcement_guest_views")
    op.drop_column("announcement", "scope")
