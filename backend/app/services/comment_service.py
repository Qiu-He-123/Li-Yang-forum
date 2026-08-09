"""评论业务逻辑层。"""
import asyncio
import json
from datetime import datetime

from fastapi import HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import Comment, Post, User
from app.schemas.interactions import CommentCreate
from app.services.ai_service import ai_service
from app.services.audit_log import log_user_action
from app.services.notification_service import create_notification


def comment_dict(comment: Comment, user: User | None) -> dict:
    """序列化评论为前端响应字典（含 user_id 用于权限判断）。"""
    from app.services.badge_service import badge_dict as _badge_dict
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "parent_id": comment.parent_id,
        "content": comment.content,
        "author": user.nickname if user else "同学",
        "author_avatar_url": user.avatar_url if user and user.avatar_url else None,
        "author_badge": _badge_dict(getattr(user, "wearing_badge", None)) if user else None,
        "user_id": comment.user_id,
        "like_count": comment.like_count,
        "ai_status": comment.ai_status,
        "reject_reason": comment.reject_reason,
        "created_at": to_iso_zh(comment.created_at),
    }


def list_comments(post_id: int, db: Session, page: int = 1, page_size: int = 20, user: User | None = None) -> dict:
    """查询帖子评论列表（按楼层分页加载）。

    改造说明：
    - 按楼层分页：先分页根评论（parent_id IS NULL），
      再把这批根评论的所有子孙回复递归查出，保证每个楼层完整返回。
    - 支持无限层级回复：C 可回复 B（B 回复了 A），D 可回复 C，以此类推。
      所有子孙评论都会归到根评论的楼层下。

    AI 审核可见性：
    - 匿名用户：只见 ai_status=approved 的评论
    - 登录用户：可见 approved；自己发的 pending/rejected 也可见

    返回 {items, total, page, page_size} 结构：
    - items: 当前页的根评论 + 其所有子孙回复，按 created_at 排序
    - total: 根评论总数（用于分页计算，回复不计入 total）
    """
    if not db.get(Post, post_id):
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)

    from sqlalchemy import func, or_

    # AI 审核可见性过滤
    if user is not None:
        ai_filter = or_(Comment.ai_status == "approved", Comment.user_id == user.id)
    else:
        ai_filter = Comment.ai_status == "approved"

    # 统计根评论总数（分页基准）
    total_count = db.scalar(
        select(func.count(Comment.id)).where(
            Comment.post_id == post_id,
            Comment.parent_id.is_(None),
            ai_filter,
        )
    ) or 0

    # 第一步：分页查询根评论
    offset = (page - 1) * page_size
    root_comments = db.scalars(
        select(Comment)
        .where(
            Comment.post_id == post_id,
            Comment.parent_id.is_(None),
            ai_filter,
        )
        .order_by(desc(Comment.created_at))
        .offset(offset)
        .limit(page_size)
    ).all()

    if not root_comments:
        return {
            "items": [],
            "total": total_count,
            "page": page,
            "page_size": page_size,
        }

    root_ids = [r.id for r in root_comments]

    # 第二步：递归查询这批根评论的所有子孙回复（支持无限层级）
    # 策略：先查出该帖所有非根评论，在 Python 中按 parent_id 建树，
    #       然后收集当前页 root_ids 的所有子孙。
    all_replies = db.scalars(
        select(Comment)
        .where(
            Comment.post_id == post_id,
            Comment.parent_id.is_not(None),
            ai_filter,
        )
        .order_by(Comment.created_at)
    ).all() if root_ids else []

    # 建立 parent_id -> children 映射
    children_map: dict[int, list[Comment]] = {}
    for reply in all_replies:
        children_map.setdefault(reply.parent_id, []).append(reply)

    # 递归收集 root_ids 的所有子孙
    def _collect_descendants(parent_ids: list[int]) -> list[Comment]:
        result: list[Comment] = []
        for pid in parent_ids:
            for child in children_map.get(pid, []):
                result.append(child)
                result.extend(_collect_descendants([child.id]))
        return result

    descendants = _collect_descendants(root_ids)

    # 合并：根评论 + 所有子孙回复，按时间排序
    all_comments = list(root_comments) + descendants

    # 查询涉及到的所有用户
    user_ids = {item.user_id for item in all_comments if item.user_id is not None}
    users = (
        {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
        if user_ids
        else {}
    )
    return {
        "items": [comment_dict(item, users.get(item.user_id)) for item in all_comments],
        "total": total_count,
        "page": page,
        "page_size": page_size,
    }


async def create_comment(post_id: int, payload: CommentCreate, request: Request, db: Session, user: User) -> dict:
    """发表评论：落库（ai_status=pending）→ 立即返回 → 后台异步审核。

    改造说明（本次功能性 bug 修复）：
    - 之前同步等待 AI 审核结果才落库，评论延迟 2-5 秒
    - 现在先落库 status=pending 立即返回，AI 审核在后台异步进行
    - 前端通过 ai_status 字段显示「AI审核中/已通过/审核失败」徽标
    - AI 不可用时直接 approved
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    if payload.parent_id and not db.get(Comment, payload.parent_id):
        raise HTTPException(status_code=404, detail=ErrorCode.PARENT_COMMENT_NOT_FOUND)

    # 封号用户禁止评论（与发帖一致，写操作必须拦截）
    from app.services import user_service
    ban_status = user_service.get_ban_status(user, db)
    if ban_status["is_banned"]:
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)

    # 审核策略：AI 可用 → 后台异步审核；AI 不可用（未开启/无余额/失败）→ 转人工审核，不直接放行
    from app.services import audit_service
    from app.services.notification_service import create_notification
    ai_available = audit_service.is_ai_audit_available(db)
    initial_ai_status = "pending" if ai_available else "manual_review"

    comment = Comment(
        post_id=post_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        content=payload.content,
        ai_status=initial_ai_status,
    )
    post.comment_count += 1
    # 更新最后回复时间
    post.last_reply_at = datetime.now()
    db.add(comment)
    db.flush()
    log_user_action(
        db,
        user.id,
        "create_comment",
        json.dumps({"comment_id": comment.id, "post_id": post_id, "parent_id": payload.parent_id}, ensure_ascii=False),
        _extract_ip(request),
    )
    # T5-5：通知帖子作者被评论（不通知自己）
    if post.author_id and post.author_id != user.id:
        content_preview = (payload.content[:30] + "...") if len(payload.content) > 30 else payload.content
        create_notification(
            db,
            post.author_id,
            "收到评论",
            f"{user.nickname} 评论了你的帖子：{content_preview}",
            ntype="comment",
            sender_id=user.id,
            reference_type="post",
            reference_id=post_id,
        )
    db.commit()
    db.refresh(comment)

    # 后台异步审核
    if initial_ai_status == "pending":
        asyncio.create_task(audit_service.audit_comment_background(comment.id))
    else:
        # AI 不可用：转人工审核并通知作者
        comment.reject_reason = "AI 审核服务暂不可用，已转人工审核"
        create_notification(
            db,
            user.id,
            "评论已进入人工审核",
            "您的评论已提交，当前进入人工审核（AI 审核服务暂不可用，未开启/无余额/调用失败）。"
            "审核可能较慢，请耐心等待。",
            ntype="system",
            reference_type="comment",
            reference_id=comment.id,
        )
        db.commit()

    # T6-6：返回 post_comment_count，前端用此值覆盖，避免前后端不一致
    return {**comment_dict(comment, user), "post_comment_count": post.comment_count}


async def _audit_comment_background(comment_id: int, content: str) -> None:
    """[已废弃] 后台异步审核评论。

    请使用 app.services.audit_service.audit_comment_background 替代。
    此函数保留仅为向后兼容，内部委托给 audit_service。
    """
    from app.services import audit_service
    await audit_service.audit_comment_background(comment_id, content)


def delete_comment(post_id: int, comment_id: int, request: Request, db: Session, user: User) -> int:
    """删除评论：权限校验 + 级联删除子回复 + 计数回滚 + 审计日志。

    Bug 修复：删除根评论时级联删除其所有回复，避免回复成为孤立数据
    导致 comment_count 与实际评论数不一致（前端显示 1 但列表为空）。

    返回: 删除后帖子的 comment_count（绝对值，供前端覆盖）
    """
    comment = db.get(Comment, comment_id)
    if not comment or comment.post_id != post_id:
        raise HTTPException(status_code=404, detail=ErrorCode.COMMENT_NOT_FOUND)
    if comment.user_id != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    post = db.get(Post, post_id)

    # 级联删除：递归删除所有子孙回复（支持无限层级）
    deleted_count = 1
    # 查出该帖所有非根评论，建立 parent_id -> children 映射
    all_replies = db.scalars(
        select(Comment).where(
            Comment.post_id == post_id,
            Comment.parent_id.is_not(None),
        )
    ).all()
    children_map: dict[int, list[Comment]] = {}
    for reply in all_replies:
        children_map.setdefault(reply.parent_id, []).append(reply)

    def _collect_descendants(parent_id: int) -> list[Comment]:
        result: list[Comment] = []
        for child in children_map.get(parent_id, []):
            result.append(child)
            result.extend(_collect_descendants(child.id))
        return result

    descendants = _collect_descendants(comment_id)
    deleted_count += len(descendants)
    for reply in descendants:
        db.delete(reply)

    # 先删除评论和子回复
    db.delete(comment)
    db.flush()  # 确保删除生效后再统计

    if post:
        # 删除后重新统计实际评论数，保证 comment_count 与数据库一致
        from sqlalchemy import func as _func
        real_count = db.scalar(select(_func.count(Comment.id)).where(Comment.post_id == post_id)) or 0
        post.comment_count = real_count
    log_user_action(db, user.id, "delete_comment", json.dumps({"comment_id": comment_id, "post_id": post_id, "cascade": deleted_count > 1, "deleted_count": deleted_count}, ensure_ascii=False), _extract_ip(request))
    db.commit()

    if post:
        db.refresh(post)
        return post.comment_count
    return 0


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip

        return extract_ip(request)
    except Exception:
        return None
