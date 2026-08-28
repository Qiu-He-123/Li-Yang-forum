"""首页「排行」API。

- GET /rankings/coins：金币排行（按 users.coins 倒序）
- GET /rankings/pet-affinity：宠物亲密度排行（按 user_pets.affinity 求和倒序）
- GET /rankings/game：游戏排行（按 game_records.best_score 求和倒序）
- GET /rankings/all：全部排行 = 金币 + 亲密度 + 游戏 三项总和
- POST /rankings/game/score：上报小游戏最佳战绩（Upsert，取较大值）

排行数据为公开数据（游客可看）；「me」字段在登录后返回自己的名次。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import GameRecord, User, UserPet
from app.schemas.common import ok
from app.services.avatar import avatar_url_or_default
from app.services.badge_service import badge_dict

router = APIRouter(prefix="/rankings", tags=["rankings"])

# 前端 PetPlay 的小游戏 key 白名单（防越权写入任意 key）
GAME_KEYS = {"catch", "bubble", "memory", "rps", "wheel", "mole"}


def _user_items(
    scored: list[tuple[User, int]],
    limit: int,
    extras: dict[int, dict] | None = None,
) -> list[dict]:
    """把有序 (User, score) 列表转成排行条目（带名次/头像/徽章/学校）。"""
    extras = extras or {}
    items: list[dict] = []
    for i, (u, score) in enumerate(scored[:limit], start=1):
        items.append(
            {
                "rank": i,
                "user_id": u.id,
                "nickname": u.nickname,
                "avatar_url": avatar_url_or_default(u.avatar_url),
                "badge": badge_dict(u.wearing_badge),
                "school": u.school.name if u.school else None,
                "score": score,
                "extra": extras.get(u.id, {}),
            }
        )
    return items


def _me_entry(scored: list[tuple[User, int]], user: User | None) -> dict | None:
    """在有序列表里定位当前登录用户的名次；未登录或不在榜返回 None。"""
    if not user:
        return None
    for i, (u, s) in enumerate(scored, start=1):
        if u.id == user.id:
            return {"rank": i, "user_id": user.id, "nickname": user.nickname, "score": s}
    return None


def _load_users(db: Session, user_ids: list[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    return {
        u.id: u
        for u in db.scalars(
            select(User).options(selectinload(User.school)).where(User.id.in_(user_ids))
        ).all()
    }


@router.get("/coins")
def coin_ranking(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """金币排行：仅统计余额 > 0 的活跃用户。"""
    users = db.scalars(
        select(User).options(selectinload(User.school)).where(User.is_active.is_(True))
    ).all()
    scored: list[tuple[User, int]] = [
        (u, u.coins or 0) for u in users if (u.coins or 0) > 0
    ]
    scored.sort(key=lambda t: (-t[1], t[0].id))
    return ok(
        {
            "items": _user_items(scored, limit),
            "total": len(scored),
            "me": _me_entry(scored, user),
        }
    )


@router.get("/pet-affinity")
def pet_affinity_ranking(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """宠物亲密度排行：按每个用户所有宠物好感度之和倒序。"""
    rows = db.execute(
        select(
            UserPet.user_id,
            func.coalesce(func.sum(UserPet.affinity), 0).label("aff"),
            func.count(UserPet.id).label("cnt"),
        )
        .group_by(UserPet.user_id)
        .order_by(func.coalesce(func.sum(UserPet.affinity), 0).desc(), UserPet.user_id.asc())
    ).all()
    stats = {r[0]: (r[1] or 0, r[2] or 0) for r in rows if (r[1] or 0) > 0}
    user_map = _load_users(db, list(stats.keys()))
    scored = [(user_map[uid], aff) for uid, (aff, _cnt) in stats.items() if uid in user_map]
    scored.sort(key=lambda t: (-t[1], t[0].id))
    extras = {uid: {"pet_count": cnt} for uid, (_aff, cnt) in stats.items()}
    return ok(
        {
            "items": _user_items(scored, limit, extras),
            "total": len(scored),
            "me": _me_entry(scored, user),
        }
    )


@router.get("/game")
def game_ranking(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """游戏排行：按每个用户各小游戏最佳战绩之和倒序。"""
    rows = db.execute(
        select(
            GameRecord.user_id,
            func.coalesce(func.sum(GameRecord.best_score), 0).label("total"),
            func.count(GameRecord.id).label("cnt"),
        )
        .group_by(GameRecord.user_id)
        .order_by(func.coalesce(func.sum(GameRecord.best_score), 0).desc(), GameRecord.user_id.asc())
    ).all()
    stats = {r[0]: (r[1] or 0, r[2] or 0) for r in rows if (r[1] or 0) > 0}
    user_map = _load_users(db, list(stats.keys()))
    scored = [(user_map[uid], total) for uid, (total, _cnt) in stats.items() if uid in user_map]
    scored.sort(key=lambda t: (-t[1], t[0].id))
    extras = {uid: {"game_count": cnt} for uid, (_total, cnt) in stats.items()}
    return ok(
        {
            "items": _user_items(scored, limit, extras),
            "total": len(scored),
            "me": _me_entry(scored, user),
        }
    )


@router.get("/all")
def all_ranking(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """全部排行：金币 + 宠物亲密度 + 游戏战绩 三项总和，覆盖"其他排行之和"。

    每个子项采用与对应单独排行一致的数值（coins / 亲和度总和 / 游戏分总和），
    相加得到总分，按总分倒序；extra 里附带三项明细。
    """
    # 金币
    coin_users = db.scalars(
        select(User).options(selectinload(User.school)).where(User.is_active.is_(True))
    ).all()
    coins_map = {u.id: (u.coins or 0) for u in coin_users}
    # 亲密度
    aff_rows = db.execute(
        select(UserPet.user_id, func.coalesce(func.sum(UserPet.affinity), 0))
        .group_by(UserPet.user_id)
    ).all()
    aff_map = {r[0]: (r[1] or 0) for r in aff_rows}
    # 游戏
    game_rows = db.execute(
        select(GameRecord.user_id, func.coalesce(func.sum(GameRecord.best_score), 0))
        .group_by(GameRecord.user_id)
    ).all()
    game_map = {r[0]: (r[1] or 0) for r in game_rows}

    all_ids = set(coins_map) | set(aff_map) | set(game_map)
    user_map = _load_users(db, list(all_ids))

    scored: list[tuple[User, int]] = []
    extras: dict[int, dict] = {}
    for uid in all_ids:
        u = user_map.get(uid)
        if not u or not u.is_active:
            continue
        coins, aff, game = coins_map.get(uid, 0), aff_map.get(uid, 0), game_map.get(uid, 0)
        total = coins + aff + game
        if total <= 0:
            continue
        scored.append((u, total))
        extras[uid] = {"coins": coins, "affinity": aff, "game": game}
    scored.sort(key=lambda t: (-t[1], t[0].id))

    return ok(
        {
            "items": _user_items(scored, limit, extras),
            "total": len(scored),
            "me": _me_entry(scored, user),
        }
    )


class _GameScoreIn(BaseModel):
    game_key: str = Field(min_length=1, max_length=32)
    best_score: int = Field(ge=0, le=1_000_000)


@router.post("/game/score")
def submit_game_score(
    payload: _GameScoreIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """上报小游戏最佳战绩（Upsert：已有记录且新值更大才覆盖）。"""
    if payload.game_key not in GAME_KEYS:
        raise HTTPException(status_code=400, detail="unknown game key")
    record = db.scalar(
        select(GameRecord).where(
            GameRecord.user_id == user.id, GameRecord.game_key == payload.game_key
        )
    )
    if record is None:
        record = GameRecord(user_id=user.id, game_key=payload.game_key, best_score=payload.best_score)
        db.add(record)
    elif payload.best_score > record.best_score:
        record.best_score = payload.best_score
    db.commit()
    return ok({"ok": True, "best_score": record.best_score})
