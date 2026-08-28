"""wechat bind verify flow

Revision ID: 0038

- wechat_bindings：新增 verify_code / verify_code_expires_at / status（pending -> verified）
  绑定改为分步：先查好友生成验证码，用户把验证码发给社区微信号，后台读到消息后才 verified
- wechat_recent_messages：客户端定期上报"收到的最近消息"，供验证码校验
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0038"
down_revision: str = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wechat_bindings", sa.Column("verify_code", sa.String(length=16), nullable=True))
    op.add_column("wechat_bindings", sa.Column("verify_code_expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "wechat_bindings",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.create_table(
        "wechat_recent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("peer_wxid", sa.String(length=64), nullable=False),
        sa.Column("last_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_time", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wechat_recent_messages_peer_wxid", "wechat_recent_messages", ["peer_wxid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_wechat_recent_messages_peer_wxid", table_name="wechat_recent_messages")
    op.drop_table("wechat_recent_messages")
    op.drop_column("wechat_bindings", "status")
    op.drop_column("wechat_bindings", "verify_code_expires_at")
    op.drop_column("wechat_bindings", "verify_code")
