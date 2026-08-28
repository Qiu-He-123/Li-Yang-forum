from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import circle_service

router = APIRouter(prefix="/circles", tags=["circles"])


@router.get("")
def list_circles(db: Session = Depends(get_db), user: User | None = Depends(optional_user)) -> dict:
    """圈子列表（含 member_count, post_count, 当前用户是否已加入 is_joined）。

    匿名用户可访问，is_joined 始终为 False。
    """
    return ok(circle_service.list_circles(db, user))


@router.get("/my/views/list")
def my_viewed_circles(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    """获取我浏览过的圈子列表（我的足迹）。"""
    return ok(circle_service.list_viewed_circles(db, user.id, limit))


@router.get("/{slug}")
def get_circle(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_user)) -> dict:
    """圈子详情（含 is_joined）。"""
    data = circle_service.get_circle_detail(slug, db, user)
    # 记录圈子浏览（仅登录用户，失败静默忽略）
    if user:
        try:
            circle_service.record_circle_view(db, user.id, data["id"])
        except Exception:
            pass
    return ok(data)


@router.get("/{slug}/posts")
def list_circle_posts(
    slug: str,
    type: str = Query(default="all", pattern="^(all|essence|image|video)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """圈子内帖子列表（type=all/essence/image/video）。匿名用户可访问。"""
    return ok(circle_service.list_circle_posts(slug, db, user, type, page, page_size))


@router.post("/{slug}/join")
def join_circle(slug: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """加入圈子（幂等，更新 member_count）。"""
    return ok(circle_service.join_circle(slug, db, user))


@router.delete("/{slug}/join")
def leave_circle(slug: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """退出圈子（幂等）。"""
    return ok(circle_service.leave_circle(slug, db, user))
