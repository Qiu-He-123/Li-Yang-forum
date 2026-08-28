"""把历史数据里的微信表情代码（[微笑] 等）迁移成真实 Emoji。

用法（在 backend 目录）：
    .venv\\Scripts\\python scripts/migrate_wechat_emoji.py

只处理朋友圈相关内容：
- wechat_moments.content（朋友圈原始内容）
- posts.content 且 wechat_moment_id 不为空（已同步/已导入的帖子）
普通用户手写的帖子不做转换。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Post, WechatMoment  # noqa: E402
from app.utils.wechat_emoji import convert_wechat_emoji  # noqa: E402


def main() -> None:
    changed_moments = 0
    changed_posts = 0
    with SessionLocal() as db:
        for m in db.scalars(select(WechatMoment)).all():
            new_content = convert_wechat_emoji(m.content)
            if new_content != m.content:
                m.content = new_content
                changed_moments += 1
        for p in db.scalars(
            select(Post).where(Post.wechat_moment_id.isnot(None))
        ).all():
            new_content = convert_wechat_emoji(p.content)
            if new_content != p.content:
                p.content = new_content
                changed_posts += 1
        db.commit()
    print(f"朋友圈内容更新 {changed_moments} 条，同步帖子更新 {changed_posts} 条。")


if __name__ == "__main__":
    main()
