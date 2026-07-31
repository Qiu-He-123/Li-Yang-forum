from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user, verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.schemas.interactions import CommentCreate
from app.services import comment_service

router = APIRouter(prefix="/posts/{post_id}/comments", tags=["comments"])


@router.get("")
def list_comments(
    post_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """查询帖子评论列表（按楼层分页，匿名用户也可查看）。

    AI 审核可见性：
    - 匿名用户：只见 ai_status=approved 的评论
    - 登录用户：可见 approved；自己发的 pending/rejected 也可见
    """
    return ok(comment_service.list_comments(post_id, db, page, page_size, user))


@router.post("")
async def create_comment(
    post_id: int,
    payload: CommentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """发评论：需要 verified 状态（已填邀请码）。"""
    data = await comment_service.create_comment(post_id, payload, request, db, user)
    return ok(data)


@router.delete("/{comment_id}")
def delete_comment(post_id: int, comment_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """删除评论（含级联删除子回复），返回删除后的 post_comment_count。"""
    new_count = comment_service.delete_comment(post_id, comment_id, request, db, user)
    return ok({"post_comment_count": new_count})
