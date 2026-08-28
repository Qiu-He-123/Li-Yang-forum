"""0057 游戏中心（赚金币小游戏）

新增：
- games 表：游戏元信息 + 每局金币奖励 + 每日上限 + 用户自制游戏（html_content）
- 种子数据：内置 6 款宠物小游戏 + 6 款 tufang HTML 小游戏
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def _seed_games(bind) -> None:
    """幂等写入内置游戏（按 slug 判断已存在则跳过）。"""
    games = [
        # 宠物内置小游戏（前端 PetPlay.vue 原生实现）
        ("接零食", "catch", "single", "左右移动接住落下的零食，喂饱小馋猫！", "🍖", 5, 5, 1),
        ("戳泡泡", "bubble", "single", "泡泡浮起来啦，快点戳爆它们！", "🫧", 5, 5, 2),
        ("记忆翻牌", "memory", "single", "翻出所有配对的图案，考验记忆力！", "🧠", 5, 5, 3),
        ("猜拳", "rps", "single", "和宠物石头剪刀布，三局两胜！", "✊", 5, 5, 4),
        ("幸运轮", "wheel", "single", "转一转，赢好感大礼包！", "🎡", 5, 5, 5),
        ("打地鼠", "mole", "single", "小地鼠冒头啦，快敲它脑袋！", "🐹", 5, 5, 6),
        # tufang-games 移植的 HTML 小游戏（前端 public/games 提供）
        ("2048", "game-2048", "single", "经典数字合成，合并方块冲击 2048！", "🔢", 5, 5, 7),
        ("打砖块", "game-breakout", "single", "移动挡板反弹小球，清空所有砖块！", "🧱", 5, 5, 8),
        ("像素鸟", "game-flappy", "single", "点击屏幕让小鸟飞越管道，越远越强！", "🐦", 5, 5, 9),
        ("反应测试", "game-reaction", "single", "屏幕变绿瞬间点击，考验你的反应速度！", "⚡", 5, 5, 10),
        ("贪吃蛇", "game-snake", "single", "经典贪吃蛇，吃下食物越长越长！", "🐍", 5, 5, 11),
        ("俄罗斯方块", "game-tetris", "single", "经典方块消除，消除整行拿高分！", "🧩", 5, 5, 12),
        ("连连看", "game-match", "single", "找出所有配对的图案，眼力大考验！", "🎴", 5, 5, 13),
        ("记忆大师", "game-memory", "single", "记住图案位置，翻开所有配对！", "🧠", 5, 5, 14),
        ("扫雷", "game-minesweeper", "single", "推理避开所有地雷，经典益智游戏！", "💣", 5, 5, 15),
        ("数独", "game-sudoku", "single", "填入 1-9 让每行每列都不重复！", "🔢", 5, 5, 16),
        ("极速打地鼠", "game-whack", "single", "地鼠疯狂冒头，限时敲打拿高分！", "🔨", 5, 5, 17),
    ]
    result = bind.execute(sa.text("SELECT slug FROM games"))
    existing = {row[0] for row in result.fetchall()}
    for name, slug, gtype, desc, icon, reward, daily, sort_order in games:
        if slug in existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO games "
                "(name, slug, type, description, icon_url, reward_coins, daily_limit, "
                "is_active, sort_order, source, status, created_at, updated_at) "
                "VALUES (:name, :slug, :type, :desc, :icon, :reward, :daily, 1, :sort, "
                "'builtin', 'active', datetime('now'), datetime('now'))"
            ),
            {
                "name": name,
                "slug": slug,
                "type": gtype,
                "desc": desc,
                "icon": icon,
                "reward": reward,
                "daily": daily,
                "sort": sort_order,
            },
        )


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, index=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("type", sa.String(20), nullable=False, server_default="single", index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon_url", sa.String(255), nullable=True),
        sa.Column("reward_coins", sa.Integer, nullable=False, server_default="5"),
        sa.Column("daily_limit", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1", index=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="builtin"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("html_content", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    bind = op.get_bind()
    _seed_games(bind)


def downgrade() -> None:
    op.drop_table("games")
