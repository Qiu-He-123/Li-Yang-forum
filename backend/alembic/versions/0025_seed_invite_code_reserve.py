"""seed invite code reserve (status / reserved_by / reserved_at)

Revision ID: 0025

种子邀请码后台优化：
- status: unused(未使用) / reserved(待使用) / used(已使用)
- reserved_by / reserved_at: 记录哪位管理员「复制 N 个未使用种子」带走，
  其他管理员看到「待使用」状态后避免重复分发同一批种子。
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: str = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="unused",
            )
        )
        batch_op.add_column(
            sa.Column(
                "reserved_by",
                sa.Integer(),
                sa.ForeignKey("admin.id", name="fk_seed_invite_codes_reserved_by_admin"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("reserved_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_seed_invite_codes_status", ["status"])

    # 历史数据迁移：已使用的种子码 status 置为 used
    op.execute("UPDATE seed_invite_codes SET status='used' WHERE used_by IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.drop_index("ix_seed_invite_codes_status")
        batch_op.drop_column("reserved_at")
        batch_op.drop_column("reserved_by")
        batch_op.drop_column("status")
