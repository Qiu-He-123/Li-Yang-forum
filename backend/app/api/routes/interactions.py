from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.schemas.interactions import ReportCreate
from app.services import interaction_service

router = APIRouter(tags=["interactions"])


@router.post("/likes/{target_type}/{target_id}")
def like_target(target_type: str, target_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return ok(interaction_service.like_target(target_type, target_id, request, db, user))


@router.delete("/likes/{target_type}/{target_id}")
def unlike_target(target_type: str, target_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return ok(interaction_service.unlike_target(target_type, target_id, request, db, user))


@router.post("/favorites/{post_id}")
def favorite_post(post_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    interaction_service.favorite_post(post_id, request, db, user)
    return ok()


@router.delete("/favorites/{post_id}")
def unfavorite_post(post_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    interaction_service.unfavorite_post(post_id, request, db, user)
    return ok()


@router.post("/reports")
async def create_report(payload: ReportCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return ok(await interaction_service.create_report(payload, request, db, user))
