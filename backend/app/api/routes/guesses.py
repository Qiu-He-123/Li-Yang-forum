"""今日竞猜用户侧路由：获取当日竞猜 + 押注 + 跳过。"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import guess_service

router = APIRouter(prefix="/guesses", tags=["guesses"])


class BetRequest(BaseModel):
    option_id: int
    amount: int = Field(ge=10, le=10_000)


@router.get("/today")
def get_today_guess(
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
):
    """获取今日竞猜：含选项实时汇总、当前用户的押注情况（登录后）。
    当日未创建竞猜时返回 data=null。
    """
    g = guess_service.get_active_guess(db)
    if not g:
        return ok({"guess": None, "my_bet": None, "now": datetime.now().isoformat()})
    data = guess_service.guess_with_options(db, g)
    my = None
    if user:
        b = guess_service.get_my_bet(db, user.id, g.id)
        if b:
            my = {
                "id": b.id,
                "option_id": b.option_id,
                "amount": b.amount,
                "skipped": b.skipped,
                "result": b.result,
                "reward": b.reward,
            }
    return ok({"guess": data, "my_bet": my, "now": datetime.now().isoformat()})


@router.post("/{guess_id}/bet")
def bet(
    guess_id: int,
    payload: BetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """押注：一人每日一次，成功后返回我的押注与最新汇总。"""
    bet = guess_service.place_bet(db, user, guess_id, payload.option_id, payload.amount)
    db.commit()
    g = db.get(guess_service.Guess if False else None, guess_id) or None
    from app.models import Guess
    g = db.get(Guess, guess_id)
    return ok({
        "bet": {
            "id": bet.id,
            "option_id": bet.option_id,
            "amount": bet.amount,
            "skipped": bool(bet.skipped),
            "result": bet.result,
        },
        "guess": guess_service.guess_with_options(db, g),
    })


@router.post("/{guess_id}/skip")
def skip(
    guess_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """今日不押注：登记后不再弹该日竞猜弹窗。"""
    bet = guess_service.skip_today(db, user, guess_id)
    db.commit()
    return ok({
        "bet": {
            "id": bet.id,
            "option_id": bet.option_id,
            "amount": bet.amount,
            "skipped": bool(bet.skipped),
            "result": bet.result,
        },
    })
