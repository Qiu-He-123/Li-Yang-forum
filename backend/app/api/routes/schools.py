from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import School
from app.schemas.common import ok

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("")
def list_schools(db: Session = Depends(get_db)) -> dict:
    schools = db.scalars(select(School).order_by(School.id)).all()
    return ok([{"id": item.id, "name": item.name, "code": item.code} for item in schools])

