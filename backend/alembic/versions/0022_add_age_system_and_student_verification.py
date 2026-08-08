"""add age system (birthday) and student verification

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-28

变更：
1. users 表：新增 birthday 字段（日期类型，动态计算年龄替代 grade）
2. bottles 表：新增 author_age 字段（整数，投放时从生日计算的快照）
3. match_queue 表：新增 age_min / age_max 字段（期望年龄范围，替代 grades）
4. seed_invite_codes 表：新增 batch_no 字段（批次号，便于按批次管理）
5. 新表 student_verifications：学生认证申请（上传照片 → 管理员审核 → 自动发邀请码）

数据迁移：
- users.grade（初一~高三）→ 估算 birthday（初一=13岁，初二=14，...高三=18）
- bottles.grade → bottles.author_age（同上映射）
"""
import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 年级 → 年龄映射
GRADE_AGE_MAP = {
    "初一": 13,
    "初二": 14,
    "初三": 15,
    "高一": 16,
    "高二": 17,
    "高三": 18,
}


def upgrade() -> None:
    # ============ 1. users 表加 birthday ============
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("birthday", sa.Date(), nullable=True, server_default=None))

    # 数据迁移：grade → birthday（估算）
    conn = op.get_bind()
    today = datetime.date.today()
    for grade_name, age in GRADE_AGE_MAP.items():
        estimated_birthday = today.replace(year=today.year - age)
        conn.execute(
            sa.text(
                "UPDATE users SET birthday = :bd WHERE grade = :g AND birthday IS NULL"
            ),
            {"bd": estimated_birthday, "g": grade_name},
        )

    # ============ 2. bottles 表加 author_age ============
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.add_column(sa.Column("author_age", sa.Integer(), nullable=True, server_default=None))

    # 数据迁移：bottles.grade → bottles.author_age
    for grade_name, age in GRADE_AGE_MAP.items():
        conn.execute(
            sa.text(
                "UPDATE bottles SET author_age = :age WHERE grade = :g AND author_age IS NULL"
            ),
            {"age": age, "g": grade_name},
        )

    # ============ 3. match_queue 表加 age_min / age_max ============
    with op.batch_alter_table("match_queue") as batch_op:
        batch_op.add_column(sa.Column("age_min", sa.Integer(), nullable=True, server_default=None))
        batch_op.add_column(sa.Column("age_max", sa.Integer(), nullable=True, server_default=None))

    # ============ 4. seed_invite_codes 表加 batch_no ============
    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.add_column(sa.Column("batch_no", sa.String(32), nullable=True, server_default=None))
        batch_op.create_index("ix_seed_invite_codes_batch_no", ["batch_no"])

    # ============ 5. 新表 student_verifications ============
    op.create_table(
        "student_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("note", sa.String(200), nullable=True, server_default=None),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("admin.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reject_reason", sa.String(200), nullable=True, server_default=None),
        sa.Column("granted_invite_code", sa.String(16), nullable=True, server_default=None),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("student_verifications")
    with op.batch_alter_table("seed_invite_codes") as batch_op:
        batch_op.drop_index("ix_seed_invite_codes_batch_no")
        batch_op.drop_column("batch_no")
    with op.batch_alter_table("match_queue") as batch_op:
        batch_op.drop_column("age_max")
        batch_op.drop_column("age_min")
    with op.batch_alter_table("bottles") as batch_op:
        batch_op.drop_column("author_age")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("birthday")
