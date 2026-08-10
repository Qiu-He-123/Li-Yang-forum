"""评论业务逻辑层。"""
import asyncio
import json

from fastapi import HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import ErrorCode
from app.core.time_utils import now_utc, to_iso_zh
from app.models import Comment, Post, User
from app.schemas.interactions import CommentCreate
from app.services.ai_service import ai_service
from app.services.audit_log import log_user_action
from app.services import explore_service
from app.services.notification_service import cleanup_notifications_for_deleted_comments, create_notification


def comment_dict(comment: Comment, user: User | None, explored: bool = False) -> dict:
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
        "explored": bool(explored),
        "created_at": to_iso_zh(comment.created_at),
    }


def list_comments(
    post_id: int,
    db: Session,
    page: int = 1,
    page_size: int = 20,
    user: User | None = None,
    sort: str = "latest",
) -> dict:
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

    # 第一步：分页查询根评论（最新 / 最热两种排序）
    offset = (page - 1) * page_size
    root_query = (
        select(Comment)
        .where(
            Comment.post_id == post_id,
            Comment.parent_id.is_(None),
            ai_filter,
        )
        .offset(offset)
        .limit(page_size)
    )
    if sort == "hot":
        root_query = root_query.order_by(desc(Comment.like_count), desc(Comment.created_at))
    else:
        root_query = root_query.order_by(desc(Comment.created_at))
    root_comments = list(db.scalars(root_query).all())

    # ============ 评论探索：最热排序首页按比例插入低赞新评论 ============
    explored_comment_ids: set[int] = set()
    if sort == "hot" and page == 1:
        try:
            cfg = explore_service.get_explore_config(db)
            if cfg["comment_explore_enabled"]:
                slots = explore_service.explore_slot_count(page_size, cfg["comment_explore_rate"])
                if slots > 0 and root_comments:
                    # 保留最热的前 N 条，其余槽位从「低赞新评论」探索池补充
                    keep_count = max(0, len(root_comments) - slots)
                    hot_ids = {c.id for c in root_comments[:keep_count]}
                    pool = explore_service.pick_explore_comments(
                        db,
                        post_id,
                        slots,
                        cfg,
                        exclude_ids=hot_ids,
                    )
                    if not pool:
                        # 评论总数不足一页时，直接用当前页尾部的低赞评论作为探索位
                        tail = [
                            c for c in root_comments[keep_count:]
                            if (c.like_count or 0) <= 3
                        ]
                        pool = tail[:slots]
                    if pool:
                        root_comments = explore_service.merge_explore(
                            root_comments[: max(0, len(root_comments) - len(pool))],
                            pool,
                            user,
                            page,
                        )
                        explored_comment_ids = {c.id for c in pool}
                        # 只写曝光日志（track_stats=False），避免评论曝光计入帖子统计
                        explore_service.record_feed_impressions(
                            db,
                            [post_id] * len(pool),
                            user.id if user else None,
                            explore_service.SCENE_COMMENT,
                            page,
                            track_stats=False,
                            target_ids=[c.id for c in pool],
                        )
        except Exception as exc:  # noqa: BLE001
            from loguru import logger
            logger.warning("[EXPLORE] list_comments explore failed: {}", exc)
            try:
                db.rollback()
            except Exception:
                pass

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
        "items": [
            comment_dict(
                item,
                users.get(item.user_id),
                explored=item.id in explored_comment_ids,
            )
            for item in all_comments
        ],
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

    # 审核策略（受后台「AI 审核配置 - 审核范围 / 人工复核触发」控制）：
    # - 未开启 comment 范围 → 评论免审，直接放行
    # - 开启且 AI 可用 → 后台异步审核（pending）
    # - 开启且 AI 不可用 → 开启 ai_unavailable 触发则转人工审核，否则直接放行
    from app.services import audit_service, settings_service
    from app.services.notification_service import create_notification
    scope = settings_service.get_audit_scope(db)
    triggers = settings_service.get_manual_review_triggers(db)
    if "comment" not in scope:
        initial_ai_status = "approved"
    elif audit_service.is_ai_audit_available(db):
        initial_ai_status = "pending"
    elif "ai_unavailable" in triggers:
        initial_ai_status = "manual_review"
    else:
        initial_ai_status = "approved"

    comment = Comment(
        post_id=post_id,
        user_id=user.id,
        parent_id=payload.parent_id,
        content=payload.content,
        ai_status=initial_ai_status,
    )
    # 评论审核通过前不计数、不更新最后回复时间（未通过的评论只是"隐藏"而非真拦截）
    # 计数与作者通知统一在审核通过时进行（见 audit_comment_background / admin_audit_comment）
    db.add(comment)
    db.flush()
    log_user_action(
        db,
        user.id,
        "create_comment",
        json.dumps({"comment_id": comment.id, "post_id": post_id, "parent_id": payload.parent_id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(comment)
    # 探索奖励归因：该用户近期在探索位看过这篇帖子，评论计入探索互动
    explore_service.record_interaction(db, post_id, user.id, "comment")

    # 后台异步审核
    if initial_ai_status == "pending":
        asyncio.create_task(audit_service.audit_comment_background(comment.id))
    elif initial_ai_status == "approved":
        # 免审评论立即生效：同步帖子评论数、最后回复时间并通知作者
        post.comment_count = (post.comment_count or 0) + 1
        post.last_reply_at = now_utc()
        if post.author_id and post.author_id != user.id:
            content_preview = (comment.content[:30] + "...") if len(comment.content) > 30 else comment.content
            create_notification(
                db,
                post.author_id,
                "收到评论",
                f"你有一条新评论：{content_preview}",
                ntype="comment",
                sender_id=user.id,
                reference_type="comment",
                reference_id=comment.id,
            )
        db.commit()
        db.refresh(comment)
    elif initial_ai_status == "manual_review":
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

    # T6-6：返回已审核通过的评论数（审核中的评论不计入），前端用此值覆盖
    from sqlalchemy import func as _func
    approved_count = db.scalar(
        select(_func.count(Comment.id)).where(
            Comment.post_id == post_id,
            Comment.ai_status == "approved",
        )
    ) or 0
    return {**comment_dict(comment, user), "post_comment_count": int(approved_count)}


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

    # 同步清理关联通知（被评论人/被回复人不再看到已删除评论的消息）
    deleted_ids = [comment_id] + [r.id for r in descendants]
    cleanup_notifications_for_deleted_comments(db, deleted_ids)

    if post:
        # 删除后重新统计"已审核通过"的评论数（审核中的不计入），
        # 保证 comment_count 与真实可见评论一致
        from sqlalchemy import func as _func
        real_count = db.scalar(
            select(_func.count(Comment.id)).where(
                Comment.post_id == post_id,
                Comment.ai_status == "approved",
            )
        ) or 0
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
