"""金币与新手引导接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.core.time_utils import to_iso_zh
from app.models import Badge, CoinTransaction, User, UserBadge
from app.schemas.common import ok
from app.services import coin_service
from app.services.badge_service import badge_dict
from app.services import daily_mission_service

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("/me")
def coins_me(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(
        {
            "coins": coin_service.get_balance(db, user.id),
            "onboarding_done": bool(user.onboarding_done),
        }
    )


# 新人欢迎礼金额（首次登录送金币，一次性）
WELCOME_BONUS = 500


@router.get("/welcome-bonus")
def welcome_bonus(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """首次进入赠送 500 积分（一次性，以是否存在 type='welcome' 流水判定，幂等）。"""
    exists = db.scalar(
        select(func.count(CoinTransaction.id)).where(
            CoinTransaction.user_id == user.id,
            CoinTransaction.type == "welcome",
        )
    ) or 0
    granted = False
    if not exists:
        coin_service.grant_coins(
            db,
            user,
            WELCOME_BONUS,
            "welcome",
            ref_id="welcome-bonus",
            description="新人欢迎礼：首次进入赠送 500 积分",
        )
        db.commit()
        granted = True
    return ok(
        {
            "granted": granted,
            "coins": coin_service.get_balance(db, user.id),
            "onboarding_done": bool(user.onboarding_done),
        }
    )


@router.get("/transactions")
def coin_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    base = select(CoinTransaction).where(CoinTransaction.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        db.scalars(
            base.order_by(desc(CoinTransaction.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    items = [
        {
            "id": t.id,
            "amount": t.amount,
            "balance_after": t.balance_after,
            "type": t.type,
            "ref_id": t.ref_id,
            "description": t.description,
            "created_at": to_iso_zh(t.created_at),
        }
        for t in rows
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/badges")
def purchasable_badges(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    owned = set(
        db.scalars(
            select(UserBadge.badge_id).where(UserBadge.user_id == user.id)
        )
    )
    rows = db.scalars(
        select(Badge).where(Badge.is_active.is_(True), Badge.price > 0).order_by(Badge.price)
    ).all()
    return ok(
        {
            "items": [
                {**badge_dict(b), "price": b.price, "owned": b.id in owned}
                for b in rows
            ],
            "coins": coin_service.get_balance(db, user.id),
        }
    )


@router.post("/badges/{badge_id}/purchase")
def purchase_badge(
    badge_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    badge = db.get(Badge, badge_id)
    if badge is None or not badge.is_active:
        raise HTTPException(status_code=404, detail="徽章不存在")
    if badge.price <= 0:
        raise HTTPException(status_code=400, detail="该徽章不可购买")
    already = db.scalar(
        select(UserBadge.id).where(
            UserBadge.user_id == user.id,
            UserBadge.badge_id == badge.id,
        )
    )
    if already:
        raise HTTPException(status_code=400, detail="已拥有该徽章")
    coin_service.charge_coins(
        db,
        user,
        badge.price,
        "badge_purchase",
        ref_id=str(badge.id),
        description=f"购买徽章：{badge.name}",
    )
    db.add(UserBadge(user_id=user.id, badge_id=badge.id))
    db.commit()
    return ok(
        {
            "badge": badge_dict(badge),
            "coins": coin_service.get_balance(db, user.id),
        }
    )


@router.get("/missions")
def daily_missions(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok({"coins": coin_service.get_balance(db, user.id), "items": daily_mission_service.list_missions(db, user)})


@router.post("/missions/{key}/claim")
def claim_daily_mission(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    try:
        result = daily_mission_service.claim_mission(db, user, key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return ok(result)
