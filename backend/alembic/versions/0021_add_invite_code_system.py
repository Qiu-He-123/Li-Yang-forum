"""add invite code system (three-state auth)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-28

新增邀请码系统（三状态鉴权）：
- guest（游客）：未登录，只能看列表
- unverified（已注册未填邀请码）：能看帖子内容，但不能发帖/评论/匹配/漂流瓶
- verified（已填邀请码）：解锁全部功能

变更：
1. users 表：
   - 新增 username（登录账号，唯一索引）
   - phone 改为 nullable（向后兼容旧数据）
   - 新增 qq / verification_status / verified_at / invite_code / invite_code_shared_at
     / invited_by / invite_privilege_until 字段
2. posts / comments 表：新增 is_hidden_by_unverify 字段
3. 新表 invite_code_usages：邀请码使用记录（连坐追溯）
4. 新表 seed_invite_codes：管理员预生成的种子邀请码（冷启动）
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ 1. users 表改造 ============
    with op.batch_alter_table("users") as batch_op:
        # 新增 username 字段（登录账号）
        batch_op.add_column(
            sa.Column("username", sa.String(32), nullable=True, server_default=None)
        )
        # phone 改为 nullable（向后兼容，新注册不再使用 phone）
        batch_op.alter_column("phone", existing_type=sa.String(20), nullable=True)
        # 邀请码系统字段
        batch_op.add_column(sa.Column("qq", sa.String(20), nullable=True, server_default=None))
        batch_op.add_column(
            sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified")
        )
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column("invite_code", sa.String(16), nullable=True, server_default=None))
        batch_op.add_column(sa.Column("invite_code_shared_at", sa.DateTime(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column("invited_by", sa.Integer(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column("invite_privilege_until", sa.DateTime(), nullable=True, server_default=None))

    # username 唯一索引（部分索引，仅非 NULL 值唯一，避免多个 NULL 冲突）
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_index("ix_users_username", ["username"], unique=True)
        batch_op.create_index("ix_users_verification_status", ["verification_status"])
        batch_op.create_index("ix_users_invite_code", ["invite_code"], unique=True)

    # 旧用户数据迁移：如果有 phone 但没 username，用 phone 作为 username（向后兼容）
    op.execute("UPDATE users SET username = phone WHERE username IS NULL AND phone IS NOT NULL")
    # 旧用户默认视为 verified（避免影响现有用户体验）
    op.execute("UPDATE users SET verification_status = 'verified', verified_at = created_at WHERE verification_status = 'unverified'")

    # ============ 2. posts / comments 表加 is_hidden_by_unverify ============
    with op.batch_alter_table("posts") as batch_op:
        batch_op.add_column(
            sa.Column("is_hidden_by_unverify", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_index("ix_posts_is_hidden_by_unverify", ["is_hidden_by_unverify"])

    with op.batch_alter_table("comments") as batch_op:
        batch_op.add_column(
            sa.Column("is_hidden_by_unverify", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_index("ix_comments_is_hidden_by_unverify", ["is_hidden_by_unverify"])

    # ============ 3. 新表 invite_code_usages ============
    op.create_table(
        "invite_code_usages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inviter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invitee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("used_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.UniqueConstraint("invitee_id", name="uq_invitee_once"),
    )
    op.create_index("ix_invite_code_usages_inviter_id", "invite_code_usages", ["inviter_id"])
    op.create_index("ix_invite_code_usages_invitee_id", "invite_code_usages", ["invitee_id"])
    op.create_index("ix_invite_code_usages_code", "invite_code_usages", ["code"])
    op.create_index("ix_invite_code_usages_status", "invite_code_usages", ["status"])

    # ============ 4. 新表 seed_invite_codes ============
    op.create_table(
        "seed_invite_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("note", sa.String(100), nullable=True, server_default=None),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("used_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, server_default=None),
        sa.Column("used_at", sa.DateTime(), nullable=True, server_default=None),
    )
    op.create_index("ix_seed_invite_codes_code", "seed_invite_codes", ["code"], unique=True)


def downgrade() -> None:
    op.drop_table("seed_invite_codes")
    op.drop_table("invite_code_usages")

    with op.batch_alter_table("comments") as batch_op:
        batch_op.drop_index("ix_comments_is_hidden_by_unverify")
        batch_op.drop_column("is_hidden_by_unverify")

    with op.batch_alter_table("posts") as batch_op:
        batch_op.drop_index("ix_posts_is_hidden_by_unverify")
        batch_op.drop_column("is_hidden_by_unverify")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_invite_code")
        batch_op.drop_index("ix_users_verification_status")
        batch_op.drop_index("ix_users_username")
        batch_op.drop_column("invite_privilege_until")
        batch_op.drop_column("invited_by")
        batch_op.drop_column("invite_code_shared_at")
        batch_op.drop_column("invite_code")
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verification_status")
        batch_op.drop_column("qq")
        batch_op.alter_column("phone", existing_type=sa.String(20), nullable=False)
        batch_op.drop_column("username")
