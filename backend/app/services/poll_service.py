"""投票业务逻辑层（阶段二）。

负责投票、查询投票详情、检查截止投票并通知发起人。
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Poll, PollOption, PollVote, Post, User
from app.services import notification_service


def create_poll_for_post(
    db: Session,
    post_id: int,
    title: str,
    multi_vote: bool,
    deadline: datetime | None,
    options: list[str],
) -> Poll:
    """为帖子创建投票 + 选项（不 commit，由调用方提交）。

    Args:
        db: Session
        post_id: 帖子 id
        title: 投票标题
        multi_vote: 是否允许多选
        deadline: 截止时间（可选）
        options: 选项内容列表（2-6 个）

    Returns:
        Poll 实例
    """
    poll = Poll(
        post_id=post_id,
        title=title,
        multi_vote=multi_vote,
        deadline=deadline,
    )
    db.add(poll)
    db.flush()
    for content in options:
        db.add(PollOption(poll_id=poll.id, content=content, vote_count=0))
    db.flush()
    return poll


def _poll_dict(
    db: Session,
    poll: Poll,
    user: User | None = None,
) -> dict:
    """序列化投票为前端响应字典。

    Args:
        db: Session
        poll: Poll 实例
        user: 当前用户（用于判断是否已投票）

    Returns:
        包含 user_voted / is_expired 字段的投票详情字典
    """
    options = db.scalars(
        select(PollOption).where(PollOption.poll_id == poll.id).order_by(PollOption.id)
    ).all()
    # 当前用户已投的选项 id
    voted_option_ids: set[int] = set()
    if user is not None:
        voted = db.scalars(
            select(PollVote.option_id).where(
                PollVote.user_id == user.id,
                PollVote.option_id.in_([o.id for o in options]),
            )
        ).all()
        voted_option_ids = set(voted)
    total_votes = sum(o.vote_count for o in options)
    # 是否已截止
    is_expired = poll.deadline is not None and datetime.utcnow() > poll.deadline
    return {
        "id": poll.id,
        "post_id": poll.post_id,
        "title": poll.title,
        "multi_vote": poll.multi_vote,
        "deadline": to_iso_zh(poll.deadline),
        "total_votes": total_votes,
        "user_voted": len(voted_option_ids) > 0,
        "is_expired": is_expired,
        "options": [
            {
                "id": o.id,
                "content": o.content,
                "vote_count": o.vote_count,
                "voted": o.id in voted_option_ids,
            }
            for o in options
        ],
        "created_at": to_iso_zh(poll.created_at),
    }


def get_poll_detail(db: Session, post_id: int, user: User | None = None) -> dict | None:
    """获取投票详情（含选项、投票数、当前用户是否已投）。

    Args:
        db: Session
        post_id: 帖子 id
        user: 当前用户（可选）

    Returns:
        投票详情字典；不存在返回 None
    """
    poll = db.scalar(select(Poll).where(Poll.post_id == post_id))
    if not poll:
        return None
    return _poll_dict(db, poll, user=user)


def vote(db: Session, user: User, post_id: int, option_ids: list[int]) -> dict:
    """用户对帖子关联的投票进行投票（支持单选/多选）。

    规则：
    - 帖子必须存在且有关联投票
    - 选项必须属于该帖子的投票
    - 投票必须未截止
    - multi_vote=False 时：option_ids 仅取第一个；用户已投过任意选项则 400
    - multi_vote=True 时：允许提交多个选项；同一选项重复投票由唯一约束兜底
    - 同一选项重复投票由 UniqueConstraint 拦截（返回 409）

    Args:
        db: Session
        user: 当前用户
        post_id: 帖子 id
        option_ids: 选项 id 列表

    Returns:
        投票后的投票详情字典
    """
    poll = db.scalar(select(Poll).where(Poll.post_id == post_id))
    if not poll:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    # 截止校验
    if poll.deadline is not None and datetime.utcnow() > poll.deadline:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    # 获取该投票的所有选项 id
    poll_option_ids = set(
        db.scalars(select(PollOption.id).where(PollOption.poll_id == poll.id)).all()
    )
    # 校验选项归属
    invalid = [oid for oid in option_ids if oid not in poll_option_ids]
    if invalid:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    # 单选模式：只取第一个；检查是否已投过
    if not poll.multi_vote:
        existing = db.scalar(
            select(PollVote).where(
                PollVote.user_id == user.id,
                PollVote.option_id.in_(poll_option_ids),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
        option_ids = option_ids[:1]
    # 写入投票记录
    for oid in option_ids:
        option = db.get(PollOption, oid)
        if option is None:
            continue
        # 检查是否已投过该选项（多选模式下避免重复）
        already = db.scalar(
            select(PollVote).where(
                PollVote.user_id == user.id,
                PollVote.option_id == oid,
            )
        )
        if already is not None:
            continue
        db.add(PollVote(option_id=oid, user_id=user.id))
        option.vote_count = (option.vote_count or 0) + 1
    db.commit()
    db.refresh(poll)
    return _poll_dict(db, poll, user=user)


def check_deadline_and_notify(db: Session) -> None:
    """检查截止的投票，给发起人发 type='vote_end' 通知。

    注意：本函数为幂等设计，但当前实现仅按 deadline <= now 过滤，
    调用方需自行保证不重复发送（如用 scheduled task 周期调用）。
    实际生产应增加 is_notified 字段避免重复，此处简化处理。
    """
    now = datetime.utcnow()
    polls = db.scalars(
        select(Poll).where(Poll.deadline.is_not(None), Poll.deadline <= now)
    ).all()
    for poll in polls:
        # 取帖子作者
        post = db.get(Post, poll.post_id)
        if not post:
            continue
        # 统计总票数
        options = db.scalars(
            select(PollOption).where(PollOption.poll_id == poll.id)
        ).all()
        total = sum(o.vote_count for o in options)
        notification_service.create_notification(
            db,
            user_id=post.author_id,
            title="投票已结束",
            content=f"你的投票「{poll.title}」已截止，共收到 {total} 票",
            ntype="vote_end",
            sender_id=None,
            reference_type="post",
            reference_id=post.id,
        )
    if polls:
        db.commit()
