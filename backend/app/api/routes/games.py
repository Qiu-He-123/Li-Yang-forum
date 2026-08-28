"""游戏中心（赚金币小游戏）路由。

用户侧（/games）：
- GET  /games             公开游戏列表（仅已上架）
- GET  /games/{slug}/play 返回用户自制游戏的 HTML（iframe 直接加载）
- POST /games/{slug}/reward  领取游戏金币奖励（新纪录 / 手动领取，每日限量）
- POST /games/submit      用户「制作游戏」提交（上传 HTML，待审核）

管理侧（/admin/games）：
- GET   /admin/games              全部游戏（含未上架/待审核）
- POST  /admin/games              新增游戏
- PUT   /admin/games/{id}         更新游戏（金币奖励/每日上限/排序/上下架/审核状态）
- DELETE /admin/games/{id}        删除游戏
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user
from app.core.database import get_db
from app.models import Admin, Game, User
from app.schemas.common import ok
from app.services import game_service

router = APIRouter(prefix="/games", tags=["games"])
admin_router = APIRouter(prefix="/admin/games", tags=["admin-games"])


# ==================== 用户侧 ====================


@router.get("")
def games_list(db: Session = Depends(get_db)) -> dict:
    """公开游戏列表：仅已上架（status=active 且 is_active）。"""
    return ok({"items": game_service.list_games(db)})


@router.get("/{slug}/play")
def game_play(slug: str, db: Session = Depends(get_db)) -> dict:
    """返回用户自制游戏的 HTML 源码（iframe 直接加载游玩）。"""
    game = game_service.get_game_by_slug(db, slug)
    if not game.html_content:
        raise HTTPException(status_code=404, detail="该游戏暂无在线源码")
    return ok({"slug": game.slug, "name": game.name, "html": game.html_content})


class _RewardIn(BaseModel):
    best_score: int = Field(default=0, ge=0, le=1_000_000)
    track: bool = True
    pet_product_id: int | None = Field(default=None)


@router.post("/{slug}/reward")
def game_reward(
    slug: str,
    payload: _RewardIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """领取游戏金币奖励。

    - track=True：刷新最佳战绩（新纪录）才发金币，防刷。
    - track=False：手动领取（无分数追踪的游戏），每日限量防刷。
    - 可选 pet_product_id：同局给宠物「陪我玩」发放好感（受该游戏每日好感上限约束）。
    """
    resp = game_service.claim_reward(db, user, slug, payload.best_score, payload.track)
    gained_affinity = 0
    if payload.pet_product_id:
        try:
            gained_affinity = game_service.grant_game_affinity(db, user, slug, payload.pet_product_id)
        except HTTPException:
            gained_affinity = 0
    resp["gained_affinity"] = gained_affinity
    game = game_service.get_game_by_slug(db, slug)
    resp["affinity_remaining"] = max(
        0, (getattr(game, "affinity_daily_limit", None) or 0)
        - game_service._daily_affinity_count(db, user.id, slug)
    )
    resp["affinity_limit"] = getattr(game, "affinity_daily_limit", None) or 0
    resp["coins_daily_remaining"] = resp["daily_remaining"]
    db.commit()
    return ok(resp)


@router.post("/submit")
async def game_submit(
    name: str = Form(...),
    type: str = Form("single"),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """用户「制作游戏」提交：上传 HTML 文件，后台审核通过后上架。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="文件编码不支持") from None
    if len(html) > 2_000_000:
        raise HTTPException(status_code=400, detail="游戏文件过大（限 2MB）")
    return ok(game_service.submit_game(db, user, name, type, description, html))


# ==================== 管理侧 ====================


@router.get("/{slug}/my-status")
def my_game_status(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """当前用户在该游戏的金币领取状态（今日已领/上限、最佳战绩）。"""
    from sqlalchemy import select as _select

    from app.models import GameRecord

    game = game_service.get_game_by_slug(db, slug)
    record = db.scalar(
        _select(GameRecord).where(
            GameRecord.user_id == user.id,
            GameRecord.game_key == slug,
        )
    )
    return ok(
        {
            "reward_coins": game.reward_coins,
            "daily_limit": game.daily_limit,
            "claimed_today": game_service._daily_claim_count(db, user.id, slug),
            "affinity_daily_limit": getattr(game, "affinity_daily_limit", None) or 0,
            "affinity_today": game_service._daily_affinity_count(db, user.id, slug),
            "best_score": record.best_score if record else 0,
        }
    )


class _AdminGameIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="single", pattern="^(single|multi)$")
    description: str = Field(default="", max_length=500)
    icon_url: str = Field(default="", max_length=255)
    reward_coins: int = Field(default=5, ge=0)
    daily_limit: int = Field(default=5, ge=1)
    affinity_daily_limit: int = Field(default=20, ge=0)
    sort_order: int = Field(default=0)


class _AdminGameUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, pattern="^(single|multi)$")
    description: str | None = Field(default=None, max_length=500)
    icon_url: str | None = Field(default=None, max_length=255)
    reward_coins: int | None = Field(default=None, ge=0)
    daily_limit: int | None = Field(default=None, ge=1)
    affinity_daily_limit: int | None = Field(default=None, ge=0)
    sort_order: int | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    status: str | None = Field(default=None, pattern="^(active|pending|rejected)$")


@admin_router.get("")
def admin_games_list(
    keyword: str | None = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """全部游戏（含未上架/待审核）。"""
    return ok({"items": game_service.admin_list(db, keyword)})


@admin_router.post("")
def admin_games_create(
    payload: _AdminGameIn,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    return ok(game_service.admin_create(
        db, payload.name, payload.slug, payload.type,
        payload.description, payload.icon_url,
        payload.reward_coins, payload.daily_limit,
        payload.affinity_daily_limit, payload.sort_order,
    ))


@admin_router.put("/{game_id}")
def admin_games_update(
    game_id: int,
    payload: _AdminGameUpdateIn,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    return ok(game_service.admin_update(db, game_id, **fields))


@admin_router.delete("/{game_id}")
def admin_games_delete(
    game_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    game_service.admin_delete(db, game_id)
    return ok()
