"""意见反馈路由。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
import jwt
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.security import TOKEN_TYPE_ADMIN, decode_token
from app.models import Admin, Feedback, User
from app.schemas.common import ok
from app.schemas.feedback import FeedbackCreate, FeedbackReplyCreate
from app.services import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _is_admin_request(db: Session, request: Request) -> bool:
    """判断请求是否携带有效的 admin_token（管理员身份）。"""
    admin_token = request.cookies.get("admin_token")
    if not admin_token:
        return False
    try:
        admin_id = int(decode_token(admin_token, TOKEN_TYPE_ADMIN))
    except (jwt.InvalidTokenError, ValueError):
        return False
    return db.get(Admin, admin_id) is not None


@router.post("")
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """创建反馈（需登录）。"""
    return ok(feedback_service.create_feedback(db, user.id, payload))


@router.get("")
def list_my_feedbacks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查看我的反馈列表（需登录，分页）。"""
    return ok(feedback_service.list_my_feedbacks(db, user.id, page, page_size))


@router.get("/all")
def list_all_feedbacks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """管理员查看所有反馈（需管理员，分页，支持 status 过滤）。"""
    return ok(feedback_service.list_all_feedbacks(db, page, page_size, status))


@router.get("/{feedback_id}")
def get_feedback(
    feedback_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查看反馈详情（需登录，权限验证：用户只能看自己的，管理员可看所有）。"""
    is_admin = _is_admin_request(db, request)
    return ok(feedback_service.get_feedback(db, feedback_id, user.id, is_admin))


@router.post("/{feedback_id}/reply")
def reply_feedback(
    feedback_id: int,
    payload: FeedbackReplyCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(admin_user),
) -> dict:
    """管理员回复反馈（需管理员）。"""
    return ok(feedback_service.reply_feedback(db, feedback_id, admin.id, payload.content))


@router.patch("/{feedback_id}/close")
def close_feedback(
    feedback_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """关闭反馈（需管理员或反馈作者）。"""
    feedback = db.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")
    is_admin = _is_admin_request(db, request)
    if not is_admin and feedback.user_id != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    return ok(feedback_service.close_feedback(db, feedback_id))
