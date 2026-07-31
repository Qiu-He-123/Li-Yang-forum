from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user, current_user_allow_banned
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.schemas.interactions import ProfileUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def me(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return ok(user_service.profile(user, db))


@router.get("/me/likes")
def my_likes(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """返回当前用户点赞过的帖子 ID 和评论 ID 列表（前端用于回填 active 态）。"""
    return ok({
        "post_ids": user_service.my_liked_post_ids(user.id, db),
        "comment_ids": user_service.my_liked_comment_ids(user.id, db),
    })


@router.get("/me/favorites")
def my_favorites(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """返回当前用户收藏过的帖子 ID 列表（前端用于回填 active 态）。"""
    return ok({"post_ids": user_service.my_favorited_post_ids(user.id, db)})


@router.get("/me/favorites/posts")
def my_favorite_posts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """返回当前用户收藏的帖子完整列表（T5-4 我的收藏页用，分页）。"""
    return ok(user_service.my_favorite_posts(user.id, db, page=page, page_size=page_size))


@router.get("/me/drafts")
def my_drafts(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """返回当前用户的草稿列表（T5-3 我的草稿页用）。"""
    return ok(user_service.my_drafts(user.id, db))


@router.get("/me/likes/posts")
def my_liked_posts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """返回当前用户点赞过的帖子完整列表（T5-1 个人主页点赞 Tab 用，分页）。"""
    return ok(user_service.my_liked_posts(user.id, db, page=page, page_size=page_size))


@router.patch("/me")
def update_me(payload: ProfileUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return ok(user_service.update_me(payload, request, db, user))


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """查询指定用户资料。

    将当前登录用户作为 viewer 传入 profile，返回 is_following / is_following_me /
    is_mutual 字段，供前端主页直接渲染关注状态，避免前端缓存导致的状态不一致。
    """
    return ok(user_service.get_user(user_id, db, viewer=user))


# ============ 封号状态 & 申诉 ============

@router.get("/me/ban-status")
def my_ban_status(db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """获取当前用户的封号状态。封号用户也可访问（封号提示页需要展示封禁信息）。"""
    return ok(user_service.get_ban_status(user, db))


@router.post("/me/appeals")
def create_appeal(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user_allow_banned),
) -> dict:
    """提交申诉。封号用户可访问。

    payload:
    - reason: 申诉理由（必填）
    - ban_record_id: 关联封号记录 ID（可选）
    """
    return ok(user_service.create_appeal(
        user,
        payload.get("reason", ""),
        payload.get("ban_record_id"),
        db,
    ))


@router.get("/me/appeals")
def my_appeals(db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """查询当前用户的申诉列表。封号用户可访问。"""
    return ok(user_service.my_appeals(user, db))


# ============ 警告值系统 ============

@router.get("/me/warning")
def my_warning_status(db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """获取当前用户的警告值状态（个人主页展示用）。封号用户也可访问。"""
    from app.services import warning_service
    return ok(warning_service.get_user_warning_status(user, db))


@router.get("/me/warning-logs")
def my_warning_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user_allow_banned),
) -> dict:
    """查询当前用户的警告值变动记录（分页）。封号用户也可访问。"""
    from app.services import warning_service
    return ok(warning_service.list_user_warning_logs(db, user.id, page, page_size))


@router.get("/{user_id}/posts")
def user_posts_list(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(user_service.user_posts(user_id, db, viewer_id=user.id, page=page, page_size=page_size))


@router.get("/{user_id}/likers")
def user_likers(user_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    """获取点赞过该用户帖子的用户列表（获赞列表页用）。"""
    return ok(user_service.user_likers(user_id, db))


# ============ 学生认证 ============

@router.get("/me/verification")
def my_verification_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """查询当前用户的学生认证申请状态。"""
    from app.services import verification_service
    return ok(verification_service.get_my_verification_status(db, user))


@router.post("/me/verification")
def submit_verification(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """提交学生认证申请（上传学生证/校园卡照片）。

    payload:
        image_url: str (必填，图片 URL，先调 /images 上传得到)
        note: str | None (选填，申请说明，最多 200 字)

    防护：每天最多 3 次，已有 pending 申请不可重复提交。
    """
    from app.services import verification_service
    return ok(verification_service.submit_verification(
        db,
        user,
        image_url=payload.get("image_url", ""),
        note=payload.get("note"),
        request=request,
    ))
