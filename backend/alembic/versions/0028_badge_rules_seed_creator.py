"""badge auto-grant rules + seed invite code creator

Revision ID: 0028

1. badge_rules：徽章自动发放规则表（动作 + 阈值 → 徽章），后台可配置
2. seed_invite_codes.created_by：记录种子码由哪位管理员生成（系统自动生成时为 NULL）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: str = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "badge_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=40), nullable=False, index=True),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id"), nullable=False, index=True),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("action", "threshold", name="uq_badge_rule_action_threshold"),
    )

    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("admin.id", name="fk_seed_invite_codes_created_by_admin"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.drop_column("created_by")
    op.drop_table("badge_rules")
