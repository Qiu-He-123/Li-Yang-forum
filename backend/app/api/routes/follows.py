from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import follow_service

# 关注接口挂在 /users/{user_id} 下，与 users 路由保持一致风格
router = APIRouter(prefix="/users", tags=["follows"])


@router.post("/{user_id}/follow")
def follow_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """关注用户（幂等，更新 following_count/followers_count，触发 type=follow 通知）。"""
    return ok(follow_service.follow_user(db, user, user_id))


@router.delete("/{user_id}/follow")
def unfollow_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """取关用户（幂等）。"""
    return ok(follow_service.unfollow_user(db, user, user_id))


@router.get("/{user_id}/following")
def list_following(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """关注列表。"""
    return ok(follow_service.list_following(db, user_id, user.id))


@router.get("/{user_id}/followers")
def list_followers(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """粉丝列表。"""
    return ok(follow_service.list_followers(db, user_id, user.id))


@router.get("/{user_id}/is-following")
def is_following(user_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """当前用户是否已关注 user_id。"""
    return ok(follow_service.is_following(db, user, user_id))
