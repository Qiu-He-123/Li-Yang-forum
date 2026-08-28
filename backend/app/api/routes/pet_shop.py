"""宠物商城用户侧路由：商品列表、详情、分类、金币领养、我的宠物、互动/喂食/进化/升级方案。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import pet_shop_service

router = APIRouter(prefix="/pet-shop", tags=["pet-shop"])


@router.get("/categories")
def get_categories(
    db: Session = Depends(get_db),
) -> dict:
    """商品分类列表。"""
    return ok(pet_shop_service.list_categories(db))


@router.get("/products")
def get_products(
    category: str | None = Query(None, description="分类名称筛选"),
    keyword: str | None = Query(None, description="关键词搜索"),
    kind: int | None = Query(None, description="商品类型：1=宠物 2=道具(食物/玩具/日用/医疗) 3=进化道具"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """商品列表（仅上架商品，分页；登录用户附带 owned 已领养标记与 bag_qty 背包数量）。"""
    return ok(
        pet_shop_service.list_products(db, category, keyword, page, page_size, user=user, kind=kind)
    )


@router.get("/products/{product_id}")
def get_product_detail(
    product_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """商品详情（含 3D 模型地址 model_3d_url 与帧动画配置 anim）。"""
    return ok(pet_shop_service.get_product(db, product_id, user=user))


@router.post("/products/{product_id}/adopt")
def adopt_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """金币领养宠物（每人每只限 1 次，扣金币写流水）。"""
    return ok(pet_shop_service.adopt_product(db, user, product_id))


@router.post("/products/{product_id}/buy")
def buy_item(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """购买道具（食物/玩具/进化道具等）进背包，金币扣费。"""
    return ok(pet_shop_service.purchase_item(db, user, product_id))


@router.post("/products/{product_id}/adopt-slot")
def buy_pet_slot(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """购买"宠物领养位"：永久 +1 宠物名额，突破基础上限(MAX_OWNED_PETS=2)。"""
    return ok(pet_shop_service.purchase_pet_slot(db, user, product_id))


@router.post("/pets/{product_id}/feed")
def feed_pet(
    product_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """喂食：消耗背包食物 1 份，好感度提升（含冷却/递减/每日上限）。

    body 可传 `food_id` 指定喂哪种食物；不传则由后端自动选背包中好感加成最高的一份。
    """
    food_id = payload.get("food_id")
    food_id = int(food_id) if food_id is not None else None
    try:
        return ok(pet_shop_service.feed_pet(db, user, product_id, food_id=food_id))
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(status_code=429, content={"code": -1, "msg": e.detail, "data": None})
        raise


class PlayToyIn(BaseModel):
    toy_id: int = Field(..., description="背包中的玩具道具 id（kind=2，带 play/affinity 加成）")


@router.post("/pets/{product_id}/play")
def play_pet(
    product_id: int,
    payload: PlayToyIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """用背包玩具陪玩：消耗玩具 1 份，好感度提升（单独冷却，与摸摸/玩耍分开，延长互动节奏）。"""
    try:
        return ok(pet_shop_service.play_with_toy(db, user, product_id, toy_id=payload.toy_id))
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(status_code=429, content={"code": -1, "msg": e.detail, "data": None})
        raise


@router.post("/pets/{product_id}/interact")
def interact_pet(
    product_id: int,
    action: str = Query("pet", description="互动类型：pet=摸摸头(+1) play=玩耍(+2)"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """互动：摸摸头/玩耍，好感度提升（含冷却/递减/每日上限）。"""
    try:
        return ok(pet_shop_service.interact_pet(db, user, product_id, action=action))
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(status_code=429, content={"code": -1, "msg": e.detail, "data": None})
        raise


@router.post("/pets/{product_id}/abandon")
def abandon_pet(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """遗弃宠物：删除领养记录（好感度清零，可重新领养）。"""
    return ok(pet_shop_service.abandon_pet(db, user, product_id))


@router.get("/my-pets")
def my_pets(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我的宠物列表（含动画配置、好感度、等级/冷却/进化状态与金币余额）。"""
    return ok(pet_shop_service.my_pets(db, user))


@router.get("/user/{user_id}/pets")
def user_pets(
    user_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """某用户已领养的宠物（公开轻量信息，含动画配置，用于帖子卡片等展示他人的宠物）。"""
    return ok(pet_shop_service.user_pets_by_owner(db, user_id))


@router.get("/my-bag")
def my_bag(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """道具背包（食物/玩具/进化道具等，含数量）。"""
    return ok(pet_shop_service.my_bag(db, user))


class UseItemIn(BaseModel):
    item_id: int = Field(..., description="背包中的道具 id")


@router.post("/pets/{pet_id}/use-item")
def use_bag_item(
    pet_id: int,
    payload: UseItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """背包道具统一使用：食物喂食/玩具陪玩/日用医疗使用/进化水晶进化。

    部分操作受冷却限制（喂食 30 分钟、陪玩 10 分钟），命中时返回 429。
    """
    try:
        return ok(pet_shop_service.use_item(db, user, pet_id, payload.item_id))
    except HTTPException as e:
        if e.status_code == 429:
            return JSONResponse(status_code=429, content={"code": -1, "msg": e.detail, "data": None})
        raise


@router.get("/pets/{product_id}/plan")
def pet_upgrade_plan(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取宠物升级方案：等级路线、当前进度、下一级条件、进化所需道具。"""
    return ok(pet_shop_service.upgrade_plan(db, user, product_id))


@router.post("/pets/{product_id}/evolve")
def evolve_pet(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """超级进化：好感满100 + 消耗进化水晶 → 进化为灵魂伴侣。"""
    return ok(pet_shop_service.evolve_pet(db, user, product_id))


@router.post("/pets/{product_id}/nickname")
def set_pet_nickname(
    product_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """设置宠物昵称（进化后可自定义，最多12字）。"""
    return ok(pet_shop_service.set_pet_nickname(db, user, product_id, payload.get("nickname", "")))


@router.get("/pets/{product_id}/status")
def pet_status(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取宠物当前状态/需求（用于桌宠判断是否发出需求气泡）。"""
    return ok(pet_shop_service.pet_status(db, user, product_id))


@router.post("/pets/{product_id}/tap")
def tap_pet(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """点击宠物：爱心反馈 + 饱食度结算 + 假随机掉落（pity 保底）。"""
    return ok(pet_shop_service.tap_pet(db, user, product_id))
