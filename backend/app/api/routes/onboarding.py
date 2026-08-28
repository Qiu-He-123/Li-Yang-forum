"""新手引导完成标记（登录时检测，未完成则触发引导）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status")
def onboarding_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok({"onboarding_done": bool(user.onboarding_done)})


@router.post("/complete")
def complete_onboarding(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if not user.onboarding_done:
        user.onboarding_done = True
        db.commit()
    return ok({"onboarding_done": True})
