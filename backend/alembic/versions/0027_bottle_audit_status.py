"""bottle audit status (pending / approved / rejected / manual_review)

Revision ID: 0027

漂流瓶增加 AI 内容审核：
- bottles.audit_status: pending(AI审核中) / approved(已通过) / rejected(未通过) / manual_review(人工审核中)
- bottles.reject_reason: 未通过原因
- 只有 approved 的瓶子进入拾取池；AI 不可用时转人工审核，不直接放行
- 历史 active 瓶子默认 approved，避免上线后瓶子全部消失
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: str = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.add_column(
            sa.Column(
                "audit_status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(sa.Column("reject_reason", sa.String(length=200), nullable=True))
        batch_op.create_index("ix_bottles_audit_status", ["audit_status"])

    # 历史 active 瓶子视为已通过审核（上线前无审核机制，避免瓶子全部不可拾取）
    op.execute("UPDATE bottles SET audit_status='approved' WHERE status='active'")


def downgrade() -> None:
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.drop_index("ix_bottles_audit_status")
        batch_op.drop_column("reject_reason")
        batch_op.drop_column("audit_status")
