"""管理员业务逻辑层。

T2-2：admin_login 改用 Body 入参 + 颁发独立 admin_token Cookie。
T2-3：移除默认 admin/admin123456 后门，admin 必须通过 CLI 创建。
T7-6：所有 admin 操作日志写入 admin_id。

增强版：统计看板、内容审核、用户管理、举报处理、公告 CRUD、日志系统。
"""
import json
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.core.security import create_token, verify_password
from app.core.time_utils import beijing_today_start, now_utc, to_beijing, to_iso_zh
from app.models import (
    Admin,
    Announcement,
    Appeal,
    AuditLog,
    Badge,
    BanRecord,
    Comment,
    Image,
    LoginLog,
    Notification,
    OperationLog,
    Post,
    Report,
    User,
    UserBadge,
)
from app.schemas.interactions import AnnouncementCreate
from app.services.audit_log import log_admin_action
from app.services.auth_service import check_ip_rate_limit
from app.services.rate_limit_service import (
    check_login_locked,
    clear_login_failures,
    record_login_failure,
)


def admin_dict(admin: Admin) -> dict:
    return {"id": admin.id, "username": admin.username, "role": admin.role}


def admin_login(payload, request: Request, response: Response, db: Session) -> dict:
    """管理员登录（P0-3：IP 限流 + 失败锁定，防暴力破解）。"""
    ip = _extract_ip(request)
    lock_key = f"admin:{payload.username}"
    if check_login_locked(db, lock_key):
        raise HTTPException(status_code=429, detail=ErrorCode.LOGIN_LOCKED)
    check_ip_rate_limit(db, ip, "admin_login")

    admin = db.scalar(select(Admin).where(Admin.username == payload.username))
    if not admin or not verify_password(payload.password, admin.password_hash):
        record_login_failure(db, lock_key)
        raise HTTPException(status_code=403, detail=ErrorCode.LOGIN_FAILED)
    clear_login_failures(db, lock_key)

    settings = get_settings()
    token = create_token(str(admin.id), minutes=480)
    response.set_cookie(
        "admin_token",
        token,
        httponly=True,
        samesite="strict",
        secure=settings.env != "dev",
        max_age=480 * 60,
        path="/",
    )
    log_admin_action(
        db,
        admin.id,
        "admin_login",
        json.dumps({"username": payload.username}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return admin_dict(admin)


def admin_logout(response: Response) -> None:
    """登出管理员：清 Cookie。"""
    response.delete_cookie("admin_token", path="/")


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip
        return extract_ip(request)
    except Exception:
        return None


# ============ 统计看板 ============

def admin_stats(db: Session) -> dict:
    """管理后台首页统计数据。

    返回：
    - 核心指标：用户数、帖子数、评论数、举报数
    - 待审核数：帖子/评论 AI 审核队列
    - 今日新增：用户/帖子/评论
    - 近 7 天趋势：每天发帖数、注册数
    - 圈子分布：各圈子帖子数（前 8）
    - 举报状态分布
    """
    # 核心指标
    user_count = db.scalar(select(func.count(User.id))) or 0
    post_count = db.scalar(select(func.count(Post.id))) or 0
    comment_count = db.scalar(select(func.count(Comment.id))) or 0
    report_count = db.scalar(select(func.count(Report.id))) or 0

    # 待审核
    pending_posts = db.scalar(
        select(func.count(Post.id)).where(Post.ai_status == "pending")
    ) or 0
    pending_comments = db.scalar(
        select(func.count(Comment.id)).where(Comment.ai_status == "pending")
    ) or 0
    pending_reports = db.scalar(
        select(func.count(Report.id)).where(Report.status == "pending")
    ) or 0

    # 今日新增
    today_start = beijing_today_start()
    new_users_today = db.scalar(
        select(func.count(User.id)).where(User.created_at >= today_start)
    ) or 0
    new_posts_today = db.scalar(
        select(func.count(Post.id)).where(Post.created_at >= today_start)
    ) or 0
    new_comments_today = db.scalar(
        select(func.count(Comment.id)).where(Comment.created_at >= today_start)
    ) or 0

    # 近 7 天趋势
    trend = []
    for i in range(6, -1, -1):
        day_start = today_start - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        day_posts = db.scalar(
            select(func.count(Post.id)).where(
                Post.created_at >= day_start, Post.created_at < day_end
            )
        ) or 0
        day_users = db.scalar(
            select(func.count(User.id)).where(
                User.created_at >= day_start, User.created_at < day_end
            )
        ) or 0
        trend.append({
            "date": to_beijing(day_start).strftime("%m-%d"),
            "posts": int(day_posts),
            "users": int(day_users),
        })

    # 圈子分布（前 8）
    circle_rows = db.execute(
        select(Post.category, func.count(Post.id))
        .where(Post.is_draft.is_(False))
        .group_by(Post.category)
        .order_by(desc(func.count(Post.id)))
        .limit(8)
    ).all()
    circle_dist = [{"name": r[0], "count": int(r[1])} for r in circle_rows]

    # 举报状态分布
    report_status_rows = db.execute(
        select(Report.status, func.count(Report.id)).group_by(Report.status)
    ).all()
    report_status = {r[0]: int(r[1]) for r in report_status_rows}

    return {
        "overview": {
            "user_count": int(user_count),
            "post_count": int(post_count),
            "comment_count": int(comment_count),
            "report_count": int(report_count),
        },
        "pending": {
            "posts": int(pending_posts),
            "comments": int(pending_comments),
            "reports": int(pending_reports),
        },
        "today": {
            "new_users": int(new_users_today),
            "new_posts": int(new_posts_today),
            "new_comments": int(new_comments_today),
        },
        "trend_7d": trend,
        "circle_distribution": circle_dist,
        "report_status": report_status,
    }


# ============ 帖子管理 ============

def admin_posts(db: Session, page: int = 1, page_size: int = 20, keyword: str | None = None, ai_status: str | None = None) -> dict:
    """帖子列表（分页 + 搜索 + AI 状态过滤）。

    ai_status 支持特殊值 'audit_failed'：表示 rejected 或 manual_review（用于审核管理页）。
    """
    query = select(Post).order_by(desc(Post.created_at))
    if keyword:
        query = query.where(Post.content.contains(keyword))
    if ai_status:
        if ai_status == "audit_failed":
            query = query.where(Post.ai_status.in_(["rejected", "manual_review"]))
        else:
            query = query.where(Post.ai_status == ai_status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_post_dict(p) for p in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _post_dict(p: Post) -> dict:
    # image_urls 存的是 JSON 字符串
    try:
        image_urls = json.loads(p.image_urls) if p.image_urls else []
    except Exception:
        image_urls = []
    try:
        tags = json.loads(p.tags) if p.tags else []
    except Exception:
        tags = []
    return {
        "id": p.id,
        "title": p.title,
        "content": p.content,
        "category": p.category,
        "school": p.school.name if p.school else None,
        "author_id": p.author_id,
        "author": p.author.nickname if p.author else None,
        "author_avatar_url": p.author.avatar_url if p.author else None,
        "ai_status": p.ai_status,
        "reject_reason": p.reject_reason,
        "is_public": p.is_public,
        "is_anonymous": p.is_anonymous,
        "image_urls": image_urls,
        "tags": tags,
        "like_count": p.like_count,
        "comment_count": p.comment_count,
        "view_count": p.view_count,
        "share_count": getattr(p, "share_count", 0),
        "created_at": to_iso_zh(p.created_at),
    }


def admin_get_post_detail(post_id: int, db: Session) -> dict:
    """获取帖子完整详情（举报处理页面查看帖子详情用）。"""
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return _post_dict(post)


def admin_get_comment_detail(comment_id: int, db: Session) -> dict:
    """获取评论完整详情（举报处理页面查看评论详情用）。"""
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(status_code=404, detail="评论不存在")
    return _comment_dict(c, db)


def admin_delete_post(post_id: int, reason: str, request: Request, db: Session, admin: Admin) -> None:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="删除理由不能为空")
    # 先写通知再删除帖子（保留引用信息），通知作者删除原因
    if post.author_id:
        snippet = post.title or (post.content[:20] + ("…" if len(post.content) > 20 else "") if post.content else "")
        db.add(Notification(
            user_id=post.author_id,
            title="帖子已被删除",
            content=f"你的帖子「{snippet}」已被管理员删除。删除理由：{reason}",
            type="system",
            reference_type="post",
            reference_id=post_id,
        ))
    db.delete(post)
    # 清理该帖及其评论的关联通知（"帖子已被删除"系统通知保留）
    from app.services.notification_service import (
        cleanup_notifications_for_deleted_comments,
        cleanup_notifications_for_deleted_posts,
    )
    comment_ids = db.scalars(select(Comment.id).where(Comment.post_id == post_id)).all()
    cleanup_notifications_for_deleted_comments(db, list(comment_ids))
    cleanup_notifications_for_deleted_posts(db, post_id)
    log_admin_action(
        db, admin.id, "delete_post",
        json.dumps({"post_id": post_id, "reason": reason}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()


def admin_audit_post(post_id: int, ai_status: str, request: Request, db: Session, admin: Admin, reject_reason: str | None = None) -> dict:
    """审核帖子：设置 ai_status (approved/rejected/manual_review/pending)。

    当 ai_status=rejected 时，可携带 reject_reason，并向作者发送通知。
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    old = post.ai_status
    post.ai_status = ai_status
    if ai_status == "rejected":
        post.reject_reason = reject_reason or "内容违反社区规范"
    else:
        post.reject_reason = None
    log_admin_action(
        db, admin.id, "audit_post",
        json.dumps({"post_id": post_id, "old": old, "new": ai_status, "reject_reason": post.reject_reason}, ensure_ascii=False),
        _extract_ip(request),
    )
    # 审核未通过时发送通知给作者
    if ai_status == "rejected" and post.author_id:
        notif = Notification(
            user_id=post.author_id,
            title="帖子审核未通过",
            content=f"您的帖子「{(post.title or post.content[:20]) if post.content else ''}」未通过审核。原因：{post.reject_reason}",
            type="system",
            reference_type="post",
            reference_id=post.id,
        )
        db.add(notif)
    db.commit()
    db.refresh(post)
    # 徽章自动发放：审核通过帖子数达到阈值自动发徽章（含人工审核通过场景）
    if ai_status == "approved":
        try:
            from sqlalchemy import func as _func
            from app.services.badge_service import auto_grant_by_action
            author = db.get(User, post.author_id) if post.author_id else None
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
    return _post_dict(post)


# ============ 评论管理 ============

def admin_comments(db: Session, page: int = 1, page_size: int = 20, keyword: str | None = None, ai_status: str | None = None) -> dict:
    """评论列表（分页 + 搜索 + AI 状态过滤）。

    ai_status 支持特殊值 'audit_failed'：表示 rejected 或 manual_review（用于审核管理页）。
    """
    query = select(Comment).order_by(desc(Comment.created_at))
    if keyword:
        query = query.where(Comment.content.contains(keyword))
    if ai_status:
        if ai_status == "audit_failed":
            query = query.where(Comment.ai_status.in_(["rejected", "manual_review"]))
        else:
            query = query.where(Comment.ai_status == ai_status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_comment_dict(c, db) for c in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _comment_dict(c: Comment, db: Session) -> dict:
    author = db.get(User, c.user_id) if c.user_id else None
    return {
        "id": c.id,
        "post_id": c.post_id,
        "content": c.content,
        "user_id": c.user_id,
        "author": author.nickname if author else None,
        "ai_status": c.ai_status,
        "reject_reason": c.reject_reason,
        "like_count": c.like_count,
        "created_at": to_iso_zh(c.created_at),
    }


def admin_delete_comment(comment_id: int, request: Request, db: Session, admin: Admin) -> None:
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(status_code=404, detail="评论不存在")
    db.delete(c)
    log_admin_action(db, admin.id, "delete_comment", json.dumps({"comment_id": comment_id}, ensure_ascii=False), _extract_ip(request))
    db.commit()


def admin_audit_comment(comment_id: int, ai_status: str, request: Request, db: Session, admin: Admin, reject_reason: str | None = None) -> dict:
    """审核评论：设置 ai_status。rejected 时携带 reject_reason 并通知作者。"""
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(status_code=404, detail="评论不存在")
    old = c.ai_status
    c.ai_status = ai_status
    if ai_status == "rejected":
        c.reject_reason = reject_reason or "内容违反社区规范"
    else:
        c.reject_reason = None
    log_admin_action(
        db, admin.id, "audit_comment",
        json.dumps({"comment_id": comment_id, "old": old, "new": ai_status, "reject_reason": c.reject_reason}, ensure_ascii=False),
        _extract_ip(request),
    )
    # 审核未通过时发送通知给评论者
    if ai_status == "rejected" and c.user_id:
        notif = Notification(
            user_id=c.user_id,
            title="评论审核未通过",
            content=f"您的评论「{c.content[:30]}」未通过审核。原因：{c.reject_reason}",
            type="system",
            reference_type="comment",
            reference_id=c.id,
        )
        db.add(notif)
    db.commit()
    db.refresh(c)
    # 审核通过（且此前未通过）：帖子评论数 +1、更新最后回复时间、通知作者
    # 未通过的评论不计数不通知，避免"隐藏了但还能收到通知/计数"的假拦截
    if ai_status == "approved" and old != "approved":
        try:
            from app.services.notification_service import create_notification
            post = db.get(Post, c.post_id)
            if post:
                post.comment_count = (post.comment_count or 0) + 1
                post.last_reply_at = now_utc()
            if post and post.author_id and post.author_id != c.user_id:
                content_preview = (c.content[:30] + "...") if len(c.content) > 30 else c.content
                create_notification(
                    db,
                    post.author_id,
                    "收到评论",
                    f"你有一条新评论：{content_preview}",
                    ntype="comment",
                    sender_id=c.user_id,
                    reference_type="comment",
                    reference_id=c.id,
                )
            db.commit()
        except Exception:
            pass
    # 徽章自动发放：审核通过评论数达到阈值自动发徽章（含人工审核通过场景）
    if ai_status == "approved":
        try:
            from sqlalchemy import func as _func
            from app.services.badge_service import auto_grant_by_action
            author = db.get(User, c.user_id) if c.user_id else None
            if author:
                approved_count = db.scalar(
                    select(_func.count(Comment.id)).where(
                        Comment.user_id == c.user_id,
                        Comment.ai_status == "approved",
                    )
                ) or 0
                auto_grant_by_action(db, author, "approved_comments", int(approved_count))
        except Exception:
            pass
    return _comment_dict(c, db)


# ============ 用户管理 ============

def admin_users(db: Session, page: int = 1, page_size: int = 20, keyword: str | None = None) -> dict:
    query = select(User).order_by(desc(User.created_at))
    if keyword:
        like = f"%{keyword}%"
        query = query.where(User.nickname.contains(keyword) | User.phone.contains(like))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_user_dict(u, db) for u in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def admin_get_user_brief(user_id: int, db: Session) -> dict:
    """按用户 ID 查询简要信息（默认好友配置页输入 ID 时自动展示用户名）。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "school": u.school.name if u.school else None,
    }


def _user_dict(u: User, db: Session | None = None) -> dict:
    from app.services.badge_service import badge_dict as _badge_dict
    from app.models import UserBadge
    badge_names: list[str] = []
    if db is not None:
        rows = db.execute(
            select(Badge.name, Badge.icon).join(
                UserBadge, UserBadge.badge_id == Badge.id
            ).where(UserBadge.user_id == u.id).order_by(Badge.sort_order.asc())
        ).all()
        badge_names = [
            f"{icon} {name}" for name, icon in rows
        ]
    return {
        "id": u.id,
        "nickname": u.nickname,
        "phone": u.phone,
        "school": u.school.name if u.school else None,
        "grade": u.grade,
        "avatar_url": u.avatar_url,
        "bio": u.bio,
        "wearing_badge": _badge_dict(getattr(u, "wearing_badge", None)),
        "badge_names": badge_names,
        "is_active": u.is_active,
        "ban_until": to_iso_zh(u.ban_until) if u.ban_until else None,
        "ban_reason": u.ban_reason,
        "violation_count": u.violation_count,
        "post_count": 0,
        "following_count": u.following_count,
        "followers_count": u.followers_count,
        "created_at": to_iso_zh(u.created_at),
    }


def admin_update_user(user_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """更新用户信息（封禁/解封、修改昵称等）。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    changes = {}
    for key in ("nickname", "bio", "grade", "is_active"):
        if key in payload and getattr(u, key) != payload[key]:
            changes[key] = {"old": getattr(u, key), "new": payload[key]}
            setattr(u, key, payload[key])
    log_admin_action(
        db, admin.id, "update_user",
        json.dumps({"user_id": user_id, "changes": changes}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(u)
    return _user_dict(u, db)


# ============ 举报处理 ============

def admin_reports(db: Session, status: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    query = select(Report).order_by(desc(Report.created_at))
    if status:
        query = query.where(Report.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [admin_report_with_target(r, db) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def admin_get_report(report_id: int, db: Session) -> dict:
    """获取单条举报详情（含被举报对象快照）。"""
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="举报不存在")
    return admin_report_with_target(r, db)


def _report_dict(r: Report) -> dict:
    return {
        "id": r.id,
        "reporter_id": r.reporter_id,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "reason": r.reason,
        "ai_summary": r.ai_summary,
        "status": r.status,
        "created_at": to_iso_zh(r.created_at),
    }


def admin_report_with_target(r: Report, db: Session) -> dict:
    """举报详情（含被举报对象的内容快照，便于管理员直接查看）。"""
    data = _report_dict(r)
    target = None
    try:
        if r.target_type == "post":
            p = db.get(Post, r.target_id)
            if p:
                target = _post_dict(p)
        elif r.target_type == "comment":
            c = db.get(Comment, r.target_id)
            if c:
                target = _comment_dict(c, db)
        elif r.target_type == "user":
            u = db.get(User, r.target_id)
            if u:
                target = _user_dict(u, db)
    except Exception:
        target = None
    data["target"] = target
    # 举报人昵称
    reporter = db.get(User, r.reporter_id) if r.reporter_id else None
    data["reporter_nickname"] = reporter.nickname if reporter else None
    return data


def admin_handle_report(report_id: int, status: str, request: Request, db: Session, admin: Admin) -> dict:
    """处理举报：resolved(已处理) / dismissed(已驳回) / pending(重置)。"""
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="举报不存在")
    old = r.status
    r.status = status
    log_admin_action(
        db, admin.id, "handle_report",
        json.dumps({"report_id": report_id, "old": old, "new": status}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(r)
    return _report_dict(r)


# ============ 公告管理 ============

def admin_list_announcements(db: Session, page: int = 1, page_size: int = 20) -> dict:
    query = select(Announcement).order_by(desc(Announcement.created_at))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_ann_dict(a) for a in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _ann_dict(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "content": a.content,
        "school_id": a.school_id,
        "is_active": a.is_active,
        "created_at": to_iso_zh(a.created_at),
    }


def create_announcement(payload: AnnouncementCreate, request: Request, db: Session, admin: Admin) -> dict:
    item = Announcement(**payload.model_dump())
    db.add(item)
    log_admin_action(db, admin.id, "create_announcement", json.dumps({"title": payload.title}, ensure_ascii=False), _extract_ip(request))
    db.commit()
    db.refresh(item)
    return _ann_dict(item)


def admin_update_announcement(ann_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(status_code=404, detail="公告不存在")
    changes = {}
    for key in ("title", "content", "school_id", "is_active"):
        if key in payload and getattr(a, key) != payload[key]:
            changes[key] = {"old": getattr(a, key), "new": payload[key]}
            setattr(a, key, payload[key])
    log_admin_action(
        db, admin.id, "update_announcement",
        json.dumps({"ann_id": ann_id, "changes": changes}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(a)
    return _ann_dict(a)


def admin_delete_announcement(ann_id: int, request: Request, db: Session, admin: Admin) -> None:
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(status_code=404, detail="公告不存在")
    db.delete(a)
    log_admin_action(db, admin.id, "delete_announcement", json.dumps({"ann_id": ann_id}, ensure_ascii=False), _extract_ip(request))
    db.commit()


# ============ 日志系统 ============

def admin_logs(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    admin_id: int | None = None,
    action: str | None = None,
) -> dict:
    """管理员操作日志（分页 + 过滤）。"""
    query = select(OperationLog).where(OperationLog.admin_id.is_not(None))
    if admin_id:
        query = query.where(OperationLog.admin_id == admin_id)
    if action:
        query = query.where(OperationLog.action == action)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(desc(OperationLog.created_at)).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_oplog_dict(item) for item in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def admin_user_logs(
    user_id: int | None,
    action: str | None,
    db: Session,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """用户操作日志（分页 + 过滤）。"""
    query = select(OperationLog).where(OperationLog.user_id.is_not(None))
    if user_id is not None:
        query = query.where(OperationLog.user_id == user_id)
    if action:
        query = query.where(OperationLog.action == action)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(desc(OperationLog.created_at)).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_oplog_dict(item) for item in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _oplog_dict(item: OperationLog) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "admin_id": item.admin_id,
        "action": item.action,
        "detail": item.detail,
        "ip": item.ip,
        "created_at": to_iso_zh(item.created_at),
    }


def admin_login_logs(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    user_id: int | None = None,
    success: bool | None = None,
) -> dict:
    """用户登录日志（分页 + 过滤）。"""
    query = select(LoginLog)
    if user_id is not None:
        query = query.where(LoginLog.user_id == user_id)
    if success is not None:
        query = query.where(LoginLog.success.is_(success))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(desc(LoginLog.created_at)).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "phone": item.phone,
                "ip": item.ip,
                "device": item.device,
                "success": item.success,
                "created_at": to_iso_zh(item.created_at),
            }
            for item in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ============ 图片人工审核（图片不走 AI 审核） ============

def admin_list_images(
    db: Session,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict:
    """图片审核列表（分页 + 状态过滤 + 使用统计）。"""
    query = select(Image).order_by(desc(Image.created_at))
    if status in ("pending", "approved", "rejected"):
        query = query.where(Image.audit_status == status)
    if keyword:
        query = query.where(Image.url.contains(keyword))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    user_ids = list({r.user_id for r in rows if r.user_id})
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}

    counts = {s: 0 for s in ("pending", "approved", "rejected")}
    for row in db.execute(
        select(Image.audit_status, func.count(Image.id)).group_by(Image.audit_status)
    ).all():
        if row[0] in counts:
            counts[row[0]] = int(row[1])

    items = []
    for img in rows:
        used_in_posts = db.scalar(
            select(func.count(Post.id)).where(Post.image_urls.like(f"%{img.url}%"))
        ) or 0
        items.append({
            "id": img.id,
            "url": img.url,
            "mime_type": img.mime_type,
            "size_bytes": img.size_bytes,
            "is_private": img.is_private,
            "audit_status": img.audit_status,
            "user_id": img.user_id,
            "user_nickname": users.get(img.user_id).nickname if img.user_id and users.get(img.user_id) else None,
            "used_in_posts": int(used_in_posts),
            "created_at": to_iso_zh(img.created_at),
        })
    return {
        "items": items,
        "total": int(total),
        "counts": counts,
        "page": page,
        "page_size": page_size,
    }


def admin_review_image(
    db: Session,
    admin: Admin,
    image_id: int,
    action: str,
    reject_reason: str | None = None,
) -> dict:
    """人工审核图片（图片不走 AI 审核）。

    - approve: 标记通过；相关因「图片需人工审核」而挂起的帖子自动放行
    - reject:  标记驳回；相关帖子标记为 rejected 并通知作者
    """
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="图片不存在")
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="审核动作仅支持 approve / reject")

    old = img.audit_status
    img.audit_status = "approved" if action == "approve" else "rejected"

    related_posts = db.scalars(
        select(Post).where(
            Post.image_urls.like(f"%{img.url}%"),
            Post.is_draft.is_(False),
        )
    ).all()
    for post in related_posts:
        if action == "approve" and post.ai_status == "manual_review":
            post.ai_status = "approved"
            post.reject_reason = None
            db.add(
                Notification(
                    user_id=post.author_id,
                    title="帖子已通过人工审核",
                    content="您帖子中的图片已通过人工审核，帖子已正常发布。",
                    type="system",
                    reference_type="post",
                    reference_id=post.id,
                )
            )
        elif action == "reject" and post.ai_status in ("manual_review", "pending"):
            post.ai_status = "rejected"
            reason = (reject_reason or "图片未通过人工审核").strip()
            post.reject_reason = f"图片未通过人工审核：{reason}"[:200]
            db.add(
                Notification(
                    user_id=post.author_id,
                    title="帖子未通过人工审核",
                    content=f"您帖子中的图片未通过人工审核（{reason}），帖子暂未发布。请更换图片后重新发布。",
                    type="system",
                    reference_type="post",
                    reference_id=post.id,
                )
            )

    log_admin_action(
        db,
        admin.id,
        "review_image",
        json.dumps({
            "image_id": image_id,
            "old": old,
            "new": img.audit_status,
            "related_posts": [p.id for p in related_posts],
            "reject_reason": reject_reason or "",
        }, ensure_ascii=False),
        None,
    )
    db.commit()
    return {
        "id": img.id,
        "url": img.url,
        "audit_status": img.audit_status,
        "related_posts": [p.id for p in related_posts],
    }


# ============ 系统设置 ============

def admin_list_settings(db: Session) -> list[dict]:
    """列出所有系统设置项。"""
    from app.services import settings_service
    return settings_service.list_settings(db)


def admin_update_settings(payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """批量更新系统设置。payload: {"settings": {"key": "value", ...}}"""
    from app.services import settings_service
    items = payload.get("settings", {}) if payload else {}
    if not items:
        raise HTTPException(status_code=400, detail="settings 不能为空")
    settings_service.set_many(db, items)
    log_admin_action(
        db, admin.id, "update_settings",
        json.dumps({"keys": list(items.keys())}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return {"updated": list(items.keys())}


def admin_get_deepseek_config(db: Session) -> dict:
    """读取 DeepSeek 配置（脱敏）。"""
    from app.services import settings_service
    cfg = settings_service.get_deepseek_config(db)
    return {
        "enabled": cfg["enabled"],
        "api_key": cfg["api_key"],  # 管理员后台需要回显，前端不再二次脱敏
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "auto_delete_days": cfg["auto_delete_days"],
        "audit_scope": cfg["audit_scope"],
        "manual_review_triggers": cfg["manual_review_triggers"],
    }


def admin_update_deepseek_config(payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """更新 DeepSeek 配置。"""
    from app.services import settings_service
    settings_service.update_deepseek_config(db, payload or {})
    log_admin_action(
        db, admin.id, "update_deepseek_config",
        json.dumps({"keys": list((payload or {}).keys())}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return admin_get_deepseek_config(db)


# ============ 审核失败内容自动清理 ============

def admin_cleanup_expired_audit(db: Session, request: Request | None = None, admin: Admin | None = None) -> dict:
    """清理超过自动删除天数且仍为 rejected 状态的帖子/评论。

    读取 settings.audit_auto_delete_days：
    - 0 表示不自动删除
    - N 表示删除 N 天前 ai_status=rejected 的内容
    """
    from app.services import settings_service
    days = settings_service.get_int(db, "audit_auto_delete_days", 0)
    if days <= 0:
        return {"enabled": False, "days": days, "deleted_posts": 0, "deleted_comments": 0}

    threshold = now_utc() - timedelta(days=days)
    # 删除过期且仍为 rejected 的帖子
    old_posts = db.scalars(
        select(Post).where(Post.ai_status == "rejected", Post.created_at < threshold)
    ).all()
    for p in old_posts:
        db.delete(p)
    # 删除过期且仍为 rejected 的评论
    old_comments = db.scalars(
        select(Comment).where(Comment.ai_status == "rejected", Comment.created_at < threshold)
    ).all()
    for c in old_comments:
        db.delete(c)

    deleted_posts = len(old_posts)
    deleted_comments = len(old_comments)

    if admin is not None and request is not None:
        log_admin_action(
            db, admin.id, "cleanup_expired_audit",
            json.dumps({"days": days, "deleted_posts": deleted_posts, "deleted_comments": deleted_comments}, ensure_ascii=False),
            _extract_ip(request),
        )
    db.commit()
    return {"enabled": True, "days": days, "deleted_posts": deleted_posts, "deleted_comments": deleted_comments}


# ============ 封号管理 ============


def _ban_record_dict(r: BanRecord, db: Session) -> dict:
    user = db.get(User, r.user_id) if r.user_id else None
    admin = db.get(Admin, r.admin_id) if r.admin_id else None
    return {
        "id": r.id,
        "user_id": r.user_id,
        "user_nickname": user.nickname if user else None,
        "user_phone": user.phone if user else None,
        "admin_id": r.admin_id,
        "admin_name": admin.username if admin else None,
        "reason": r.reason,
        "duration_hours": r.duration_hours,
        "ban_until": to_iso_zh(r.ban_until) if r.ban_until else None,
        "banned_at": to_iso_zh(r.banned_at),
        "unbanned_at": to_iso_zh(r.unbanned_at) if r.unbanned_at else None,
        "status": r.status,
        "appealable": r.appealable,
    }


def admin_ban_user(user_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """封禁用户。

    payload:
    - reason: 封禁原因（必填）
    - duration_hours: 封禁时长（小时），0=警告不封禁，-1=永久封禁。不传则根据警告值阈值自动判定
    - appealable: 是否允许申诉（默认 True）

    新机制：管理员手动封号时同步增加警告值并记录到 warning_logs，
    未指定 duration_hours 时按警告值阈值（warn/temp_ban/perm_ban）自动判定封号等级。
    """
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")

    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="请填写封禁原因")

    # 增加警告值（管理员手动封号视为一次违规）
    from app.services import warning_service
    cfg = warning_service.get_warning_config(db)
    old_score = u.warning_score or 0
    warning_service.add_warning_score(
        db, u, cfg.violation_base_score,
        reason=f"管理员封号：{reason[:150]}",
        source="violation",
        operator_id=admin.id,
    )
    score_after = u.warning_score

    # 确定封禁时长
    if "duration_hours" in payload:
        duration_hours = int(payload["duration_hours"])
        # 管理员显式指定封号时长时，同步抬升 warning_score 到对应阈值，
        # 保证 DB 状态与封号提示页"已达 X 阈值"文案一致，避免显示 0/100 误导
        if duration_hours == -1 and score_after < cfg.perm_ban_threshold:
            delta = cfg.perm_ban_threshold - score_after
            warning_service.add_warning_score(
                db, u, delta,
                reason=f"管理员永久封号：{reason[:150]}",
                source="violation",
                operator_id=admin.id,
            )
            score_after = u.warning_score
        elif duration_hours > 0 and score_after < cfg.temp_ban_threshold:
            delta = cfg.temp_ban_threshold - score_after
            warning_service.add_warning_score(
                db, u, delta,
                reason=f"管理员临时封号：{reason[:150]}",
                source="violation",
                operator_id=admin.id,
            )
            score_after = u.warning_score
    else:
        # 根据警告值阈值自动判定
        if score_after >= cfg.perm_ban_threshold:
            duration_hours = -1  # 永久封禁
        elif score_after >= cfg.temp_ban_threshold:
            duration_hours = cfg.temp_ban_hours  # 临时封号
        else:
            duration_hours = 0  # 仅警告，不封禁

    appealable = payload.get("appealable", True)

    if duration_hours == 0:
        # 仅警告，不封禁，但记录违规
        ban_until = None
        u.is_active = True  # 保持活跃
        u.ban_until = None
        u.ban_reason = None
        record_status = "expired"  # 警告记录直接标记为 expired
    elif duration_hours == -1:
        # 永久封禁
        ban_until = None
        u.is_active = False
        u.ban_until = None
        u.ban_reason = reason
        record_status = "active"
    else:
        # 时长封禁
        ban_until = now_utc() + timedelta(hours=duration_hours)
        u.is_active = False
        u.ban_until = ban_until
        u.ban_reason = reason
        record_status = "active"

    record = BanRecord(
        user_id=user_id,
        admin_id=admin.id,
        reason=reason,
        duration_hours=duration_hours if duration_hours > 0 else 0,
        ban_until=ban_until,
        status=record_status,
        appealable=appealable,
    )
    db.add(record)

    # 发送通知（采用警告值表述）
    if duration_hours == 0:
        notif_title = "违规警告"
        notif_content = (
            f"您的内容违反社区规范。原因：{reason}。\n"
            f"您的警告值已变为 {score_after}，"
            f"达到 {cfg.temp_ban_threshold} 将被封号 {cfg.temp_ban_hours} 小时，"
            f"达到 {cfg.perm_ban_threshold} 将被永久封号。\n\n"
            f"保持良好社区行为（签到、发帖等）可减少警告值。"
        )
    elif duration_hours == -1:
        notif_title = "账号已被永久封禁"
        notif_content = (
            f"您的警告值已达到 {score_after}（永久封号阈值 {cfg.perm_ban_threshold}），"
            f"账号已被永久封禁。原因：{reason}。如有异议可提交申诉。"
        )
    else:
        days = duration_hours // 24
        hours = duration_hours % 24
        period = f"{days}天" if days else f"{hours}小时"
        notif_title = f"账号已被封禁 {period}"
        notif_content = (
            f"您的警告值已达到 {score_after}（临时封号阈值 {cfg.temp_ban_threshold}），"
            f"账号已被封禁 {period}。原因：{reason}。\n"
            f"解封时间：{to_iso_zh(ban_until) if ban_until else '永久'}。\n"
            f"达到 {cfg.perm_ban_threshold} 将永久封号。\n\n"
            f"保持良好社区行为（签到、发帖等）可减少警告值。如有异议可提交申诉。"
        )

    notif = Notification(
        user_id=user_id,
        title=notif_title,
        content=notif_content,
        type="system",
    )
    db.add(notif)

    log_admin_action(
        db, admin.id, "ban_user",
        json.dumps({"user_id": user_id, "reason": reason, "duration_hours": duration_hours, "warning_score": score_after, "old_score": old_score}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(record)
    return _ban_record_dict(record, db)


def admin_unban_user(user_id: int, request: Request, db: Session, admin: Admin) -> dict:
    """手动解封用户：撤销当前生效的封禁记录，恢复账号。"""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 撤销所有 active 封禁记录
    active_records = db.scalars(
        select(BanRecord).where(BanRecord.user_id == user_id, BanRecord.status == "active")
    ).all()
    for r in active_records:
        r.status = "revoked"
        r.unbanned_at = now_utc()

    u.is_active = True
    u.ban_until = None
    u.ban_reason = None

    notif = Notification(
        user_id=user_id,
        title="账号已解封",
        content="您的账号已被管理员解封，请遵守社区规范。",
        type="system",
    )
    db.add(notif)

    log_admin_action(
        db, admin.id, "unban_user",
        json.dumps({"user_id": user_id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(u)
    return _user_dict(u, db)


def admin_ban_records(db: Session, page: int = 1, page_size: int = 20, user_id: int | None = None, status: str | None = None) -> dict:
    """封号记录列表（分页 + 过滤）。"""
    query = select(BanRecord).order_by(desc(BanRecord.banned_at))
    if user_id:
        query = query.where(BanRecord.user_id == user_id)
    if status:
        query = query.where(BanRecord.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_ban_record_dict(r, db) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ============ 申诉管理 ============

def _appeal_dict(a: Appeal, db: Session) -> dict:
    user = db.get(User, a.user_id) if a.user_id else None
    admin = db.get(Admin, a.reviewed_by) if a.reviewed_by else None
    return {
        "id": a.id,
        "user_id": a.user_id,
        "user_nickname": user.nickname if user else None,
        "ban_record_id": a.ban_record_id,
        "reason": a.reason,
        "status": a.status,
        "reviewed_by": a.reviewed_by,
        "reviewer_name": admin.username if admin else None,
        "reviewed_at": to_iso_zh(a.reviewed_at) if a.reviewed_at else None,
        "review_comment": a.review_comment,
        "created_at": to_iso_zh(a.created_at),
    }


def admin_appeals(db: Session, page: int = 1, page_size: int = 20, status: str | None = None) -> dict:
    """申诉列表（分页 + 状态过滤）。"""
    query = select(Appeal).order_by(desc(Appeal.created_at))
    if status:
        query = query.where(Appeal.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_appeal_dict(a, db) for a in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def admin_review_appeal(appeal_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """审核申诉：approved（申诉成功，解封）/ rejected（驳回）。

    payload:
    - status: approved / rejected
    - review_comment: 审核回复
    """
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="申诉不存在")
    if appeal.status != "pending":
        raise HTTPException(status_code=400, detail="该申诉已处理")

    new_status = payload.get("status", "rejected")
    review_comment = payload.get("review_comment", "")

    appeal.status = new_status
    appeal.reviewed_by = admin.id
    appeal.reviewed_at = now_utc()
    appeal.review_comment = review_comment

    # 申诉成功：解封用户
    if new_status == "approved":
        u = db.get(User, appeal.user_id)
        if u:
            # 撤销 active 封禁记录
            active_records = db.scalars(
                select(BanRecord).where(BanRecord.user_id == appeal.user_id, BanRecord.status == "active")
            ).all()
            for r in active_records:
                r.status = "revoked"
                r.unbanned_at = now_utc()
            u.is_active = True
            u.ban_until = None
            u.ban_reason = None

            notif = Notification(
                user_id=appeal.user_id,
                title="申诉成功，账号已解封",
                content=f"您的申诉已通过审核，账号已解封。审核回复：{review_comment or '无'}",
                type="system",
            )
            db.add(notif)
    else:
        # 申诉驳回：通知用户
        notif = Notification(
            user_id=appeal.user_id,
            title="申诉未通过",
            content=f"您的申诉未通过审核。审核回复：{review_comment or '无'}",
            type="system",
        )
        db.add(notif)

    log_admin_action(
        db, admin.id, "review_appeal",
        json.dumps({"appeal_id": appeal_id, "status": new_status, "review_comment": review_comment}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(appeal)
    return _appeal_dict(appeal, db)


# ============ AI 审核日志 ============

def _audit_log_dict(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "user_id": log.user_id,
        "ai_provider": log.ai_provider,
        "result": log.result,
        "reason": log.reason,
        "category": log.category,
        "severity": log.severity,
        "content_snapshot": log.content_snapshot,
        "created_at": to_iso_zh(log.created_at),
    }


def admin_audit_logs(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    target_type: str | None = None,
    result: str | None = None,
    user_id: int | None = None,
    category: str | None = None,
    severity: str | None = None,
) -> dict:
    """AI 审核日志列表（分页 + 过滤）。"""
    from app.models import AuditLog as _AuditLog
    query = select(_AuditLog).order_by(desc(_AuditLog.created_at))
    if target_type:
        query = query.where(_AuditLog.target_type == target_type)
    if result:
        query = query.where(_AuditLog.result == result)
    if user_id:
        query = query.where(_AuditLog.user_id == user_id)
    if category:
        query = query.where(_AuditLog.category == category)
    if severity:
        query = query.where(_AuditLog.severity == severity)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_audit_log_dict(log) for log in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
