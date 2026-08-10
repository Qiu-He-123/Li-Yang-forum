"""AI 内容审核统一服务。

集中处理：
- 判断 AI 审核是否可用（DeepSeek 或 OpenAI 任一可用即可）
- 执行审核并记录 AuditLog
- 审核失败时发送通知给作者
- 警告值累计与警告/封号触发（委托 warning_service）

设计要点：
- 发帖/发评论均先落库 ai_status=pending，立即返回
- 后台异步审核：优先 DeepSeek，回退 OpenAI
- 审核结果写入 audit_logs 表（管理端可查看 AI 审核日志）
- 违规时：通过 warning_service.handle_violation 增加警告值，达到阈值自动警告/封号
- 审核通过时：通过 warning_service.reduce_on_* 减少警告值（积极行为奖励）
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.time_utils import now_utc
from app.models import AuditLog, Notification, Post, Comment, User
from app.services import ai_service, deepseek_service, settings_service


# ============ 审核范围 / 人工复核触发条件 ============

# 可选的审核内容范围
AUDIT_SCOPE_KEYS = ("post", "comment", "bottle", "image")

# 可选的转人工复核触发条件
MANUAL_REVIEW_TRIGGER_KEYS = ("ai_unavailable", "violation", "high_severity", "sensitive_category")

# AI 判定为这些类别时属于高敏感内容（涉及未成年人保护 / 法律风险），建议强制人工复核
SENSITIVE_CATEGORIES = {
    "政治敏感",
    "色情低俗",
    "暴力血腥",
    "违法犯罪",
    "校园欺凌",
    "自残自杀",
    "隐私泄露",
}


def is_ai_audit_available(db: Session) -> bool:
    """检查是否有任一 AI 审核服务可用（DeepSeek 或 OpenAI）。

    之前只检查 OpenAI，导致仅配置 DeepSeek 时审核被跳过。
    """
    # 1. 检查 DeepSeek
    try:
        ds_cfg = settings_service.get_deepseek_config(db)
        if ds_cfg["enabled"] and ds_cfg["api_key"]:
            return True
    except Exception:
        pass
    # 2. 检查 OpenAI
    try:
        if ai_service.get_status()["available"]:
            return True
    except Exception:
        pass
    return False


def should_route_violation_to_manual(db: Session, audit: dict[str, Any]) -> bool:
    """AI 判定违规后，是否转人工复核（而非直接按违规处理）。

    触发条件（任一命中即转人工复核）：
    - violation：AI 判定违规即保留内容转人工复核
    - high_severity：AI 判定 high / medium 严重度
    - sensitive_category：涉及敏感类别
    """
    triggers = settings_service.get_manual_review_triggers(db)
    if "violation" in triggers:
        return True
    if "high_severity" in triggers and audit.get("severity") in ("high", "medium"):
        return True
    if "sensitive_category" in triggers and audit.get("category") in SENSITIVE_CATEGORIES:
        return True
    return False


def _run_audit(db: Session, content: str, content_type: str = "generic") -> dict[str, Any]:
    """执行 AI 审核（同步），返回统一结果。

    Args:
        content_type: post（帖子）/ comment（评论）/ bottle（漂流瓶）/ generic（通用）

    返回:
        {
            "pass": bool,
            "reason": str,
            "category": str,      # none/politics/porn/abuse/ad/spam
            "severity": str,      # none/low/medium/high
            "provider": str,      # deepseek/openai/none
        }
    """
    # 优先 DeepSeek
    try:
        ds_cfg = settings_service.get_deepseek_config(db)
        if ds_cfg["enabled"] and ds_cfg["api_key"]:
            ds_result = deepseek_service.audit_content(db, content, content_type)
            if not ds_result.get("skipped"):
                return {
                    "pass": ds_result.get("pass", True),
                    "reason": ds_result.get("reason", ""),
                    "category": ds_result.get("category", "none"),
                    "severity": ds_result.get("severity", "none"),
                    "provider": "deepseek",
                }
    except Exception:
        pass

    # 回退 OpenAI（异步接口，但此处用 asyncio.run 无法在已有事件循环中调用）
    # 在后台审核场景中，调用方已经处于 async 上下文，应直接 await ai_service.check_text
    # 此同步函数仅用于 DeepSeek 不可用时的降级判断
    return {
        "pass": False,
        "reason": "AI 审核服务不可用，已转人工审核",
        "category": "none",
        "severity": "none",
        "provider": "none",
        "skipped": True,
    }


async def run_audit_async(content: str, content_type: str = "generic") -> dict[str, Any]:
    """异步执行 AI 审核：优先 DeepSeek，回退 OpenAI。

    Args:
        content_type: post（帖子）/ comment（评论）/ bottle（漂流瓶）/ generic（通用）

    重要：DeepSeek 的 audit_content 是同步阻塞调用（httpx.Client），
    直接在事件循环中调用会阻塞所有请求。必须用 asyncio.to_thread
    把它放到独立线程池中执行，避免阻塞主事件循环。
    """
    import asyncio

    # 优先 DeepSeek（同步调用 → 放到线程池）
    try:
        def _run_deepseek():
            with SessionLocal() as db:
                ds_cfg = settings_service.get_deepseek_config(db)
                if ds_cfg["enabled"] and ds_cfg["api_key"]:
                    return deepseek_service.audit_content(db, content, content_type)
            return None

        ds_result = await asyncio.to_thread(_run_deepseek)
        if ds_result and not ds_result.get("skipped"):
            return {
                "pass": ds_result.get("pass", True),
                "reason": ds_result.get("reason", ""),
                "category": ds_result.get("category", "none"),
                "severity": ds_result.get("severity", "none"),
                "provider": "deepseek",
            }
    except Exception:
        pass

    # 回退 OpenAI
    try:
        audit = await ai_service.check_text(content)
        return {
            "pass": audit.get("pass", True),
            "reason": audit.get("reason", ""),
            "category": "none",
            "severity": "none",
            "provider": "openai",
        }
    except Exception:
        pass

    # 两者都不可用 → 不直接放行，转人工审核
    return {
        "pass": False,
        "reason": "AI 审核服务不可用，已转人工审核",
        "category": "none",
        "severity": "none",
        "provider": "none",
        "skipped": True,
    }


def _record_audit_log(
    db: Session,
    target_type: str,
    target_id: int,
    user_id: int | None,
    audit: dict[str, Any],
    content: str,
) -> None:
    """写入 AI 审核日志。"""
    try:
        result = "approved" if audit.get("pass", True) else (
            "error" if audit.get("skipped") else "rejected"
        )
        log = AuditLog(
            target_type=target_type,
            target_id=target_id,
            user_id=user_id,
            ai_provider=audit.get("provider", "none"),
            result=result,
            reason=audit.get("reason", "")[:500],
            category=audit.get("category", "none"),
            severity=audit.get("severity", "none"),
            content_snapshot=content[:500],
        )
        db.add(log)
    except Exception:
        pass


def _send_manual_review_notification(
    db: Session,
    user_id: int,
    target_type: str,
    target_id: int,
    reason: str = "AI 审核服务暂不可用，已转人工审核",
) -> None:
    """内容进入人工审核时通知作者（AI 开不起了/图片需人工审核）。"""
    label = "帖子" if target_type == "post" else "评论"
    try:
        db.add(
            Notification(
                user_id=user_id,
                title=f"{label}已进入人工审核",
                content=f"您的{label}已提交，当前进入人工审核（{reason}）。"
                        f"审核可能较慢，请耐心等待，审核结果会第一时间通知您。",
                type="system",
                reference_type=target_type,
                reference_id=target_id,
            )
        )
    except Exception:
        pass


def record_audit_log(
    db: Session,
    target_type: str,
    target_id: int,
    user_id: int | None,
    audit: dict[str, Any],
    content: str,
) -> None:
    """公开的审核日志写入入口（供帖子/评论/漂流瓶审核统一调用）。"""
    _record_audit_log(db, target_type, target_id, user_id, audit, content)


def _handle_violation(db: Session, user_id: int, target_type: str, target_id: int, reason: str, content_preview: str = "", severity: str = "medium") -> None:
    """处理违规：增加警告值 + 阈值判定 + 发通知/封号。

    新机制（警告值系统）：
    - 每次违规 warning_score += violation_base_score（可根据 severity 调整）
    - 警告值 >= warn_threshold: 发警告通知
    - 警告值 >= temp_ban_threshold: 封号 temp_ban_hours 小时
    - 警告值 >= perm_ban_threshold: 永久封号

    通知文案采用警告值表述（不再说"第 X 次违规"）：
    1. 第一条：内容审核未通过通知（关联到具体帖子/评论）
    2. 第二条：警告/封号通知（告知警告值变为 X，达到 Y 将封号 Z）
    """
    from app.services import warning_service

    user = db.get(User, user_id)
    if not user:
        return

    warning_service.handle_violation(
        db, user, reason=reason, content_preview=content_preview,
        target_type=target_type, target_id=target_id,
        severity=severity,
    )


def _send_reject_notification(
    db: Session,
    user_id: int,
    target_type: str,
    target_id: int,
    content_preview: str,
    reason: str,
) -> None:
    """审核未通过但未触发封号/警告时（违规次数为 0 或本次未累计）发送通知。

    注意：当前 _handle_violation 已合并发送审核未通过 + 警告/封号通知，
    本函数仅作为保底使用。如果 _handle_violation 已被调用，本函数不应再次调用。
    """
    notif = Notification(
        user_id=user_id,
        title=f"{'帖子' if target_type == 'post' else '评论'}审核未通过",
        content=f"您发布的{'帖子' if target_type == 'post' else '评论'}「{content_preview}」未通过 AI 审核。"
                f"原因：{reason}。请修改后重新发布。",
        type="system",
        reference_type=target_type,
        reference_id=target_id,
    )
    db.add(notif)


async def audit_post_background(post_id: int) -> None:
    """后台异步审核帖子：执行 AI 审核 → 更新状态 → 记录日志 → 发送通知 → 处理违规。

    状态流转：
    - AI 通过  → ai_status=approved + 生成标签
    - AI 违规  → ai_status=rejected + reject_reason + 累计违规（合并通知，仅发一条）
    - AI 不可用 → ai_status=manual_review（不直接放行，转入人工审核）
    """
    try:
        with SessionLocal() as db:
            post = db.get(Post, post_id)
            if not post:
                return
            # 标题 + 内容一起审核（标题也要过审核）
            title_part = f"标题：{post.title}\n" if post.title else ""
            content = f"{title_part}内容：{post.content}"
            audit = await run_audit_async(content, "post")

            # 写入审核日志
            _record_audit_log(db, "post", post_id, post.author_id, audit, content)

            if audit.get("skipped"):
                if settings_service.is_manual_review_trigger_enabled(db, "ai_unavailable"):
                    # AI 不可用/调用失败 → 不直接放行，转人工审核
                    post.ai_status = "manual_review"
                    post.reject_reason = "AI 审核服务不可用，已转人工审核"
                    _send_manual_review_notification(
                        db, post.author_id, "post", post.id,
                        reason="AI 审核服务暂不可用（未开启/无余额/调用失败）",
                    )
                else:
                    # 管理员配置：AI 不可用时直接放行（免审兜底）
                    post.ai_status = "approved"
                    post.reject_reason = None
            elif audit.get("pass", True):
                post.ai_status = "approved"
                post.reject_reason = None
                # 徽章自动发放：审核通过帖子数达到阈值自动发徽章
                try:
                    from sqlalchemy import func as _func
                    from app.services.badge_service import auto_grant_by_action
                    author = db.get(User, post.author_id)
                    if author:
                        approved_count = db.scalar(
                            select(_func.count(Post.id)).where(
                                Post.author_id == post.author_id,
                                Post.ai_status == "approved",
                            )
                        ) or 0
                        auto_grant_by_action(db, author, "approved_posts", int(approved_count))
                except Exception:
                    pass
                # 生成标签（仅 OpenAI 路径有标签生成能力）
                if audit.get("provider") == "openai":
                    try:
                        tags = await ai_service.generate_tags(post.content)
                        if tags:
                            post.tags = json.dumps(tags, ensure_ascii=False)
                    except Exception:
                        pass
                # 帖子审核通过：减少作者警告值（积极行为奖励）
                try:
                    from app.services import warning_service
                    author = db.get(User, post.author_id)
                    if author:
                        warning_service.reduce_on_post_approved(db, author, post.id)
                except Exception:
                    pass
            else:
                # AI 判定违规
                reason = audit.get("reason", "内容违反社区规范")
                if should_route_violation_to_manual(db, audit):
                    # 命中人工复核触发条件：保留内容，转人工复核，不自动累计警告
                    post.ai_status = "manual_review"
                    post.reject_reason = f"AI 判定违规，已转人工复核：{reason}"
                    _send_manual_review_notification(
                        db, post.author_id, "post", post.id,
                        reason="AI 判定内容违规，待人工复核",
                    )
                else:
                    post.ai_status = "rejected"
                    post.reject_reason = reason

                    # 处理违规（增加警告值 + 阈值判定 + 通知/封号）
                    content_preview = (post.title or post.content or "")[:30]
                    severity = audit.get("severity", "medium")
                    _handle_violation(db, post.author_id, "post", post.id, reason, content_preview, severity=severity)

            db.commit()
    except Exception as exc:
        from loguru import logger
        logger.warning("[AI_AUDIT] post {} audit failed: {}", post_id, exc)
        try:
            with SessionLocal() as db:
                post = db.get(Post, post_id)
                if post:
                    post.ai_status = "manual_review"
                    post.reject_reason = "AI 审核服务不可用，已转人工审核"
                    db.commit()
        except Exception:
            pass


async def audit_comment_background(comment_id: int) -> None:
    """后台异步审核评论：执行 AI 审核 → 更新状态 → 记录日志 → 发送通知 → 处理违规。

    状态流转同 audit_post_background。
    """
    try:
        with SessionLocal() as db:
            comment = db.get(Comment, comment_id)
            if not comment:
                return
            audit = await run_audit_async(comment.content, "comment")

            # 写入审核日志
            _record_audit_log(db, "comment", comment_id, comment.user_id, audit, comment.content)

            if audit.get("skipped"):
                if settings_service.is_manual_review_trigger_enabled(db, "ai_unavailable"):
                    comment.ai_status = "manual_review"
                    comment.reject_reason = "AI 审核服务不可用，已转人工审核"
                    _send_manual_review_notification(
                        db, comment.user_id, "comment", comment.id,
                        reason="AI 审核服务暂不可用（未开启/无余额/调用失败）",
                    )
                else:
                    # 管理员配置：AI 不可用时直接放行
                    comment.ai_status = "approved"
                    comment.reject_reason = None
            elif audit.get("pass", True):
                comment.ai_status = "approved"
                comment.reject_reason = None
                # 审核通过：帖子评论数 +1、更新最后回复时间、通知作者（未通过前不计数不通知）
                try:
                    from app.models import Post as _Post
                    post = db.get(_Post, comment.post_id)
                    if post:
                        post.comment_count = (post.comment_count or 0) + 1
                        post.last_reply_at = now_utc()
                    if post and post.author_id and post.author_id != comment.user_id:
                        content_preview = (comment.content[:30] + "...") if len(comment.content) > 30 else comment.content
                        create_notification(
                            db,
                            post.author_id,
                            "收到评论",
                            f"你有一条新评论：{content_preview}",
                            ntype="comment",
                            sender_id=comment.user_id,
                            reference_type="comment",
                            reference_id=comment.id,
                        )
                except Exception:
                    pass
                # 徽章自动发放：审核通过评论数达到阈值自动发徽章
                try:
                    from sqlalchemy import func as _func
                    from app.services.badge_service import auto_grant_by_action
                    author = db.get(User, comment.user_id)
                    if author:
                        approved_count = db.scalar(
                            select(_func.count(Comment.id)).where(
                                Comment.user_id == comment.user_id,
                                Comment.ai_status == "approved",
                            )
                        ) or 0
                        auto_grant_by_action(db, author, "approved_comments", int(approved_count))
                except Exception:
                    pass
                # 评论审核通过：减少作者警告值（积极行为奖励）
                try:
                    from app.services import warning_service
                    author = db.get(User, comment.user_id)
                    if author:
                        warning_service.reduce_on_comment_approved(db, author, comment.id)
                except Exception:
                    pass
            else:
                reason = audit.get("reason", "内容违反社区规范")
                if should_route_violation_to_manual(db, audit):
                    # 命中人工复核触发条件：保留内容，转人工复核，不自动累计警告
                    comment.ai_status = "manual_review"
                    comment.reject_reason = f"AI 判定违规，已转人工复核：{reason}"
                    _send_manual_review_notification(
                        db, comment.user_id, "comment", comment.id,
                        reason="AI 判定内容违规，待人工复核",
                    )
                else:
                    comment.ai_status = "rejected"
                    comment.reject_reason = reason

                    # 处理违规（增加警告值 + 阈值判定 + 通知/封号）
                    content_preview = (comment.content or "")[:30]
                    severity = audit.get("severity", "medium")
                    _handle_violation(db, comment.user_id, "comment", comment.id, reason, content_preview, severity=severity)

            db.commit()
    except Exception as exc:
        from loguru import logger
        logger.warning("[AI_AUDIT] comment {} audit failed: {}", comment_id, exc)
        try:
            with SessionLocal() as db:
                comment = db.get(Comment, comment_id)
                if comment:
                    comment.ai_status = "manual_review"
                    comment.reject_reason = "AI 审核服务不可用，已转人工审核"
                    db.commit()
        except Exception:
            pass
