from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user, verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.schemas.post import PostCreate, PostUpdate
from app.services import post_service

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
def list_posts(
    view: str = Query(default="all", pattern="^(all|school|hot|latest|today)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    category: str | None = Query(default=None, min_length=1, max_length=32),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """帖子列表（游客可访问，仅返回 approved 且未隐藏的帖子）。"""
    return ok(post_service.list_posts(view, db, user, page, page_size, q, category, tag))


@router.get("/drafts")
def list_drafts(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取当前用户的草稿列表（需登录，按 updated_at 倒序）。"""
    return ok(post_service.list_drafts(db, user))


@router.get("/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """查询单个帖子详情。

    游客（未登录）可查看公开且审核通过的帖子详情；
    登录用户访问时自动记录浏览历史（异步、失败不阻塞主流程）。
    """
    result = post_service.get_post(post_id, db, user)
    # 记录浏览历史（仅登录用户）
    if user is not None:
        try:
            from app.services import browse_history_service
            browse_history_service.record_view(db, user.id, post_id)
        except Exception:
            pass  # 浏览历史记录失败不影响帖子详情返回
    return ok(result)


@router.post("")
async def create_post(
    payload: PostCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """发帖：需要 verified 状态（已填邀请码）。"""
    data = await post_service.create_post(payload, request, db, user)
    return ok(data)


@router.patch("/{post_id}")
async def update_post(
    post_id: int,
    payload: PostUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    data = await post_service.update_post(post_id, payload, request, db, user)
    return ok(data)


@router.delete("/{post_id}")
def delete_post(post_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    post_service.delete_post(post_id, request, db, user)
    return ok()


@router.get("/{post_id}/related")
def related_posts(
    post_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """相关推荐（同圈子/同分类的 4 条帖子，排除当前）。"""
    return ok(post_service.related_posts(post_id, db, user, limit=4))


@router.post("/{post_id}/share")
def share_post(post_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """分享计数（幂等，share_count+1）。"""
    return ok(post_service.share_post(post_id, db))


@router.post("/{post_id}/view")
def view_post(post_id: int, db: Session = Depends(get_db), user: User | None = Depends(optional_user)) -> dict:
    """浏览计数（view_count+1，匿名用户也可调用）。"""
    return ok(post_service.view_post(post_id, db))
