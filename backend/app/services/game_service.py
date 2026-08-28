"""游戏中心服务：游戏列表 / 金币奖励发放 / 用户自制游戏提交 / 后台管理。"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import beijing_today_start
from app.models import CoinTransaction, Game, GameAffinity, GameRecord, User
from app.services import coin_service


def _game_dict(g: Game) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "slug": g.slug,
        "type": g.type,
        "description": g.description or "",
        "icon_url": g.icon_url or "",
        "reward_coins": g.reward_coins,
        "daily_limit": g.daily_limit,
        "affinity_daily_limit": getattr(g, "affinity_daily_limit", None) or 0,
        "is_active": bool(g.is_active),
        "sort_order": g.sort_order,
        "source": g.source,
        "status": g.status,
        "created_by": g.created_by,
    }


def list_games(db: Session, include_inactive: bool = False) -> list[dict]:
    """公开列表：仅返回已上架（status=active 且 is_active）的游戏。"""
    q = select(Game).order_by(Game.sort_order.asc(), Game.id.asc())
    if not include_inactive:
        q = q.where(Game.is_active.is_(True), Game.status == "active")
    return [_game_dict(g) for g in db.scalars(q).all()]


def get_game_by_slug(db: Session, slug: str) -> Game:
    g = db.scalar(select(Game).where(Game.slug == slug))
    if g is None:
        raise HTTPException(status_code=404, detail="游戏不存在")
    return g


def _daily_claim_count(db: Session, user_id: int, slug: str) -> int:
    return db.scalar(
        select(func.count(CoinTransaction.id)).where(
            CoinTransaction.user_id == user_id,
            CoinTransaction.type == "game_reward",
            CoinTransaction.ref_id == slug,
            CoinTransaction.created_at >= beijing_today_start(),
        )
    ) or 0


def _today_str() -> str:
    from datetime import date
    return date.today().strftime("%Y-%m-%d")


def _daily_affinity_count(db: Session, user_id: int, slug: str) -> int:
    """用户今日从某游戏获得的好感度累计（来自 game_affinity_records）。"""
    today = _today_str()
    return db.scalar(
        select(func.coalesce(func.sum(GameAffinity.amount), 0)).where(
            GameAffinity.user_id == user_id,
            GameAffinity.game_key == slug,
            GameAffinity.date == today,
        )
    ) or 0


def grant_game_affinity(db: Session, user: User, slug: str, pet_product_id: int) -> int:
    """给宠物的「陪我玩」发放好感（受该游戏 affinity_daily_limit 与宠物每日好感上限双重约束）。

    - 该游戏今日好感知 < affinity_daily_limit 时发放，否则返回 0。
    - 好感数值基准 raw_gain=2（玩耍），并复用 pet 侧递减/每日上限逻辑。
    返回实际发放的好感值。
    """
    game = get_game_by_slug(db, slug)
    limit = getattr(game, "affinity_daily_limit", None)
    if limit is None or limit <= 0:
        return 0

    from app.models import UserPet
    from app.services import pet_shop_service

    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    # 1) 该游戏每日好感上限
    today = _today_str()
    game_today = _daily_affinity_count(db, user.id, slug)
    game_remaining = limit - game_today
    if game_remaining <= 0:
        return 0

    # 2) 宠物全局每日好感上限（_apply_affinity 内部会扣减并截断）
    result = pet_shop_service._apply_affinity(up, 2)  # raw_gain=2（玩耍）
    gained = result["gained"]
    actual = min(gained, game_remaining)

    # 实际发放少于按原始好感知算出的值时，回补 daily_affinity_gained 差额，保证全局配额不被虚耗
    if gained != actual:
        # 直接修正：把本次 _apply_affinity 多计的部分回退
        up.affinity = max(0, up.affinity - (gained - actual))
        up.daily_affinity_gained = max(0, up.daily_affinity_gained - (gained - actual))

    if actual > 0:
        rec = db.scalar(
            select(GameAffinity).where(
                GameAffinity.user_id == user.id,
                GameAffinity.game_key == slug,
                GameAffinity.date == today,
            )
        )
        if rec is None:
            rec = GameAffinity(user_id=user.id, game_key=slug, date=today, amount=actual)
            db.add(rec)
        else:
            rec.amount = (rec.amount or 0) + actual
        db.flush()
    return actual


def _upsert_best(db: Session, user: User, slug: str, best_score: int) -> bool:
    """Upsert 游戏最佳战绩，返回是否刷新了新纪录。"""
    record = db.scalar(
        select(GameRecord).where(
            GameRecord.user_id == user.id,
            GameRecord.game_key == slug,
        )
    )
    if record is None:
        db.add(GameRecord(user_id=user.id, game_key=slug, best_score=best_score))
        db.flush()
        return True
    if best_score > record.best_score:
        record.best_score = best_score
        db.flush()
        return True
    return False


def claim_reward(
    db: Session,
    user: User,
    slug: str,
    best_score: int = 0,
    track: bool = True,
) -> dict:
    """领取游戏金币奖励。

    - track=True：仅当刷新最佳战绩（新纪录）时才有资格领奖，防刷。
    - track=False：无分数追踪的游戏（用户自制等），每次游玩后手动领取，
      由 daily_limit 限制每日可领次数防刷。
    - 每日领取次数达到 daily_limit 后不再发放（金币流水 type='game_reward' 计次）。
    """
    game = get_game_by_slug(db, slug)
    if not game.is_active or game.status != "active":
        raise HTTPException(status_code=400, detail="该游戏暂未上架")

    new_best = False
    if track and best_score > 0:
        new_best = _upsert_best(db, user, slug, best_score)

    eligible = (track and new_best) or (not track)
    awarded = 0
    if eligible:
        daily_count = _daily_claim_count(db, user.id, slug)
        if daily_count < game.daily_limit:
            # grant_coins 返回的是发放后的余额，这里单独记录实际发放的金币数
            awarded = game.reward_coins
            coin_service.grant_coins(
                db,
                user,
                game.reward_coins,
                "game_reward",
                ref_id=slug,
                description=f"小游戏「{game.name}」奖励（+{game.reward_coins}金币）",
            )
    db.commit()

    return {
        "awarded": awarded,
        "coins": coin_service.get_balance(db, user.id),
        "new_best": new_best,
        "daily_remaining": max(0, game.daily_limit - _daily_claim_count(db, user.id, slug)),
        "reward_coins": game.reward_coins,
        "daily_limit": game.daily_limit,
    }


def submit_game(
    db: Session,
    user: User,
    name: str,
    type_: str,
    description: str,
    html_content: str,
) -> dict:
    """用户「制作游戏」提交：入库待审核，审核通过后自动生成 slug 并上架。"""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写游戏名称")
    if type_ not in {"single", "multi"}:
        raise HTTPException(status_code=400, detail="游戏类型不合法")
    if not html_content or len(html_content) < 200:
        raise HTTPException(status_code=400, detail="请上传完整可运行的游戏 HTML")
    # 简单防 XSS：自制游戏由 iframe 承载，本应用不做展示型内容注入
    from uuid import uuid4

    slug = f"user-{uuid4().hex[:12]}"
    game = Game(
        name=name[:100],
        slug=slug,
        type=type_,
        description=(description or "")[:500],
        html_content=html_content,
        source="user",
        status="pending",
        reward_coins=6,
        daily_limit=8,
        created_by=user.id,
        icon_url="🎮",
        is_active=False,
        sort_order=1000,
    )
    db.add(game)
    db.commit()
    return _game_dict(game)


# ============ 后台管理 ============


def admin_list(db: Session, keyword: str | None = None) -> list[dict]:
    q = select(Game).order_by(Game.sort_order.asc(), Game.id.asc())
    if keyword:
        q = q.where(Game.name.contains(keyword))
    return [_game_dict(g) for g in db.scalars(q).all()]


def admin_create(
    db: Session,
    name: str,
    slug: str,
    type_: str,
    description: str,
    icon_url: str,
    reward_coins: int,
    daily_limit: int,
    affinity_daily_limit: int = 20,
    sort_order: int = 0,
) -> dict:
    name = name.strip()
    slug = slug.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="请填写游戏名称")
    if not slug:
        raise HTTPException(status_code=400, detail="请填写游戏标识")
    if db.scalar(select(Game).where(Game.slug == slug)):
        raise HTTPException(status_code=400, detail="游戏标识已存在")
    game = Game(
        name=name[:100],
        slug=slug,
        type=type_,
        description=description[:500] or None,
        icon_url=icon_url or None,
        reward_coins=max(0, reward_coins),
        daily_limit=max(1, daily_limit),
        affinity_daily_limit=max(0, affinity_daily_limit),
        sort_order=sort_order,
        source="builtin",
        status="active",
        is_active=True,
    )
    db.add(game)
    db.commit()
    return _game_dict(game)


def admin_update(db: Session, game_id: int, **fields) -> dict:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="游戏不存在")
    allowed = {
        "name", "type", "description", "icon_url", "reward_coins",
        "daily_limit", "affinity_daily_limit", "sort_order", "is_active", "status",
    }
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "name":
                v = str(v).strip()[:100]
                if not v:
                    raise HTTPException(status_code=400, detail="游戏名称不能为空")
            elif k == "reward_coins":
                v = max(0, int(v))
            elif k == "daily_limit":
                v = max(1, int(v))
            elif k == "affinity_daily_limit":
                v = max(0, int(v))
            elif k == "sort_order":
                v = int(v)
            setattr(game, k, v)
    db.commit()
    return _game_dict(game)


def admin_delete(db: Session, game_id: int) -> None:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="游戏不存在")
    db.delete(game)
    db.commit()
