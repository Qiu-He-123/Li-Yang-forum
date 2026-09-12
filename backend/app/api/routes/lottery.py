"""抽奖（提现改抽奖）接口。

用户端（前缀 /orders）：
- 查看奖池 / 我的券与库存
- 交易币兑换抽奖券
- 抽取（摇奖 / 看广告加成 / 领取）

后台（前缀 /admin/orders/lottery）：
- 奖品 CRUD / 启停
- 抽奖设置（券汇率 / 开关 / 管理员微信）
- 抽取记录 / 库存兑付列表
"""
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user
from app.core.database import get_db
from app.core.time_utils import to_iso_zh
from app.models import Admin, LotteryAccount, LotteryDraw, LotteryInventory, LotteryPrize, User
from app.schemas.common import ok
from app.services import order_service as os, settings_service

router = APIRouter(prefix="/orders/lottery", tags=["orders-lottery"])
admin_router = APIRouter(prefix="/admin/orders/lottery", tags=["orders-lottery-admin"])

DRAW_COST = 1  # 每次抽奖消耗抽奖券张数


def _ticket_rate(db: Session) -> int:
    return max(1, settings_service.get_int(db, "lottery_ticket_rate", os._rate(db)))


def _enabled(db: Session) -> bool:
    return settings_service.get_bool(db, "lottery_enabled", True)


def _admin_wechat(db: Session) -> str:
    return settings_service.get_setting(db, "lottery_admin_wechat", "")


def _get_account(db: Session, user_id: int) -> LotteryAccount:
    acc = db.scalar(select(LotteryAccount).where(LotteryAccount.user_id == user_id))
    if acc is None:
        acc = LotteryAccount(user_id=user_id, ticket_qty=0, total_draws=0)
        db.add(acc)
        db.flush()
    return acc


def _pick_prize(db: Session) -> LotteryPrize:
    prizes = db.scalars(
        select(LotteryPrize).where(LotteryPrize.enabled == True)  # noqa: E712
        .order_by(LotteryPrize.sort_order, LotteryPrize.id)
    ).all()
    if not prizes:
        raise HTTPException(status_code=400, detail="奖池空空如也，管理员还没上架奖品")
    weights = [max(1, p.weight) for p in prizes]
    return random.choices(prizes, weights=weights, k=1)[0]


def _roll_qty(p: LotteryPrize) -> int:
    """在 [min,max] 上以 hot_qty 为峰值加权摇数量：越接近爆率峰值概率越高。"""
    lo, hi = p.min_qty, p.max_qty
    hot = max(lo, min(hi, p.hot_qty))
    span = max(1, hi - lo)
    pool: list[int] = []
    weight_map: list[int] = []
    for v in range(lo, hi + 1):
        dist = abs(v - hot)
        pool.append(v)
        weight_map.append(max(1, span - dist + 1))
    return random.choices(pool, weights=weight_map, k=1)[0]


def _prize_dict(p: LotteryPrize) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "image_url": p.image_url,
        "weight": p.weight,
        "min_qty": p.min_qty,
        "max_qty": p.max_qty,
        "hot_qty": p.hot_qty,
        "ad_qty": p.ad_qty,
        "max_ad_times": p.max_ad_times,
        "enabled": bool(p.enabled),
    }


# ==================== 用户端 ====================


