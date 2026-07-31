from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, current_user_allow_banned
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import message_service, notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    type: str | None = Query(
        default=None,
        pattern="^(interaction|comment|like|follow|system|announcement|mention|topic|vote_end)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查询当前用户的通知列表（T5-5），支持按 type 过滤 + 分页。"""
    return ok(notification_service.list_notifications(user.id, db, type, page, page_size))


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """返回未读通知数 + 私信未读数（底部导航栏消息红点用）。

    允许封号用户访问：封号用户停留在 /banned 页时，App.vue 全局轮询会调用该接口，
    若用 current_user 会返回 403 + -301 触发 handleBannedRedirect 副作用，引发"系统开小差了"。

    注意：该静态路径必须定义在 /{notification_id} 之前，否则 "unread-count" 会被
    动态路径 {notification_id} 先匹配，触发 int_parsing 422 错误。
    """
    result = notification_service.unread_count(user.id, db)
    result["dm_unread"] = message_service.count_unread_messages(user.id, db)
    return ok(result)


@router.patch("/read-all")
def mark_all_read(
    type: str | None = Query(
        default=None,
        pattern="^(interaction|comment|like|follow|system|announcement|mention|topic|vote_end)$",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """全部已读（可按 type 过滤）。

    注意：该静态路径必须定义在 /{notification_id}/read 之前，避免 "read-all" 被
    动态路径 {notification_id} 先匹配触发 int_parsing 422 错误。
    """
    return ok(notification_service.mark_all_read(user.id, db, type))


@router.get("/{notification_id}")
def get_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """查询单条通知详情（用于通知详情页展示原文）。"""
    return ok(notification_service.get_notification(notification_id, user.id, db))


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """标记单条通知为已读（T5-5）。"""
    return ok(notification_service.mark_read(notification_id, user.id, db))
