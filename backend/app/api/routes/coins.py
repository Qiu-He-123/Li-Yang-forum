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
