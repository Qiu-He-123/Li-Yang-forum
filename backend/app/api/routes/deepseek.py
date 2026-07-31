"""DeepSeek AI 审核路由。

提供：
- POST /deepseek/audit: 审核单条文本内容（管理员测试用）
- POST /deepseek/audit-post/{post_id}: 用 DeepSeek 审核指定帖子并更新 ai_status
- POST /deepseek/audit-comment/{comment_id}: 用 DeepSeek 审核指定评论并更新 ai_status
- GET /deepseek/status: 查询 DeepSeek 配置状态
- POST /deepseek/test: 测试连接
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import admin_user
from app.core.database import get_db
from app.models import Admin, Comment, Post
from app.schemas.common import ok
from app.services import deepseek_service, settings_service
from app.services.audit_log import log_admin_action

router = APIRouter(prefix="/deepseek", tags=["deepseek"])


@router.get("/status")
def deepseek_status(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """查询 DeepSeek 配置状态（脱敏返回）。"""
    cfg = settings_service.get_deepseek_config(db)
    # 脱敏：API Key 只返回是否已配置
    return ok({
        "enabled": cfg["enabled"],
        "api_key_configured": bool(cfg["api_key"]),
        "api_key_masked": _mask_key(cfg["api_key"]),
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "auto_delete_days": cfg["auto_delete_days"],
    })


@router.post("/test")
def deepseek_test(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """测试 DeepSeek 连接。"""
    result = deepseek_service.test_connection(db)
    return ok(result)


@router.post("/audit")
def deepseek_audit_text(
    payload: dict,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """审核单条文本内容（管理员测试用）。

    payload: {"content": "待审核文本"}
    """
    content = (payload or {}).get("content", "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    result = deepseek_service.audit_content(db, content)
    return ok(result)


@router.post("/audit-post/{post_id}")
def deepseek_audit_post(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """用 DeepSeek 重新审核指定帖子，并更新 ai_status。

    审核结果：
    - pass=True → ai_status = approved
    - pass=False → ai_status = rejected（保留内容，待人工最终决定）
    - 跳过/失败 → ai_status 保持不变
    """
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    result = deepseek_service.audit_content(db, post.content)
    new_status = None
    if not result.get("skipped"):
        new_status = "approved" if result["pass"] else "rejected"
        post.ai_status = new_status
        db.commit()
        db.refresh(post)

    log_admin_action(
        db,
        admin.id,
        "deepseek_audit_post",
        f'{{"post_id":{post_id},"pass":{result.get("pass")},"category":"{result.get("category")}","severity":"{result.get("severity")}"}}',
        _extract_ip(request),
    )
    db.commit()

    return ok({
        "post_id": post_id,
        "ai_status": post.ai_status,
        "audit_result": result,
    })


@router.post("/audit-comment/{comment_id}")
def deepseek_audit_comment(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """用 DeepSeek 重新审核指定评论，并更新 ai_status。"""
    comment = db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")

    result = deepseek_service.audit_content(db, comment.content)
    if not result.get("skipped"):
        comment.ai_status = "approved" if result["pass"] else "rejected"
        db.commit()
        db.refresh(comment)

    log_admin_action(
        db,
        admin.id,
        "deepseek_audit_comment",
        f'{{"comment_id":{comment_id},"pass":{result.get("pass")},"category":"{result.get("category")}","severity":"{result.get("severity")}"}}',
        _extract_ip(request),
    )
    db.commit()

    return ok({
        "comment_id": comment_id,
        "ai_status": comment.ai_status,
        "audit_result": result,
    })


def _mask_key(key: str) -> str:
    """API Key 脱敏：只显示前 4 位和后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _extract_ip(request) -> str | None:
    try:
        from app.api.deps import extract_ip
        return extract_ip(request)
    except Exception:
        return None
