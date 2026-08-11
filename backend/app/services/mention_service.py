"""帖子 @ 提及业务逻辑层（阶段二）。

负责解析帖子内容中的 @昵称、创建 Mention 记录、给被@用户发通知。
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.avatar import avatar_url_or_default
from app.models import Mention, User
from app.services import notification_service


# 匹配 @昵称（昵称支持中文/英文/数字/下划线，1-32 字符）
_MENTION_PATTERN = re.compile(r"@([\w\u4e00-\u9fa5]{1,32})")


def extract_mentions(content: str, explicit_ids: list[int], db: Session) -> list[int]:
    """从内容中解析 @昵称，结合显式传入的 user_ids，去重返回。

    Args:
        content: 帖子内容
        explicit_ids: 前端显式传入的被@用户 id 列表
        db: Session

    Returns:
        去重后的用户 id 列表（不含不存在的用户）
    """
    ids: set[int] = set()
    # 1. 显式传入的 id
    for uid in explicit_ids or []:
        if uid and uid > 0:
            ids.add(uid)
    # 2. 从内容解析 @昵称
    if content:
        nicknames = set(_MENTION_PATTERN.findall(content))
        if nicknames:
            # 批量查询存在的用户 id
            rows = db.scalars(select(User.id).where(User.nickname.in_(nicknames))).all()
            for uid in rows:
                ids.add(uid)
    return list(ids)


def create_mentions(db: Session, post_id: int, mentioned_user_ids: list[int]) -> None:
    """为帖子批量创建 Mention 记录（不 commit，已存在则跳过）。

    Args:
        db: Session
        post_id: 帖子 id
        mentioned_user_ids: 被@用户 id 列表
    """
    if not mentioned_user_ids:
        return
    # 查询已存在的 Mention，避免重复插入
    existing = set(
        db.scalars(
            select(Mention.mentioned_user_id).where(
                Mention.post_id == post_id,
                Mention.mentioned_user_id.in_(mentioned_user_ids),
            )
        ).all()
    )
    for uid in mentioned_user_ids:
        if uid in existing:
            continue
        db.add(Mention(post_id=post_id, mentioned_user_id=uid))


def send_mention_notifications(
    db: Session,
    post_id: int,
    mentioned_user_ids: list[int],
    from_user_id: int,
) -> None:
    """给被@用户发送 type='mention' 通知（不 commit）。

    Args:
        db: Session
        post_id: 帖子 id
        mentioned_user_ids: 被@用户 id 列表
        from_user_id: 发起 @ 的用户 id（帖子作者）
    """
    if not mentioned_user_ids:
        return
    # 取作者昵称（用于通知文案）
    from_user = db.get(User, from_user_id)
    from_name = from_user.nickname if from_user else "有人"
    for uid in mentioned_user_ids:
        notification_service.create_notification(
            db,
            user_id=uid,
            title="@提及了你",
            content=f"{from_name} 在帖子里 @ 了你",
            ntype="mention",
            sender_id=from_user_id,
            reference_type="post",
            reference_id=post_id,
        )


def list_mentioned_users(db: Session, post_id: int) -> list[dict]:
    """返回帖子 @ 的用户列表（前端展示用）。"""
    rows = db.scalars(
        select(User)
        .join(Mention, Mention.mentioned_user_id == User.id)
        .where(Mention.post_id == post_id)
    ).all()
    return [
        {
            "id": u.id,
            "nickname": u.nickname,
            "avatar_url": avatar_url_or_default(u.avatar_url),
        }
        for u in rows
    ]
