"""点赞 / 收藏 / 举报 业务逻辑层。

注意：
- 点赞/收藏使用 db.flush() 而非 db.commit()，先 flush 成功后才更新 count，
  避免 IntegrityError 时 count 已 +1 但 rollback 不回滚的旧 Bug（L1/L2/D2）。
"""
import json

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.models import Comment, Favorite, Like, Post, Report, User
from app.schemas.interactions import ReportCreate
from app.services.ai_service import ai_service
from app.services.audit_log import log_user_action
from app.services import explore_service
from app.services.notification_service import create_notification


def like_target(target_type: str, target_id: int, request: Request, db: Session, user: User) -> dict:
    """点赞。重复点赞返回当前 count，不抛错。"""
    if target_type not in {"post", "comment"}:
        raise HTTPException(status_code=400, detail=ErrorCode.INVALID_LIKE_TARGET)
    target = db.get(Post if target_type == "post" else Comment, target_id)
    if not target:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    db.add(Like(user_id=user.id, target_type=target_type, target_id=target_id))
    try:
        db.flush()
        # flush 成功（无 IntegrityError）后才更新 count，避免 rollback 后 count 多 +1
        target.like_count += 1
        log_user_action(db, user.id, "like", json.dumps({"target_type": target_type, "target_id": target_id}, ensure_ascii=False), _extract_ip(request))
        # T5-5：通知帖子/评论作者被点赞（不通知自己）
        recipient_id = target.author_id if target_type == "post" else target.user_id
        if recipient_id and recipient_id != user.id:
            content_preview = (target.content[:30] + "...") if len(target.content) > 30 else target.content
            create_notification(
                db, recipient_id,
                f"收到点赞",
                f"{user.nickname} 赞了你的{('帖子' if target_type == 'post' else '评论')}：{content_preview}",
                ntype="like",
                sender_id=user.id,
                reference_type=target_type,
                reference_id=target_id,
            )
        db.commit()
        # 探索奖励归因：该用户近期在探索位看过这个帖子，点赞计入探索互动
        if target_type == "post":
            explore_service.record_interaction(db, target_id, user.id, "like")
        # 徽章自动发放：帖子获赞总数达到规则阈值自动发徽章
        if target_type == "post":
            try:
                from sqlalchemy import func as _func
                from app.services.badge_service import auto_grant_by_action
                author = db.get(User, target.author_id)
                if author:
                    likes = db.scalar(
                        select(_func.count(Like.id))
                        .join(Post, Post.id == Like.target_id)
                        .where(Post.author_id == target.author_id, Like.target_type == "post")
                    ) or 0
                    auto_grant_by_action(db, author, "likes_received", int(likes))
            except Exception:
                pass
    except IntegrityError:
        # 重复点赞：回滚 Like.add，但 target.like_count 已 +1 需还原
        db.rollback()
        target = db.get(Post if target_type == "post" else Comment, target_id)
    return {"like_count": target.like_count if target else 0}


def unlike_target(target_type: str, target_id: int, request: Request, db: Session, user: User) -> dict:
    """取消点赞。"""
    target = db.get(Post if target_type == "post" else Comment, target_id) if target_type in {"post", "comment"} else None
    if not target:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    result = db.execute(
        delete(Like).where(Like.user_id == user.id, Like.target_type == target_type, Like.target_id == target_id)
    )
    if result.rowcount and target.like_count > 0:
        target.like_count -= 1
    log_user_action(db, user.id, "unlike", json.dumps({"target_type": target_type, "target_id": target_id}, ensure_ascii=False), _extract_ip(request))
    db.commit()
    return {"like_count": target.like_count}


def favorite_post(post_id: int, request: Request, db: Session, user: User) -> None:
    """收藏帖子。重复收藏幂等返回。"""
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    db.add(Favorite(user_id=user.id, post_id=post_id))
    try:
        db.flush()
        log_user_action(db, user.id, "favorite", json.dumps({"post_id": post_id}, ensure_ascii=False), _extract_ip(request))
        # T5-5：通知帖子作者被收藏
        if post.author_id and post.author_id != user.id:
            content_preview = (post.content[:30] + "...") if len(post.content) > 30 else post.content
            create_notification(
                db, post.author_id, "收到收藏", f"{user.nickname} 收藏了你的帖子：{content_preview}",
                ntype="interaction",
                sender_id=user.id,
                reference_type="post",
                reference_id=post_id,
            )
        db.commit()
    except IntegrityError:
        db.rollback()


def unfavorite_post(post_id: int, request: Request, db: Session, user: User) -> None:
    """取消收藏。"""
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.post_id == post_id))
    log_user_action(db, user.id, "unfavorite", json.dumps({"post_id": post_id}, ensure_ascii=False), _extract_ip(request))
    db.commit()


async def create_report(payload: ReportCreate, request: Request, db: Session, user: User) -> dict:
    """创建举报：落库 + AI 摘要 + 审计日志。"""
    model = {"post": Post, "comment": Comment, "user": User}[payload.target_type]
    if not db.get(model, payload.target_id):
        raise HTTPException(status_code=404, detail=ErrorCode.REPORT_TARGET_NOT_FOUND)
    summary = await ai_service.summary(payload.reason)
    report = Report(
        reporter_id=user.id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        ai_summary=summary or "AI 摘要暂不可用",
    )
    db.add(report)
    db.flush()
    log_user_action(
        db,
        user.id,
        "report",
        json.dumps({"report_id": report.id, "target_type": payload.target_type, "target_id": payload.target_id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(report)
    return {"id": report.id, "status": report.status, "ai_summary": report.ai_summary}


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip

        return extract_ip(request)
    except Exception:
        return None
