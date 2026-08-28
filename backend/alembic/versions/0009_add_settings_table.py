"""Add settings table for admin-configurable system settings.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27

新增表：
- settings  系统设置表（key-value 结构）

用于存储管理员可通过后台修改的配置，例如：
- deepseek_api_key: DeepSeek API 密钥
- deepseek_base_url: DeepSeek API 基础 URL
- deepseek_model: DeepSeek 模型名
- deepseek_enabled: 是否启用 DeepSeek 审核
- audit_auto_delete_days: 审核失败内容自动删除天数
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.create_table(
            "settings",
            sa.Column("key", sa.String(length=64), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("description", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        )
    except Exception:
        pass  # 表已存在

    # 写入默认配置项
    try:
        op.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES "
                   "('deepseek_enabled', 'false', '是否启用 DeepSeek AI 审核')")
        op.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES "
                   "('deepseek_api_key', '', 'DeepSeek API 密钥')")
        op.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES "
                   "('deepseek_base_url', 'https://api.deepseek.com/v1', 'DeepSeek API 基础 URL')")
        op.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES "
                   "('deepseek_model', 'deepseek-chat', 'DeepSeek 模型名')")
        op.execute("INSERT OR IGNORE INTO settings (key, value, description) VALUES "
                   "('audit_auto_delete_days', '0', '审核失败内容自动删除天数（0=不自动删除）')")
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_table("settings")
    except Exception:
        pass