@router.get("/pool")
def lottery_pool(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    prizes = db.scalars(
        select(LotteryPrize).where(LotteryPrize.enabled == True)  # noqa: E712
        .order_by(LotteryPrize.sort_order, LotteryPrize.id)
    ).all()
    acc = _get_account(db, user.id)
    return ok(
        {
            "prizes": [_prize_dict(p) for p in prizes],
            "ticket_rate": _ticket_rate(db),
            "enabled": _enabled(db),
            "admin_wechat": _admin_wechat(db),
            "draw_cost": DRAW_COST,
            "my": {"ticket_qty": acc.ticket_qty, "total_draws": acc.total_draws},
        }
    )


@router.get("/my")
def lottery_my(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    acc = _get_account(db, user.id)
    invs = db.scalars(
        select(LotteryInventory).where(LotteryInventory.user_id == user.id).order_by(desc(LotteryInventory.id)).limit(100)
    ).all()
    return ok(
        {
            "ticket_qty": acc.ticket_qty,
            "total_draws": acc.total_draws,
            "inventory": [
                {
                    "id": x.id,
                    "draw_id": x.draw_id,
                    "prize_name": x.prize_name,
                    "image_url": x.image_url,
                    "qty": x.qty,
                    "status": x.status,
                    "claimed_at": to_iso_zh(x.claimed_at),
                    "created_at": to_iso_zh(x.created_at),
                }
                for x in invs
            ],
        }
    )


@router.post("/exchange")
def lottery_exchange(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """交易币兑换抽奖券。"""
    rate = _ticket_rate(db)
    try:
        count = int(payload.get("count", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="兑换数量不合法") from None
    if count < 1:
        raise HTTPException(status_code=400, detail="兑换数量需大于 0")
    if not _enabled(db):
        raise HTTPException(status_code=400, detail="抽奖活动未开启")
    cost = count * rate
    try:
        os.debit(db, user, cost, "ticket_exchange", ref_id=f"lottery-ex-{count}", description=f"用 {cost} 交易币兑换 {count} 张抽奖券")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    acc = _get_account(db, user.id)
    acc.ticket_qty += count
    db.commit()
    db.refresh(acc)
    return ok({"ticket_qty": acc.ticket_qty, "spent": cost, "count": count})


@router.post("/draw")
def lottery_draw(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """消耗 1 张抽奖券抽一次。"""
    if not _enabled(db):
        raise HTTPException(status_code=400, detail="抽奖活动未开启")
    acc = _get_account(db, user.id)
    if acc.ticket_qty < DRAW_COST:
        raise HTTPException(status_code=400, detail="抽奖券不足，请先兑换")
    prize = _pick_prize(db)
    base_qty = _roll_qty(prize)
    acc.ticket_qty -= DRAW_COST
    acc.total_draws += 1
    draw = LotteryDraw(
        user_id=user.id,
        prize_id=prize.id,
        prize_name=prize.name,
        base_qty=base_qty,
        total_qty=base_qty,
        status="pending",
    )
    db.add(draw)
    db.flush()
    inv = LotteryInventory(
        user_id=user.id,
        draw_id=draw.id,
        prize_id=prize.id,
        prize_name=prize.name,
        image_url=prize.image_url,
        qty=base_qty,
        status="pending",
    )
    db.add(inv)
    os._ledger(db, user.id, 0, "lottery_draw", ref_id=f"draw-{draw.id}", description=f"消耗 1 张抽奖券：抽中「{prize.name}」×{base_qty}")
    db.commit()
    db.refresh(draw)
    return ok(
        {
            "draw_id": draw.id,
            "prize": {
                "id": prize.id,
                "name": prize.name,
                "image_url": prize.image_url,
                "min_qty": prize.min_qty,
                "max_qty": prize.max_qty,
                "hot_qty": prize.hot_qty,
                "ad_qty": prize.ad_qty,
                "max_ad_times": prize.max_ad_times,
            },
            "base_qty": base_qty,
            "ticket_qty": acc.ticket_qty,
            "ad_times_left": prize.max_ad_times,
        }
    )


@router.post("/ad-grant")
def lottery_ad_grant(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """看广告抽数量：每次按奖品 ad_qty 追加，max_ad_times 次内有效（单次抽取数量不可累计）。"""
    try:
        draw_id = int(payload.get("draw_id", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="参数不合法") from None
    draw = db.get(LotteryDraw, draw_id)
    if not draw or draw.user_id != user.id:
        raise HTTPException(status_code=404, detail="抽取记录不存在")
    if draw.status == "claimed":
        raise HTTPException(status_code=400, detail="已领取，不可再加数量")
    prize = db.get(LotteryPrize, draw.prize_id)
    max_times = prize.max_ad_times if prize else 4
    if draw.ad_times_used >= max_times:
        raise HTTPException(status_code=400, detail="本单看广告次数已用尽，单次抽取数量不可累计")
    draw.ad_times_used += 1
    draw.ad_qty_granted += prize.ad_qty if prize else 1
    draw.total_qty = draw.base_qty + draw.ad_qty_granted
    # 同步库存数量
    inv = db.scalar(select(LotteryInventory).where(LotteryInventory.draw_id == draw.id))
    if inv:
        inv.qty = draw.total_qty
    os._ledger(db, user.id, 0, "lottery_win", ref_id=f"draw-{draw.id}", description=f"看广告加成「{draw.prize_name}」+{prize.ad_qty}")
    db.commit()
    db.refresh(draw)
    return ok(
        {
            "draw_id": draw.id,
            "ad_times_left": max(0, max_times - draw.ad_times_used),
            "ad_qty_granted": draw.ad_qty_granted,
            "total_qty": draw.total_qty,
        }
    )


@router.post("/claim")
def lottery_claim(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """领取：把中奖计入账户，提示加管理员微信兑付。"""
    try:
        draw_id = int(payload.get("draw_id", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="参数不合法") from None
    draw = db.get(LotteryDraw, draw_id)
    if not draw or draw.user_id != user.id:
        raise HTTPException(status_code=404, detail="抽取记录不存在")
    if draw.status == "claimed":
        return ok({"claimed": True, "admin_wechat": _admin_wechat(db), "qty": draw.total_qty})
    from app.core.time_utils import now_utc

    draw.status = "claimed"
    inv = db.scalar(select(LotteryInventory).where(LotteryInventory.draw_id == draw.id))
    if inv:
        inv.status = "claimed"
        inv.claimed_at = now_utc()
    db.commit()
    return ok({"claimed": True, "admin_wechat": _admin_wechat(db), "qty": draw.total_qty})


# ==================== 后台 ====================


@admin_router.get("/settings")
def admin_get_lottery_settings(db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    return ok(
        {
            "ticket_rate": _ticket_rate(db),
            "enabled": _enabled(db),
            "admin_wechat": _admin_wechat(db),
        }
    )


@admin_router.post("/settings")
def admin_set_lottery_settings(payload: dict, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    updates = {}
    if payload.get("ticket_rate") is not None:
        updates["lottery_ticket_rate"] = str(max(1, int(payload["ticket_rate"])))
    if payload.get("enabled") is not None:
        updates["lottery_enabled"] = "1" if bool(payload["enabled"]) else "0"
    if payload.get("admin_wechat") is not None:
        updates["lottery_admin_wechat"] = str(payload["admin_wechat"])[:64]
    if updates:
        settings_service.set_many(db, updates)
    return ok(
        {
            "ticket_rate": _ticket_rate(db),
            "enabled": _enabled(db),
            "admin_wechat": _admin_wechat(db),
        }
    )


@admin_router.get("/prizes")
def admin_list_prizes(db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    prizes = db.scalars(select(LotteryPrize).order_by(LotteryPrize.sort_order, LotteryPrize.id)).all()
    return ok({"items": [_prize_dict(p) for p in prizes]})


@admin_router.post("/prizes")
def admin_create_prize(payload: dict, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="奖品名称不能为空")
    min_qty = max(1, int(payload.get("min_qty", 1)))
    max_qty = max(1, int(payload.get("max_qty", 1)))
    hot_qty = int(payload.get("hot_qty", min_qty))
    if max_qty < min_qty:
        raise HTTPException(status_code=400, detail="数量上限不能小于下限")
    hot_qty = max(min_qty, min(max_qty, hot_qty))
    p = LotteryPrize(
        name=name,
        image_url=str(payload.get("image_url", "") or "")[:255] or None,
        weight=max(1, int(payload.get("weight", 10))),
        min_qty=min_qty,
        max_qty=max_qty,
        hot_qty=hot_qty,
        ad_qty=max(1, int(payload.get("ad_qty", 1))),
        max_ad_times=max(1, int(payload.get("max_ad_times", 4))),
        enabled=bool(payload.get("enabled", True)),
        sort_order=int(payload.get("sort_order", 0)),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return ok(_prize_dict(p))


@admin_router.put("/prizes/{prize_id}")
def admin_update_prize(prize_id: int, payload: dict, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    p = db.get(LotteryPrize, prize_id)
    if not p:
        raise HTTPException(status_code=404, detail="奖品不存在")
    if payload.get("name") is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="奖品名称不能为空")
        p.name = name
    if payload.get("image_url") is not None:
        p.image_url = str(payload["image_url"] or "")[:255] or None
    if payload.get("weight") is not None:
        p.weight = max(1, int(payload["weight"]))
    if payload.get("min_qty") is not None or payload.get("max_qty") is not None or payload.get("hot_qty") is not None:
        min_qty = int(payload.get("min_qty", p.min_qty))
        max_qty = int(payload.get("max_qty", p.max_qty))
        if max_qty < min_qty:
            raise HTTPException(status_code=400, detail="数量上限不能小于下限")
        p.min_qty, p.max_qty = min_qty, max_qty
        hot_qty = int(payload.get("hot_qty", p.hot_qty))
        p.hot_qty = max(min_qty, min(max_qty, hot_qty))
    if payload.get("ad_qty") is not None:
        p.ad_qty = max(1, int(payload["ad_qty"]))
    if payload.get("max_ad_times") is not None:
        p.max_ad_times = max(1, int(payload["max_ad_times"]))
    if payload.get("enabled") is not None:
        p.enabled = bool(payload["enabled"])
    if payload.get("sort_order") is not None:
        p.sort_order = int(payload["sort_order"])
    db.commit()
    db.refresh(p)
    return ok(_prize_dict(p))


@admin_router.delete("/prizes/{prize_id}")
def admin_delete_prize(prize_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    p = db.get(LotteryPrize, prize_id)
    if not p:
        raise HTTPException(status_code=404, detail="奖品不存在")
    db.delete(p)
    db.commit()
    return ok()


@admin_router.get("/draws")
def admin_list_draws(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(LotteryDraw)
    if status:
        base = base.where(LotteryDraw.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(LotteryDraw.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for d in rows:
        u = db.get(User, d.user_id)
        items.append(
            {
                "id": d.id,
                "user_id": d.user_id,
                "user_name": (u.nickname if u else "") or (u.username if u else ""),
                "prize_name": d.prize_name,
                "base_qty": d.base_qty,
                "ad_times_used": d.ad_times_used,
                "ad_qty_granted": d.ad_qty_granted,
                "total_qty": d.total_qty,
                "status": d.status,
                "created_at": to_iso_zh(d.created_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@admin_router.get("/inventory")
def admin_list_inventory(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(LotteryInventory)
    if status:
        base = base.where(LotteryInventory.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(LotteryInventory.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for x in rows:
        u = db.get(User, x.user_id)
        items.append(
            {
                "id": x.id,
                "user_id": x.user_id,
                "user_name": (u.nickname if u else "") or (u.username if u else ""),
                "prize_name": x.prize_name,
                "image_url": x.image_url,
                "qty": x.qty,
                "status": x.status,
                "claimed_at": to_iso_zh(x.claimed_at),
                "created_at": to_iso_zh(x.created_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})