"""image audit status (pending / approved / rejected)

Revision ID: 0026

图片上传默认进入人工审核（不走 AI 审核）：
- images.audit_status: pending(待人工审核) / approved(已通过) / rejected(已驳回)
- 历史图片默认 approved，避免刷屏进入审核队列；新上传图片显式标记 pending
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: str = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("images") as batch_op:
        batch_op.add_column(
            sa.Column(
                "audit_status",
                sa.String(length=20),
                nullable=False,
                server_default="approved",
            )
        )
        batch_op.create_index("ix_images_audit_status", ["audit_status"])


def downgrade() -> None:
    with op.batch_alter_table("images") as batch_op:
        batch_op.drop_index("ix_images_audit_status")
        batch_op.drop_column("audit_status")
