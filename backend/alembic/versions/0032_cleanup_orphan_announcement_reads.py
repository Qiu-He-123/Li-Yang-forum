"""cleanup orphan announcement reads

Revision ID: 0032

清理历史脏数据：公告被删除后，announcement_reads 里可能残留孤儿记录。
由于 SQLite/MySQL 会复用被删除的 id，这些旧已读记录会指向新公告，
导致新公告"默认已读、不弹窗"。此迁移删除所有不存在的公告对应的已读记录。
"""
from alembic import op

revision: str = "0032"
down_revision: str = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM announcement_reads "
        "WHERE announcement_id NOT IN (SELECT id FROM announcement)"
    )


def downgrade() -> None:
    pass
