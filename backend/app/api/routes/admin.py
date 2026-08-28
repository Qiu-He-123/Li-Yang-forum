import io
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from PIL import Image as PILImage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import admin_user
from app.core.database import get_db
from app.models import Admin
from app.schemas.auth import AdminLoginIn
from app.schemas.common import ok
from app.schemas.interactions import AnnouncementCreate
from app.services import activity_service, admin_service, badge_service, circle_apply_service, explore_service, guess_service, pet_shop_service

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminDeletePostIn(BaseModel):
    reason: str


@router.post("/login")
def admin_login(payload: AdminLoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """管理员登录。"""
    return ok(admin_service.admin_login(payload, request, response, db))


@router.post("/logout")
def admin_logout(response: Response, _: Admin = Depends(admin_user)) -> dict:
    """管理员登出，清 admin_token Cookie。"""
    admin_service.admin_logout(response)
    return ok()


# ============ 统计看板 ============

@router.get("/stats")
def admin_stats(db: Session = Depends(get_db), _: Admin = Depends(admin_user)) -> dict:
    """管理后台首页统计数据。"""
    return ok(admin_service.admin_stats(db))


@router.get("/pending-counts")
def admin_pending_counts(db: Session = Depends(get_db), _: Admin = Depends(admin_user)) -> dict:
    """后台各待处理事项数量（侧边栏红点提醒）。"""
    return ok(admin_service.admin_pending_counts(db))


# ============ 帖子管理 ============

@router.get("/posts")
def admin_posts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    ai_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """帖子列表（分页 + 搜索 + AI 状态过滤）。"""
    return ok(admin_service.admin_posts(db, page, page_size, keyword, ai_status))


@router.post("/posts/{post_id}/delete")
def admin_delete_post(post_id: int, payload: AdminDeletePostIn, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(admin_user)) -> dict:
    """管理员删除帖子（需提供删除理由，并通知作者）。"""
    admin_service.admin_delete_post(post_id, payload.reason, request, db, admin)
    return ok()


# ============ 组局管理 ============

@router.get("/gatherings")
def admin_gatherings_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(recruiting|cancelled|ended)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """组局列表（分页 + 标题/描述搜索 + 状态过滤，含已取消/已结束）。"""
    return ok(admin_service.admin_gatherings(db, page, page_size, keyword, status))


@router.post("/gatherings/{gathering_id}/delete")
def admin_delete_gathering(
    gathering_id: int,
    payload: AdminDeletePostIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """管理员删除组局（需提供删除理由，并通知发起人与参与者）。"""
    admin_service.admin_delete_gathering(gathering_id, payload.reason, request, db, admin)
    return ok()


@router.patch("/posts/{post_id}/audit")
def admin_audit_post(
    post_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """审核帖子：ai_status (approved/rejected/manual_review/pending)，rejected 可携带 reject_reason。"""
    return ok(admin_service.admin_audit_post(
        post_id, payload.get("ai_status", "approved"), request, db, admin,
        reject_reason=payload.get("reject_reason"),
    ))


# ============ 评论管理 ============

@router.get("/comments")
def admin_comments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    ai_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """评论列表（分页 + 搜索 + AI 状态过滤）。"""
    return ok(admin_service.admin_comments(db, page, page_size, keyword, ai_status))


@router.delete("/comments/{comment_id}")
def admin_delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(admin_user)) -> dict:
    """删除评论。"""
    admin_service.admin_delete_comment(comment_id, request, db, admin)
    return ok()


@router.patch("/comments/{comment_id}/audit")
def admin_audit_comment(
    comment_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """审核评论：ai_status (approved/rejected/manual_review/pending)，rejected 可携带 reject_reason。"""
    return ok(admin_service.admin_audit_comment(
        comment_id, payload.get("ai_status", "approved"), request, db, admin,
        reject_reason=payload.get("reject_reason"),
    ))


# ============ 用户管理 ============

@router.get("/users")
def admin_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """用户列表（分页 + 搜索）。"""
    return ok(admin_service.admin_users(db, page, page_size, keyword))


@router.get("/users/{user_id}")
def admin_get_user_brief(
    user_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """按用户 ID 查询简要信息（默认好友配置用）。"""
    return ok(admin_service.admin_get_user_brief(user_id, db))


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """更新用户（封禁/解封、修改昵称等）。"""
    return ok(admin_service.admin_update_user(user_id, payload, request, db, admin))


# ============ 举报处理 ============

@router.get("/reports")
def admin_reports(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """举报列表（分页 + 状态过滤）。"""
    return ok(admin_service.admin_reports(db, status, page, page_size))


@router.patch("/reports/{report_id}")
def admin_handle_report(
    report_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """处理举报：status (resolved/dismissed/pending)。"""
    return ok(admin_service.admin_handle_report(report_id, payload.get("status", "resolved"), request, db, admin))


@router.get("/reports/{report_id}")
def admin_get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """获取单条举报详情（含被举报对象快照）。"""
    return ok(admin_service.admin_get_report(report_id, db))


@router.get("/posts/{post_id}")
def admin_get_post(
    post_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """获取帖子完整详情（举报处理/审核管理查看详情用）。"""
    return ok(admin_service.admin_get_post_detail(post_id, db))


@router.get("/comments/{comment_id}")
def admin_get_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """获取评论完整详情。"""
    return ok(admin_service.admin_get_comment_detail(comment_id, db))


# ============ 公告管理 ============

@router.get("/announcements")
def admin_list_announcements(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """公告列表（分页）。"""
    return ok(admin_service.admin_list_announcements(db, page, page_size))


@router.post("/announcements")
def create_announcement(payload: AnnouncementCreate, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(admin_user)) -> dict:
    """创建公告。"""
    return ok(admin_service.create_announcement(payload, request, db, admin))


@router.patch("/announcements/{ann_id}")
def admin_update_announcement(
    ann_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """更新公告。"""
    return ok(admin_service.admin_update_announcement(ann_id, payload, request, db, admin))


@router.delete("/announcements/{ann_id}")
def admin_delete_announcement(ann_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(admin_user)) -> dict:
    """删除公告。"""
    admin_service.admin_delete_announcement(ann_id, request, db, admin)
    return ok()



# ============ 活动管理 ============

class ActivityCreateIn(BaseModel):
    title: str
    description: str
    location: str | None = None
    cover_url: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    organizer: str | None = None
    contact: str | None = None
    max_participants: int | None = None
    is_active: bool = True


@router.get("/activities")
def admin_list_activities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """活动列表（管理端，含停用）。"""
    return ok(activity_service.admin_list_activities(db, page, page_size, keyword))


@router.post("/activities")
def admin_create_activity(
    payload: ActivityCreateIn,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """创建活动。"""
    return ok(activity_service.admin_create_activity(db, payload.model_dump(), admin.id))


@router.patch("/activities/{activity_id}")
def admin_update_activity(
    activity_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """更新活动。"""
    return ok(activity_service.admin_update_activity(db, activity_id, payload))


@router.delete("/activities/{activity_id}")
def admin_delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """删除活动。"""
    activity_service.admin_delete_activity(db, activity_id)
    return ok()


@router.get("/activities/{activity_id}/participants")
def admin_activity_participants(
    activity_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """活动报名名单。"""
    return ok(activity_service.admin_activity_participants(db, activity_id, page, page_size))


# ============ 日志系统 ============

@router.get("/logs")
def admin_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    admin_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """管理员操作日志（分页 + 过滤）。"""
    return ok(admin_service.admin_logs(db, page, page_size, admin_id, action))


@router.get("/user-logs")
def admin_user_logs(
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """用户操作日志（分页 + 过滤）。"""
    return ok(admin_service.admin_user_logs(user_id, action, db, page, page_size))


@router.get("/login-logs")
def admin_login_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user_id: int | None = Query(default=None),
    success: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """用户登录日志（分页 + 过滤）。"""
    return ok(admin_service.admin_login_logs(db, page, page_size, user_id, success))


# ============ 系统设置 ============

# ============ 图片人工审核（图片不走 AI 审核） ============

@router.get("/images")
def admin_images(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """图片审核列表（分页 + 状态过滤）。"""
    return ok(admin_service.admin_list_images(db, status, page, page_size, keyword))


@router.post("/images/{image_id}/review")
def admin_review_image(
    image_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """人工审核图片。payload: action(approve/reject) + reject_reason。"""
    return ok(admin_service.admin_review_image(
        db,
        admin,
        image_id,
        payload.get("action", "approve"),
        reject_reason=payload.get("reject_reason"),
    ))

# ============ 漂流瓶审核（AI 审核 + 人工兜底） ============

@router.get("/bottles")
def admin_bottles(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected|manual_review)$"),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """漂流瓶审核列表（分页 + 审核状态过滤）。"""
    from app.services import bottle_service
    return ok(bottle_service.admin_list_bottles(db, status, page, page_size, keyword))


@router.post("/bottles/{bottle_id}/review")
def admin_review_bottle(
    bottle_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """人工审核漂流瓶。payload: action(approve/reject) + reject_reason。"""
    from app.services import bottle_service
    return ok(bottle_service.admin_review_bottle(
        db,
        admin,
        bottle_id,
        payload.get("action", "approve"),
        reject_reason=payload.get("reject_reason"),
    ))

@router.get("/settings")
def admin_list_settings(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """列出所有系统设置项。"""
    return ok(admin_service.admin_list_settings(db))


@router.put("/settings")
def admin_update_settings(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """批量更新系统设置。payload: {"settings": {"key": "value", ...}}"""
    return ok(admin_service.admin_update_settings(payload, request, db, admin))


# ============ 微信朋友圈管理 ============

@router.get("/wechat/bindings")
def admin_wechat_bindings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """微信绑定列表（后台管理）。"""
    return ok(admin_service.admin_wechat_bindings(db, page, page_size, keyword))


@router.get("/wechat/moments")
def admin_wechat_moments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """已同步的朋友圈动态列表（后台管理）。"""
    return ok(admin_service.admin_wechat_moments(db, page, page_size, keyword))


@router.post("/wechat/bindings/{binding_id}/unbind")
def admin_wechat_unbind(
    binding_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """管理员解绑微信（解除绑定关系 + 关闭自动同步）。"""
    admin_service.admin_wechat_unbind(binding_id, request, db, admin)
    return ok()


@router.get("/explore/stats")
def admin_explore_stats(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """推荐探索效果统计：曝光 / 点击 / CTR / 互动 + Top 探索帖 + 最近曝光日志。"""
    return ok(explore_service.explore_stats(db))


@router.get("/deepseek/config")
def admin_get_deepseek_config(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """读取 DeepSeek 配置。"""
    return ok(admin_service.admin_get_deepseek_config(db))


@router.put("/deepseek/config")
def admin_update_deepseek_config(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """更新 DeepSeek 配置。

    payload: {
        "enabled": bool,
        "api_key": str,
        "base_url": str,
        "model": str,
        "auto_delete_days": int
    }
    """
    return ok(admin_service.admin_update_deepseek_config(payload, request, db, admin))


@router.post("/audit/cleanup")
def admin_cleanup_audit(
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """手动触发审核失败内容自动清理。"""
    return ok(admin_service.admin_cleanup_expired_audit(db, request, admin))


# ============ 阶段四：吧（圈子）申请审核 ============

@router.get("/circles/pending")
def admin_list_pending_circles(
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """待审核吧列表（status=None 时返回所有用户申请的吧，含已审核历史）。"""
    return ok(circle_apply_service.list_pending_applies(db, status))


@router.post("/circles/{category_id}/audit")
def admin_audit_circle(
    category_id: int,
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """审核吧申请。

    payload:
    - approved: bool（true=通过, false=拒绝）
    - reject_reason: str（拒绝时必填，最多 200 字）
    """
    approved = bool(payload.get("approved", False))
    reject_reason = payload.get("reject_reason")
    result = circle_apply_service.audit_circle(db, category_id, approved, reject_reason, admin_id=admin.id)
    # 记录管理员操作日志（audit_circle 已 commit，此处追加日志再提交）
    from app.services.audit_log import log_admin_action
    from app.api.deps import extract_ip
    import json
    log_admin_action(
        db,
        admin.id,
        "audit_circle",
        json.dumps(
            {"category_id": category_id, "approved": approved, "reject_reason": reject_reason or ""},
            ensure_ascii=False,
        ),
        extract_ip(request) if request else None,
    )
    db.commit()
    return ok(result)


# ============ 封号管理 ============

@router.get("/ban-records")
def admin_ban_records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|expired|revoked)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """封号记录列表（分页 + 过滤）。"""
    return ok(admin_service.admin_ban_records(db, page, page_size, user_id, status))


@router.post("/users/{user_id}/ban")
def admin_ban_user(
    user_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """封禁用户。

    payload:
    - reason: 封禁原因（必填）
    - duration_hours: 封禁时长（小时），0=永久，不传则自动计算
    - appealable: 是否允许申诉（默认 True）
    """
    return ok(admin_service.admin_ban_user(user_id, payload, request, db, admin))


@router.post("/users/{user_id}/unban")
def admin_unban_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """手动解封用户。"""
    return ok(admin_service.admin_unban_user(user_id, request, db, admin))


# ============ 申诉管理 ============

@router.get("/appeals")
def admin_appeals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """申诉列表（分页 + 状态过滤）。"""
    return ok(admin_service.admin_appeals(db, page, page_size, status))


@router.patch("/appeals/{appeal_id}/review")
def admin_review_appeal(
    appeal_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """审核申诉：status (approved/rejected) + review_comment。"""
    return ok(admin_service.admin_review_appeal(appeal_id, payload, request, db, admin))


# ============ AI 审核日志 ============

@router.get("/audit-logs")
def admin_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    target_type: str | None = Query(default=None, pattern="^(post|comment|bottle)$"),
    result: str | None = Query(default=None, pattern="^(approved|rejected|error)$"),
    user_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None, pattern="^(high|medium|low|none)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """AI 审核日志列表（分页 + 过滤）。"""
    return ok(admin_service.admin_audit_logs(db, page, page_size, target_type, result, user_id, category, severity))


# ============ 警告值系统管理 ============

@router.get("/warning-config")
def admin_get_warning_config(db: Session = Depends(get_db), _: Admin = Depends(admin_user)) -> dict:
    """获取警告值系统配置。"""
    from app.services import warning_service
    cfg = warning_service.get_warning_config(db)
    return ok(warning_service._config_dict(cfg))


@router.put("/warning-config")
def admin_update_warning_config(
    payload: dict,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """更新警告值系统配置。

    payload 可选字段：
    - warn_threshold: 警告阈值（达到此值发警告通知）
    - temp_ban_threshold: 临时封号阈值
    - temp_ban_hours: 临时封号时长（小时）
    - perm_ban_threshold: 永久封号阈值
    - violation_base_score: 每次违规基础增加值
    - checkin_reduce: 签到减少警告值
    - post_reduce: 发帖审核通过减少警告值
    - comment_reduce: 评论审核通过减少警告值
    """
    from app.services import warning_service
    return ok(warning_service.update_warning_config(db, payload))


@router.post("/users/{user_id}/warning")
def admin_adjust_warning(
    user_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """管理员手动调整用户警告值。

    payload:
    - delta: 调整值（正数增加，负数减少）
    - reason: 调整原因（必填）
    """
    from app.services import warning_service
    delta = int(payload.get("delta", 0))
    reason = payload.get("reason", "")
    return ok(warning_service.admin_adjust_warning(db, user_id, delta, reason, admin.id))


@router.get("/users/{user_id}/warning-logs")
def admin_user_warning_logs(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """查看指定用户的警告值变动记录（分页）。"""
    from app.services import warning_service
    return ok(warning_service.list_user_warning_logs(db, user_id, page, page_size))


# ============ 徽章管理 ============

@router.post("/badges/icon")
async def admin_upload_badge_icon(
    file: UploadFile = File(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """上传徽章图标（服务端自动极限压缩，徽章展示尺寸很小）。

    压缩策略：
    - 统一缩放到 96x96 以内（徽章展示通常 16-32px）
    - 保留透明通道（圆形徽章图标），PNG 量化 256 色 + optimize
    - 上传结果走公开存储（/uploads 或 MinIO），返回 URL 写入徽章 icon 字段
    """
    from app.api.routes.images import (
        ALLOWED_TYPES,
        TYPE_ALIASES,
        _check_content_length,
        _detect_image_type,
        _read_limited,
    )
    from app.services.storage_service import storage_service

    _check_content_length(request)
    raw_content_type = file.content_type or ""
    content_type = TYPE_ALIASES.get(raw_content_type, raw_content_type)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="图片格式仅支持 jpg、png、webp、gif")
    content = await _read_limited(file)

    real_type = _detect_image_type(content)
    if not real_type:
        raise HTTPException(status_code=400, detail="无法识别的图片格式，请重新选择文件")
    if real_type != content_type:
        raise HTTPException(status_code=400, detail="图片内容与声明格式不符，疑似伪装文件")

    # 服务端极限压缩：徽章展示很小，缩放到 96x96，透明背景保留
    BADGE_ICON_MAX_SIZE = (96, 96)
    try:
        img = PILImage.open(io.BytesIO(content))
        img.thumbnail(BADGE_ICON_MAX_SIZE, PILImage.LANCZOS)
        # 统一转 RGBA 保留透明（徽章常为圆形/异形图标）；96px 小图直接存优化 PNG
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        compressed = buf.getvalue()
    except Exception:
        raise HTTPException(status_code=400, detail="图片处理失败，请更换图片重试")

    filename = f"{uuid4().hex}.png"
    url = await storage_service.upload_image_async(filename, compressed, "image/png")
    return ok({
        "url": url,
        "size_bytes": len(compressed),
        "size_text": f"{len(compressed) / 1024:.1f} KB",
    })

@router.get("/badges")
def admin_badges(
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """徽章列表（含停用徽章 + 激活码/发放统计）。"""
    return ok(badge_service.admin_list_badges(db, keyword))


@router.post("/badges")
def admin_create_badge(
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """创建徽章。payload: name/code/icon/description/is_active/sort_order/is_system。"""
    return ok(badge_service.admin_create_badge(payload, request, db, admin))


@router.patch("/badges/{badge_id}")
def admin_update_badge(
    badge_id: int,
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """更新徽章（名称/图标/描述/排序/启用状态）。"""
    return ok(badge_service.admin_update_badge(badge_id, payload, request, db, admin))


@router.delete("/badges/{badge_id}")
def admin_delete_badge(
    badge_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """删除徽章（系统徽章不可删除，只能停用）。"""
    badge_service.admin_delete_badge(badge_id, request, db, admin)
    return ok()


@router.post("/badges/{badge_id}/codes")
def admin_generate_badge_codes(
    badge_id: int,
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """为徽章批量生成激活码。payload: count(1-100)/note/batch_no。"""
    count = int(payload.get("count", 1) or 1)
    return ok(badge_service.admin_generate_badge_codes(
        db, admin, badge_id, count=count,
        request=request,
        note=payload.get("note"),
        batch_no=payload.get("batch_no"),
    ))


@router.get("/badge-codes")
def admin_badge_codes(
    badge_id: int | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(used|unused)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """激活码列表（分页 + 徽章/状态过滤）。"""
    return ok(badge_service.admin_list_badge_codes(
        db, badge_id, status, page, page_size
    ))


@router.delete("/badge-codes/{code_id}")
def admin_delete_badge_code(
    code_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """删除未使用的激活码。"""
    badge_service.admin_delete_badge_code(code_id, request, db, admin)
    return ok()


@router.post("/badges/grant")
def admin_grant_badge(
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """直接向用户发放徽章。payload: user_id/badge_id。"""
    user_id = int(payload.get("user_id", 0))
    badge_id = int(payload.get("badge_id", 0))
    return ok(badge_service.admin_grant_badge(user_id, badge_id, request, db, admin))


@router.get("/badge-rules")
def admin_badge_rules(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """徽章自动发放规则列表。"""
    return ok(badge_service.admin_list_badge_rules(db))


@router.post("/badge-rules")
def admin_create_badge_rule(
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """创建自动发放规则。payload: action/badge_id/threshold/description/is_enabled。"""
    return ok(badge_service.admin_create_badge_rule(payload, request, db, admin))


@router.patch("/badge-rules/{rule_id}")
def admin_update_badge_rule(
    rule_id: int,
    payload: dict = Body(...),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """更新自动发放规则。"""
    return ok(badge_service.admin_update_badge_rule(rule_id, payload, request, db, admin))


@router.delete("/badge-rules/{rule_id}")
def admin_delete_badge_rule(
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """删除自动发放规则。"""
    badge_service.admin_delete_badge_rule(rule_id, request, db, admin)
    return ok()


# ============ 种子邀请码管理 ============

@router.post("/seed-codes/generate")
def admin_generate_seed_codes(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """批量生成种子邀请码。

    Body:
        count: int (1-100, 默认 1)
        note: str | None (备注)
        batch_no: str | None (批次号，不传则自动生成)
    """
    from app.services import verification_service
    count = int(payload.get("count", 1) or 1)
    note = payload.get("note")
    batch_no = payload.get("batch_no")
    return ok(verification_service.admin_generate_seed_codes(db, admin, count=count, note=note, batch_no=batch_no))


@router.get("/seed-codes")
def admin_list_seed_codes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    batch_no: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(unused|reserved|used)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """种子邀请码列表（分页 + 批次号/状态过滤）。"""
    from app.services import verification_service
    return ok(verification_service.admin_list_seed_codes(db, page, page_size, batch_no, status))


@router.post("/seed-codes/reserve")
def admin_reserve_seed_codes(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """复制 N 个未使用种子码并标记为「待使用」（记录当前管理员）。

    Body:
        count: int (1-200)
        note: str | None (备注，会追加到每个种子码的备注中)
        batch_no: str | None (批次号，不传自动生成)
    """
    from app.services import verification_service
    count = int(payload.get("count", 1) or 1)
    return ok(verification_service.admin_reserve_seed_codes(
        db,
        admin,
        count=count,
        note=payload.get("note"),
        batch_no=payload.get("batch_no"),
    ))


@router.post("/seed-codes/{code_id}/release")
def admin_release_seed_code(
    code_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """释放「待使用」种子码，回到未使用池。"""
    from app.services import verification_service
    return ok(verification_service.admin_release_seed_code(db, admin, code_id))


@router.delete("/seed-codes/{code_id}")
def admin_delete_seed_code(
    code_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """删除未使用的种子邀请码（已使用的不可删除）。"""
    from app.services import verification_service
    return ok(verification_service.admin_delete_seed_code(db, admin, code_id))


# ============ 学生认证审核 ============

@router.get("/verifications")
def admin_list_verifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """学生认证申请列表（分页 + 状态过滤）。"""
    from app.services import verification_service
    return ok(verification_service.admin_list_verifications(db, page, page_size, status))


@router.post("/verifications/{verification_id}/review")
def admin_review_verification(
    verification_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """审核学生认证申请。

    Body:
        action: "approve" | "reject"
        reject_reason: str | None (reject 时必填)
    """
    from app.services import verification_service
    action = payload.get("action", "")
    reject_reason = payload.get("reject_reason")
    return ok(verification_service.admin_review_verification(
        db, verification_id, action, admin, reject_reason=reject_reason,
    ))


# =================== 今日竞猜管理（后台） ===================


class AdminGuessCreateIn(BaseModel):
    title: str
    description: str | None = None
    deadline: str  # ISO8601 字符串
    date_key: str | None = None
    options: list[str]


class AdminGuessSettleIn(BaseModel):
    winning_option_id: int


class AdminGuessToggleIn(BaseModel):
    is_active: bool


@router.get("/guesses")
def admin_guess_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_key: str | None = Query(None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """竞猜列表（按创建时间倒序），按日期可选过滤。"""
    from sqlalchemy import select, desc
    from app.models import Guess
    stmt = select(Guess).order_by(desc(Guess.created_at))
    count_stmt = select(_gf.count(Guess.id))
    if date_key:
        stmt = stmt.where(Guess.date_key == date_key)
        count_stmt = count_stmt.where(Guess.date_key == date_key)
    items = list(db.execute(stmt.limit(page_size).offset((page - 1) * page_size)).scalars())
    total_rows = db.scalar(count_stmt)
    return ok({
        "total": int(total_rows or 0),
        "items": [guess_service.guess_with_options(db, g) for g in items],
    })


@router.get("/guesses/{guess_id}")
def admin_guess_detail(
    guess_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    from app.models import Guess
    g = db.get(Guess, guess_id)
    if not g:
        raise HTTPException(status_code=404, detail="竞猜不存在")
    data = guess_service.guess_with_options(db, g)
    # 当前押注记录列表（含 user_id、amount、option_id、result、reward）
    from sqlalchemy import select as sel2
    from app.models import GuessBet, User
    bets = list(db.execute(sel2(GuessBet, User.nickname).outerjoin(User, User.id == GuessBet.user_id).where(GuessBet.guess_id == guess_id).limit(200)).all())
    bet_list = []
    for b, nick in bets:
        bet_list.append({
            "id": b.id, "user_id": b.user_id, "nickname": nick,
            "option_id": b.option_id, "amount": b.amount,
            "result": b.result, "reward": b.reward, "skipped": bool(b.skipped),
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    data["bets"] = bet_list
    return ok(data)


@router.post("/guesses")
def admin_guess_create(
    payload: AdminGuessCreateIn,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """创建新竞猜：自动把同日期其他活跃竞猜置为非活跃。"""
    from datetime import datetime
    try:
        deadline = datetime.fromisoformat(payload.deadline.replace("Z", "+00:00"))
        if deadline.tzinfo is not None:
            deadline = deadline.astimezone().replace(tzinfo=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"deadline 解析失败: {e}")
    g = guess_service.create_guess(
        db,
        title=payload.title,
        description=payload.description,
        deadline=deadline,
        date_key=payload.date_key,
        options=payload.options,
        admin_id=admin.id,
    )
    db.commit()
    return ok(guess_service.guess_with_options(db, g))


@router.patch("/guesses/{guess_id}/toggle")
def admin_guess_toggle(
    guess_id: int,
    payload: AdminGuessToggleIn,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    g = guess_service.toggle_active(db, guess_id, payload.is_active, admin_id=admin.id)
    db.commit()
    return ok(guess_service.guess_with_options(db, g))


@router.delete("/guesses/{guess_id}")
def admin_guess_delete(
    guess_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    guess_service.delete_guess(db, guess_id, admin_id=admin.id)
    db.commit()
    return ok()


@router.post("/guesses/{guess_id}/settle")
def admin_guess_settle(
    guess_id: int,
    payload: AdminGuessSettleIn,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    g = guess_service.settle_guess(db, guess_id, payload.winning_option_id, admin_id=admin.id)
    db.commit()
    return ok(guess_service.guess_with_options(db, g))


# ============================================================
# 宠物商城管理
# ============================================================

class PetShopProductCreate(BaseModel):
    name: str
    category: str
    price: float
    original_price: float | None = None
    stock: int = 0
    image_url: str = ""
    model_3d_url: str = ""
    description: str = ""
    status: int = 1  # 1=上架, 0=下架
    kind: int = 1  # 1=活体宠物, 2=道具（食物等）
    affinity_gain: int = 0  # 喂食加好感数值（仅道具）


class PetShopProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    price: float | None = None
    original_price: float | None = None
    stock: int | None = None
    image_url: str | None = None
    model_3d_url: str | None = None
    description: str | None = None
    status: int | None = None
    kind: int | None = None
    affinity_gain: int | None = None


class PetShopToggleStatus(BaseModel):
    status: int  # 1=上架, 0=下架


class PetShopDyberImport(BaseModel):
    """从 DyberPet 开源项目资源制作宠物。"""
    source_dir: str  # 相对 res 的目录，如 "role/Toothless"
    name: str = ""
    category: str = "萌宠领养"
    price: float = 0
    original_price: float | None = None
    stock: int = 999
    description: str = ""
    actions: list[str] | None = None  # 统一动作 key（stand/walk/sleep/fly/interact），空=全部（≤5）


# 3D 模型上传限制：仅 GLB/GLTF，最大 20MB
MODEL_MAX_BYTES = 20 * 1024 * 1024
MODEL_ALLOWED_EXTS = {".glb", ".gltf"}


async def _read_upload_limited(file: UploadFile, max_bytes: int, err_msg: str) -> bytes:
    """分块读取上传文件，超过 max_bytes 立即拒绝。"""
    content = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=err_msg)
    return bytes(content)


@router.get("/pet-shop/categories")
def admin_pet_shop_categories(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """宠物商城分类列表。"""
    return ok(pet_shop_service.list_categories(db))


@router.get("/pet-shop/products")
def admin_pet_shop_list(
    keyword: str | None = None,
    category: str | None = None,
    status: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """宠物商城商品列表（分页，含下架商品）。"""
    result = pet_shop_service.admin_list_products(db, keyword, category, status, page, page_size)
    admin_service.log_admin_action(db, admin.id, "pet_shop.list", f"page={page}")
    return ok(result)


@router.get("/pet-shop/products/{product_id}")
def admin_pet_shop_detail(
    product_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """商品详情。"""
    admin_service.log_admin_action(db, admin.id, "pet_shop.detail", f"id={product_id}")
    return ok(pet_shop_service.get_product(db, product_id, is_admin=True))


@router.post("/pet-shop/products")
def admin_pet_shop_create(
    payload: PetShopProductCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """新增商品（含 3D 模型地址）。"""
    product = pet_shop_service.admin_create_product(db, payload.model_dump(), admin.id)
    admin_service.log_admin_action(db, admin.id, "pet_shop.create", f"id={product['id']}, name={product['name']}")
    db.commit()
    return ok(product)


@router.patch("/pet-shop/products/{product_id}")
def admin_pet_shop_update(
    product_id: int,
    payload: PetShopProductUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """编辑商品。"""
    product = pet_shop_service.admin_update_product(db, product_id, payload.model_dump(exclude_none=True))
    admin_service.log_admin_action(db, admin.id, "pet_shop.update", f"id={product_id}")
    db.commit()
    return ok(product)


@router.patch("/pet-shop/products/{product_id}/toggle")
def admin_pet_shop_toggle(
    product_id: int,
    payload: PetShopToggleStatus,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """商品上下架。"""
    product = pet_shop_service.admin_toggle_product(db, product_id, payload.status)
    status_text = "上架" if payload.status == 1 else "下架"
    admin_service.log_admin_action(db, admin.id, "pet_shop.toggle", f"id={product_id}, status={status_text}")
    db.commit()
    return ok(product)


@router.delete("/pet-shop/products/{product_id}")
def admin_pet_shop_delete(
    product_id: int,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """删除商品。"""
    pet_shop_service.admin_delete_product(db, product_id)
    admin_service.log_admin_action(db, admin.id, "pet_shop.delete", f"id={product_id}")
    db.commit()
    return ok({"success": True})


@router.post("/pet-shop/upload-model")
async def admin_pet_shop_upload_model(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """上传 3D 模型文件（GLB/GLTF，≤20MB），返回可访问 URL。

    用于宠物（3D）商品详情展示，前端用 model-viewer 加载。
    """
    from app.services.storage_service import storage_service

    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in MODEL_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 GLB / GLTF 格式的 3D 模型文件")

    content = await _read_upload_limited(file, MODEL_MAX_BYTES, "模型文件大小不能超过 20MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    # GLB 二进制魔数校验；GLTF 为 JSON 文本
    if ext == ".glb" and not content.startswith(b"glTF"):
        raise HTTPException(status_code=400, detail="GLB 文件格式无效")
    if ext == ".gltf" and not content.lstrip().startswith(b"{"):
        raise HTTPException(status_code=400, detail="GLTF 文件格式无效")

    filename = f"pet3d/{uuid4().hex}{ext}"
    url = await storage_service.upload_image_async(filename, content, file.content_type or "application/octet-stream")
    admin_service.log_admin_action(db, admin.id, "pet_shop.upload_model", f"file={filename}, bytes={len(content)}")
    db.commit()
    return ok({"url": url, "size": len(content)})


@router.post("/pet-shop/upload-image")
async def admin_pet_shop_upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """上传商品图片（jpg/png/webp/gif，≤5MB），返回可访问 URL。"""
    from app.services.storage_service import storage_service

    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    }
    content_type = (file.content_type or "").lower()
    ext = ext_map.get(content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / WEBP / GIF 图片")

    content = await _read_upload_limited(file, 5 * 1024 * 1024, "图片大小不能超过 5MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        img = PILImage.open(io.BytesIO(content))
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="图片文件无效") from None

    filename = f"petshop/{uuid4().hex}{ext}"
    url = await storage_service.upload_image_async(filename, content, content_type)
    admin_service.log_admin_action(db, admin.id, "pet_shop.upload_image", f"file={filename}, bytes={len(content)}")
    db.commit()
    return ok({"url": url, "size": len(content)})


@router.get("/pet-shop/dyber-pets")
def admin_pet_shop_dyber_list(
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """扫描 DyberPet 开源项目资源目录，列出可制作（导入）的宠物。"""
    result = pet_shop_service.admin_list_dyber_pets()
    admin_service.log_admin_action(db, admin.id, "pet_shop.dyber_list", f"total={result['total']}")
    db.commit()
    return ok(result)


@router.post("/pet-shop/dyber-pets/import")
def admin_pet_shop_dyber_import(
    payload: PetShopDyberImport,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """制作宠物：从 DyberPet 资源导入帧动画并上架商品（复制帧图 + 生成 anim_json）。"""
    result = pet_shop_service.admin_import_dyber_pet(db, payload.model_dump(), admin.id)
    admin_service.log_admin_action(
        db, admin.id, "pet_shop.dyber_import",
        f"source={payload.source_dir}, name={result['product']['name']}, frames={result['frames_copied']}",
    )
    db.commit()
    return ok(result)


@router.post("/pet-shop/upload-zip")
async def admin_pet_shop_import_zip(
    file: UploadFile = File(...),
    name: str = Form(""),
    category: str = Form("萌宠领养"),
    price: float = Form(0),
    original_price: float | None = Form(None),
    stock: int = Form(999),
    description: str = Form(""),
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """制作宠物（上传 ZIP）：ZIP 内含 act_conf.json 动作配置 + 帧图 PNG。

    multipart 上传（python-multipart）。服务端自动压缩帧图；压缩后总大小仍 >20MB 则拒绝。
    复用 DyberPet 的 act_conf.json 解析逻辑，创建/更新商品（kind=1）。
    """
    from app.services.pet_shop_service import MAX_PET_ZIP_COMPRESSED_BYTES

    # 限制读取上限防内存耗尽；是否符合 20MB 最终以"帧图压缩后总大小"在 service 内判定
    raw = await _read_upload_limited(file, 100 * 1024 * 1024, "上传的 ZIP 过大（原始文件超过 100MB）")
    if not raw:
        raise HTTPException(status_code=400, detail="上传的 ZIP 为空")
    meta = {
        "name": name.strip(),
        "category": category.strip(),
        "price": price,
        "original_price": original_price,
        "stock": stock,
        "description": description.strip(),
    }
    result = pet_shop_service.admin_import_pet_zip(db, raw, meta, admin.id)
    admin_service.log_admin_action(
        db, admin.id, "pet_shop.import_zip",
        f"name={result['product']['name']}, action={result['action']}, frames={result['frames_written']}",
    )
    db.commit()
    return ok(result)


# helper imports for count
from sqlalchemy import func as _gf  # noqa: E402
