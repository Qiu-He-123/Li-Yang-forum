import io
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Response, UploadFile
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.api.deps import admin_user
from app.core.database import get_db
from app.models import Admin
from app.schemas.auth import AdminLoginIn
from app.schemas.common import ok
from app.schemas.interactions import AnnouncementCreate
from app.services import admin_service, badge_service, circle_apply_service

router = APIRouter(prefix="/admin", tags=["admin"])


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


@router.delete("/posts/{post_id}")
def admin_delete_post(post_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(admin_user)) -> dict:
    """管理员删除帖子。"""
    admin_service.admin_delete_post(post_id, request, db, admin)
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
    target_type: str | None = Query(default=None, pattern="^(post|comment)$"),
    result: str | None = Query(default=None, pattern="^(approved|rejected|error)$"),
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """AI 审核日志列表（分页 + 过滤）。"""
    return ok(admin_service.admin_audit_logs(db, page, page_size, target_type, result, user_id))


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
