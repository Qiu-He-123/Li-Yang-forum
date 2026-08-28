"""0056 求助帖功能字段

新增：
- posts.reward_coins     求助帖悬赏金币（求助区必填）
- posts.is_solved        求助帖是否已解决
- posts.best_comment_id  求助帖最佳回复评论 id
- posts.solved_at        解决时间
- comments.is_best       评论是否被楼主选为最佳回复
- comments.best_at       被选为最佳回复的时间
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 注意：SQLite 不支持 ALTER TABLE 添加外键约束，best_comment_id 仅加列，
    # 外键关系由 ORM 模型（Post.best_comment_id → comments.id）声明与维护。
    op.add_column("posts", sa.Column("reward_coins", sa.Integer, nullable=True, index=True))
    op.add_column("posts", sa.Column("is_solved", sa.Boolean, nullable=False, server_default="0", index=True))
    op.add_column("posts", sa.Column("best_comment_id", sa.Integer, nullable=True))
    op.add_column("posts", sa.Column("solved_at", sa.DateTime, nullable=True))

    op.add_column("comments", sa.Column("is_best", sa.Boolean, nullable=False, server_default="0", index=True))
    op.add_column("comments", sa.Column("best_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("posts", "solved_at")
    op.drop_column("posts", "best_comment_id")
    op.drop_column("posts", "is_solved")
    op.drop_column("posts", "reward_coins")

    op.drop_column("comments", "best_at")
    op.drop_column("comments", "is_best")
