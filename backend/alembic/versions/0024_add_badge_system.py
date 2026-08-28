"""add badge system (badges / badge_codes / user_badges / users.wearing_badge_id)

Revision ID: 0024

徽章系统：
- badges：徽章定义表（图标 + 名称 + code + 描述）
- badge_codes：徽章激活码表（管理员生成，用户输入激活码领取）
- user_badges：用户徽章关系表（一人可拥有多个徽章）
- users.wearing_badge_id：当前佩戴的徽章（选择其中一个展示在名字前）
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: str = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("icon", sa.String(length=500), nullable=False, server_default="🏅"),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_badges_name"), "badges", ["name"], unique=True)
    op.create_index(op.f("ix_badges_code"), "badges", ["code"], unique=True)

    op.create_table(
        "badge_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True, index=True),
        sa.Column("note", sa.String(length=100), nullable=True),
        sa.Column("batch_no", sa.String(length=32), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("used_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "badge_id", name="uq_user_badges_user_badge"),
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "wearing_badge_id",
                sa.Integer(),
                sa.ForeignKey("badges.id", name="fk_users_wearing_badge_id_badges"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_users_wearing_badge_id", ["wearing_badge_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_wearing_badge_id"))
        batch_op.drop_column("wearing_badge_id")
    op.drop_table("user_badges")
    op.drop_table("badge_codes")
    op.drop_index(op.f("ix_badges_name"), table_name="badges")
    op.drop_index(op.f("ix_badges_code"), table_name="badges")
    op.drop_table("badges")
