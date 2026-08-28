"""宠物商城业务逻辑层（用户侧 + 管理端）。"""

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timedelta, date
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time_utils import to_iso_zh
from app.models import PetCategory, PetProduct, User, UserPet, UserPetItem
from app.services import coin_service

# DyberPet 开源项目资源目录（制作宠物用，可用环境变量覆盖）
DYBER_RES_DIR = Path(os.environ.get("DYBERPET_RES_DIR", r"D:\Users\Downloads\宠物\DyperPet\res"))
# 帧图落盘目录（与 scripts/import_dyber_pets.py 一致）
UPLOADS_PETS_DIR = Path(__file__).resolve().parents[2] / "uploads" / "pets"

# ====== 宠物等级 / 进化 配置 ======
# 等级门槛（affinity 达到即自动升级）：Lv1幼崽→Lv2幼年→Lv3少年→Lv4青年→Lv5成年→Lv6灵魂伴侣
PET_LEVELS = [
    {"level": 1, "name": "幼崽", "affinity_min": 0, "unlocks": ["stand"], "desc": "刚来到你身边的小家伙"},
    {"level": 2, "name": "幼年", "affinity_min": 20, "unlocks": ["sleep"], "desc": "开始打盹的萌宝"},
    {"level": 3, "name": "少年", "affinity_min": 40, "unlocks": ["interact"], "desc": "会互动啦，想被摸摸"},
    {"level": 4, "name": "青年", "affinity_min": 60, "unlocks": ["walk"], "desc": "活力满满，想散步玩耍"},
    {"level": 5, "name": "成年", "affinity_min": 80, "unlocks": ["fly"], "desc": "解锁全部动作，感情深厚"},
    {"level": 6, "name": "灵魂伴侣", "affinity_min": 100, "unlocks": ["evolve"], "desc": "超级进化！专属光效与昵称"},
]

# 互动冷却（秒）：服务端强制校验
COOLDOWN_PET = 300      # 摸摸头 5 分钟
COOLDOWN_FEED = 1800    # 喂食 30 分钟
COOLDOWN_PLAY = 600     # 玩耍 10 分钟
# 主动邀请"陪我玩"的最小空闲时长（秒）：距上次玩耍超过该时长才主动求陪玩，
# 用于降低主动邀玩频率（实际玩耍冷却仍为 COOLDOWN_PLAY，不影响手动玩耍频率）
NEED_PLAY_IDLE_SEC = 1800   # 30 分钟
# 每日好感上限
DAILY_AFFINITY_CAP = 20
# 好感递减系数（按当前等级：等级越高收益越少，防止刷好感）
AFFINITY_DECAY = {1: 1.0, 2: 0.9, 3: 0.75, 4: 0.6, 5: 0.4, 6: 0.25}

# ====== 饱食度配置 ======
# 每 1 小时衰减 10 点（约 10 小时从 100 降到饿虚），让"会饿/挨饿"真实可见；
# 低于 SATIETY_HUNGRY 进入饿虚状态（互动好感减半）
SATIETY_DECAY_HOURS = 1
SATIETY_DECAY_AMOUNT = 10
SATIETY_HUNGRY = 30      # 低于此值 = 饿虚（is_hungry=True）
SATIETY_FEED_RESTORE = 40  # 每次喂食恢复 40 点

# ====== 假随机掉落（pity 机制） ======
# 基础掉率 8%，连续未掉落计数每 +1 提升概率；保底：每 15 次点击必掉
DROP_BASE_RATE = 0.08
DROP_RATE_STEP = 0.01
DROP_PITY_COUNT = 15


def _calc_level(affinity: int) -> int:
    """由好感度计算等级。"""
    lv = 1
    for lvl in PET_LEVELS:
        if affinity >= lvl["affinity_min"]:
            lv = lvl["level"]
    return lv


def _now() -> datetime:
    return datetime.utcnow()


def _today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def _apply_cooldown(up: UserPet, action: str) -> dict | None:
    """检查冷却：未通过返回错误 dict（含 retry_after 秒数），通过则更新时间戳返回 None。"""
    now = _now()
    cooldowns = {
        "pet": (up.last_pet_at, COOLDOWN_PET),
        "feed": (up.last_feed_at, COOLDOWN_FEED),
        "play": (up.last_play_at, COOLDOWN_PLAY),
    }
    last, cd = cooldowns[action]
    if last is not None:
        elapsed = (now - last).total_seconds()
        if elapsed < cd:
            return {"retry_after": int(cd - elapsed), "cooldown": cd}
    # 通过则更新
    if action == "pet":
        up.last_pet_at = now
    elif action == "feed":
        up.last_feed_at = now
    elif action == "play":
        up.last_play_at = now
    return None


def _check_daily_cap(up: UserPet, gain: int) -> int:
    """检查每日好感上限，返回实际可获得的好感值（被截断则只返回到上限为止的差额）。"""
    today = _today_str()
    if up.daily_affinity_date != today:
        up.daily_affinity_date = today
        up.daily_affinity_gained = 0
    remaining = DAILY_AFFINITY_CAP - up.daily_affinity_gained
    if remaining <= 0:
        return 0
    actual = min(gain, remaining)
    up.daily_affinity_gained += actual
    return actual


def _apply_affinity(up: UserPet, raw_gain: int) -> dict:
    """应用好感度增长（递减 + 每日上限 + 自动升级），返回结果详情。"""
    level = up.level or _calc_level(up.affinity or 0)
    decay = AFFINITY_DECAY.get(level, 1.0)
    effective = max(0, int(raw_gain * decay))
    gained = _check_daily_cap(up, effective)
    old = up.affinity or 0
    up.affinity = min(100, old + gained)
    new_level = _calc_level(up.affinity)
    leveled_up = new_level > (up.level or 1)
    up.level = new_level
    return {
        "affinity": up.affinity,
        "gained": gained,
        "raw_gain": raw_gain,
        "decay": decay,
        "level": new_level,
        "leveled_up": leveled_up,
        "daily_gained": up.daily_affinity_gained,
        "daily_cap": DAILY_AFFINITY_CAP,
        "daily_remaining": max(0, DAILY_AFFINITY_CAP - up.daily_affinity_gained),
    }


def _decay_satiety(up: UserPet) -> None:
    """饱食度随时间衰减：每 4 小时 -10，最低 0。首次调用只记录时间不衰减。"""
    now = _now()
    if up.last_satiety_decay is None:
        up.last_satiety_decay = now
        return
    elapsed = (now - up.last_satiety_decay).total_seconds()
    decay_seconds = SATIETY_DECAY_HOURS * 3600
    if elapsed >= decay_seconds:
        periods = int(elapsed // decay_seconds)
        up.satiety = max(0, (up.satiety if up.satiety is not None else 100) - periods * SATIETY_DECAY_AMOUNT)
        up.last_satiety_decay = now


def _calc_mood(up: UserPet) -> str:
    """根据饱食度 + 好感计算"小情绪"，随状态返回并按养成节奏变化。"""
    satiety = up.satiety if up.satiety is not None else 100
    affinity = up.affinity or 0
    if satiety <= 0:
        return "饿晕了"
    if satiety < 30:
        return "饿肚子"
    if satiety < 60:
        return "有点饿"
    if affinity >= 80:
        return "超开心"
    if affinity >= 40:
        return "心情愉悦"
    return "乖乖的"


def _random_drop(db: Session, up: UserPet) -> dict | None:
    """假随机掉落（pity 机制）：

    - 以宠物为单位维护 interact_count；
    - streak = interact_count % DROP_PITY_COUNT，掉率 = 8% + streak × 1%；
    - 每第 15 次点击必掉（保底）；
    - 掉落池：上架中的低价食物道具（kind=2），随机一件 +1 进背包。
    """
    import random as _random

    streak = up.interact_count % DROP_PITY_COUNT
    guaranteed = streak == DROP_PITY_COUNT - 1
    rate = DROP_BASE_RATE + streak * DROP_RATE_STEP
    if not (guaranteed or _random.random() < rate):
        return None

    # 掉落池：kind=2 上架道具（优先便宜的小食物，模拟"随手捡到零食"）
    pool = db.scalars(
        select(PetProduct)
        .where(PetProduct.kind == 2, PetProduct.status == 1)
        .order_by(PetProduct.price.asc())
        .limit(6)
    ).all()
    if not pool:
        return None
    item = _random.choice(pool)

    bag_item = db.scalar(
        select(UserPetItem).where(UserPetItem.user_id == up.user_id, UserPetItem.product_id == item.id)
    )
    if bag_item:
        bag_item.qty += 1
    else:
        db.add(UserPetItem(user_id=up.user_id, product_id=item.id, qty=1))
    return {
        "item_id": item.id,
        "name": item.name,
        "image_url": item.image_url,
        "emoji": "🍱",
        "pity": guaranteed,
        "bag_qty": bag_item.qty if bag_item else 1,
    }


def tap_pet(db: Session, user: User, pet_product_id: int) -> dict:
    """点击宠物（桌宠轻点）：爱心动画 + 饱食度衰减 + 假随机掉落。

    不加好感、不占互动冷却（防止和摸摸头冲突）；掉落走 pity 假随机。
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    _decay_satiety(up)
    up.interact_count = (up.interact_count or 0) + 1
    drop = _random_drop(db, up)
    db.commit()

    satiety = up.satiety if up.satiety is not None else 100
    return {
        "satiety": satiety,
        "is_hungry": satiety < SATIETY_HUNGRY,
        "drop": drop,
        "interact_count": up.interact_count,
    }


def _json_dict(raw: str | None) -> dict:
    """安全解析商品 attrs JSON 字段（非 dict/非法时返回空 dict）。"""
    if not raw:
        return {}
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


# 道具类型 → 允许的 attrs 数值键（后台按类型只暴露这些编辑框）
_PET_ATTR_KEYS = {
    # 食物类（狗粮/猫粮/零食）：好感沿用 affinity_gain 列，这里存饱腹等
    2: {"affinity", "satiety", "mood", "play", "stamina", "health"},
    # 活体宠物 / 进化道具：一般无需数值，允许扩展（如待机间隔）
    1: {"idle_interval_sec"},
    3: {"affinity"},
}


def _clean_attrs(raw, kind: int) -> str | None:
    """规范化道具 attrs：接收 dict 或 JSON 字符串，仅保留当前类型允许的数值键。"""
    allowed = _PET_ATTR_KEYS.get(int(kind), set())
    obj: dict = {}
    if isinstance(raw, dict):
        obj = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            obj = parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            obj = {}
    out: dict[str, int] = {}
    for k, v in obj.items():
        if k not in allowed:
            continue
        try:
            num = int(v)
        except (TypeError, ValueError):
            continue
        if num < 0:
            num = 0
        out[k] = num
    return json.dumps(out, ensure_ascii=False) if out else None


def _product_dict(p: PetProduct, category_name: str = "") -> dict:
    """商品序列化（category_name 由调用方传入，避免 N+1 时重复查询）。"""
    anim = None
    if p.anim_json:
        try:
            anim = json.loads(p.anim_json)
        except (TypeError, ValueError):
            anim = None
    return {
        "id": p.id,
        "name": p.name,
        "category_id": p.category_id,
        "category": category_name,
        "price": float(p.price) if p.price is not None else 0.0,
        "original_price": float(p.original_price) if p.original_price is not None else None,
        "stock": p.stock,
        "image_url": p.image_url,
        # 兼容字段：前端 image = image_url（可能为 emoji 占位符）
        "image": p.image_url,
        "model_3d_url": p.model_3d_url,
        # 帧动画配置（DyberPet 像素宠物），无则为 null
        "anim": anim,
        "description": p.description,
        "sales": p.sales,
        "status": p.status,
        # 1=活体宠物（限领1只） 2=食物/玩具/日用/医疗道具 3=进化道具
        "kind": p.kind or 1,
        # 喂食加好感数值（仅 kind=2 食物道具）
        "affinity_gain": (p.affinity_gain or 0) if (p.kind or 1) == 2 else 0,
        # 宠物是否能飞行（kind=1 活体宠物）：自动触发"上抛悬空再落回"行为
        "can_fly": bool(p.can_fly),
        # 道具按类型定制的数值字段（JSON: 好感/饱腹/心情/玩耍/体力/健康等）
        "attrs": _json_dict(p.attrs),
        # 陪我玩「动作→宠物说话」常量 JSON（自定义宠物选填，与人设 ai_persona 同块编辑；空则前端用默认）
        "ai_persona": p.ai_persona,
        "game_speech": p.game_speech,
        "created_at": to_iso_zh(p.created_at) if p.created_at else None,
    }


def _user_pet_dict(up: UserPet, p: PetProduct, category_name: str) -> dict:
    """用户宠物序列化（含等级/进化/冷却/每日上限/饱食度等状态）。"""
    d = _product_dict(p, category_name)
    now = _now()
    # 序列化前先结算饱食度衰减
    _decay_satiety(up)

    def _cd(last, cd):
        if last is None:
            return 0
        elapsed = (now - last).total_seconds()
        return max(0, int(cd - elapsed))

    cooldowns = {
        "pet": _cd(up.last_pet_at, COOLDOWN_PET),
        "feed": _cd(up.last_feed_at, COOLDOWN_FEED),
        "play": _cd(up.last_play_at, COOLDOWN_PLAY),
    }
    cur_level = up.level or _calc_level(up.affinity or 0)
    level_info = PET_LEVELS[cur_level - 1]
    next_level = PET_LEVELS[cur_level] if cur_level < len(PET_LEVELS) else None
    satiety = up.satiety if up.satiety is not None else 100
    return {
        **d,
        "adopted_at": to_iso_zh(up.created_at) if up.created_at else None,
        "affinity": up.affinity or 0,
        "level": cur_level,
        "level_name": level_info["name"],
        "level_desc": level_info["desc"],
        "evolved": bool(up.evolved),
        "evolved_at": to_iso_zh(up.evolved_at) if up.evolved_at else None,
        "nickname": up.nickname,
        "satiety": satiety,
        "is_hungry": satiety < SATIETY_HUNGRY,
        "mood": _calc_mood(up),
        "cooldowns": cooldowns,
        "daily_affinity": {
            "date": up.daily_affinity_date,
            "gained": up.daily_affinity_gained or 0,
            "cap": DAILY_AFFINITY_CAP,
            "remaining": max(0, DAILY_AFFINITY_CAP - (up.daily_affinity_gained or 0)),
        },
        "next_level": {
            "level": next_level["level"],
            "name": next_level["name"],
            "affinity_needed": next_level["affinity_min"] - (up.affinity or 0),
            "desc": next_level["desc"],
            "unlocks": next_level["unlocks"],
        } if next_level else None,
    }


def _category_dict(c: PetCategory) -> dict:
    return {"id": c.id, "name": c.name, "icon": c.icon, "sort_order": c.sort_order}


def list_categories(db: Session) -> list[dict]:
    """分类列表（按 sort_order 排序）。"""
    rows = db.scalars(select(PetCategory).order_by(PetCategory.sort_order, PetCategory.id)).all()
    return [_category_dict(c) for c in rows]


def _resolve_category_map(db: Session) -> dict[int, str]:
    return {c.id: c.name for c in db.scalars(select(PetCategory)).all()}


def list_products(
    db: Session,
    category: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    only_on_shelf: bool = True,
    user: User | None = None,
    kind: int | None = None,
) -> dict:
    """商品列表（分页 + 分类/关键词/类型筛选）。category 传分类名称。登录用户附带 owned 与背包数量。"""
    query = select(PetProduct)
    if category:
        cat = db.scalar(select(PetCategory).where(PetCategory.name == category))
        if not cat:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        query = query.where(PetProduct.category_id == cat.id)
    if kind is not None:
        query = query.where(PetProduct.kind == kind)
    if only_on_shelf:
        query = query.where(PetProduct.status == 1)
    if keyword:
        query = query.where(PetProduct.name.contains(keyword))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    # 「全部」浏览（无分类筛选）时宠物排在道具前面，其余保持 id 倒序
    if category is None:
        order = [(PetProduct.kind == 1).desc(), PetProduct.id.desc()]
    else:
        order = [PetProduct.id.desc()]
    rows = db.scalars(
        query.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    cat_map = _resolve_category_map(db)
    owned_ids = _owned_pet_product_ids(db, user.id) if user else set()
    bag_map = _bag_qty_map(db, user.id) if user else {}
    return {
        "items": [
            {
                **_product_dict(p, cat_map.get(p.category_id, "")),
                "owned": p.id in owned_ids,
                "bag_qty": bag_map.get(p.id, 0),
            }
            for p in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def get_product(db: Session, product_id: int, is_admin: bool = False, user: User | None = None) -> dict:
    """商品详情（下架商品仅管理员可见）。登录用户附带 owned 标记。"""
    p = db.get(PetProduct, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    if p.status != 1 and not is_admin:
        raise HTTPException(status_code=404, detail="商品不存在或已下架")
    cat = db.get(PetCategory, p.category_id)
    d = _product_dict(p, cat.name if cat else "")
    if user:
        d["owned"] = p.id in _owned_pet_product_ids(db, user.id)
    return d


# ============ 宠物领养（金币购买） ============


def _owned_pet_product_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(select(UserPet.product_id).where(UserPet.user_id == user_id)).all()
    )


def _bag_qty_map(db: Session, user_id: int) -> dict[int, int]:
    """背包数量映射：product_id -> qty。"""
    rows = db.execute(
        select(UserPetItem.product_id, UserPetItem.qty).where(UserPetItem.user_id == user_id)
    ).all()
    return {pid: qty for pid, qty in rows if qty > 0}


def my_pets(db: Session, user: User) -> dict:
    """我的宠物列表（按领养时间倒序，含商品完整信息 + 动画配置 + 好感度 + 等级/冷却/进化状态）。"""
    rows = db.execute(
        select(UserPet, PetProduct)
        .join(PetProduct, UserPet.product_id == PetProduct.id)
        .where(UserPet.user_id == user.id)
        .order_by(UserPet.id.desc())
    ).all()
    cat_map = _resolve_category_map(db)
    items = []
    for up, p in rows:
        # 回填等级（防止老数据 level 为 0/None）
        if not up.level:
            up.level = _calc_level(up.affinity or 0)
        items.append(_user_pet_dict(up, p, cat_map.get(p.category_id, "")))
    db.commit()
    # 已养数量 / 上限（含已购领养位）：前端"我的宠物"页展示"已养 x / 上限 y"
    owned = len(items)
    return {
        "items": items,
        "total": owned,
        "owned": owned,
        "limit": MAX_OWNED_PETS + (user.pet_extra_slots or 0),
        "extra_slots": user.pet_extra_slots or 0,
        "coins": coin_service.get_balance(db, user.id),
    }


def user_pets_by_owner(db: Session, owner_user_id: int) -> dict:
    """某用户已领养的宠物（公开轻量信息，含动画配置，用于帖子卡片等展示他人的宠物）。"""
    rows = db.execute(
        select(UserPet, PetProduct)
        .join(PetProduct, UserPet.product_id == PetProduct.id)
        .where(UserPet.user_id == owner_user_id)
        .order_by(UserPet.id.desc())
    ).all()
    cat_map = _resolve_category_map(db)
    items = []
    for up, p in rows:
        d = _product_dict(p, cat_map.get(p.category_id, ""))
        level = up.level or _calc_level(up.affinity or 0)
        items.append({
            "id": d["id"],
            "name": d["name"],
            "nickname": up.nickname,
            "anim": d["anim"],
            "image_url": d["image_url"],
            "level": level,
            "level_name": PET_LEVELS[level - 1]["name"] if 0 < level <= len(PET_LEVELS) else "",
            "evolved": bool(up.evolved),
        })
    return {"items": items, "total": len(items)}


# ============ 道具背包 / 好感度 ============


def purchase_item(db: Session, user: User, product_id: int, qty: int = 1) -> dict:
    """购买道具进背包：kind=2 食物/玩具/日用/医疗（可多份），kind=3 进化道具（限1份持有）。"""
    p = db.get(PetProduct, product_id)
    if not p or p.status != 1:
        raise HTTPException(status_code=404, detail="商品不存在或已下架")
    kind = p.kind or 1
    if kind not in (2, 3):
        raise HTTPException(status_code=400, detail="该商品不是道具")
    if kind == 3:
        # 进化道具：背包最多持有 1 个
        existing = db.scalar(
            select(UserPetItem).where(UserPetItem.user_id == user.id, UserPetItem.product_id == p.id)
        )
        if existing and existing.qty > 0:
            raise HTTPException(status_code=400, detail="你已经拥有这个进化道具了")
        qty = 1
    else:
        qty = max(1, min(99, qty))
    if p.stock < qty:
        raise HTTPException(status_code=400, detail="库存不足")
    price = int(p.price) if p.price else 0
    if price <= 0:
        raise HTTPException(status_code=400, detail="该道具暂不支持购买")

    coin_service.charge_coins(
        db,
        user,
        price * qty,
        "pet_item_buy",
        ref_id=str(p.id),
        description=f"购买道具：{p.name} ×{qty}",
    )
    p.stock -= qty
    p.sales += qty
    item = db.scalar(
        select(UserPetItem).where(UserPetItem.user_id == user.id, UserPetItem.product_id == p.id)
    )
    if item:
        item.qty += qty
    else:
        db.add(UserPetItem(user_id=user.id, product_id=p.id, qty=qty))
    db.commit()

    cat = db.get(PetCategory, p.category_id)
    return {
        "item": {**_product_dict(p, cat.name if cat else ""), "bag_qty": _bag_qty_map(db, user.id).get(p.id, 0)},
        "coins": coin_service.get_balance(db, user.id),
    }


def purchase_pet_slot(db: Session, user: User, product_id: int, qty: int = 1) -> dict:
    """购买"宠物领养位"：kind=4 商品，购买一个永久 +1 宠物名额（不入背包，直接累加到 pet_extra_slots）。

    校验：商品存在且上架 / 库存充足 / 金币充足；扣费走 coin_service，写入 pet_slot 流水。
    """
    p = db.get(PetProduct, product_id)
    if not p or p.status != 1:
        raise HTTPException(status_code=404, detail="商品不存在或已下架")
    if (p.kind or 1) != 4:
        raise HTTPException(status_code=400, detail="该商品不是宠物领养位")
    qty = max(1, min(99, int(qty)))
    if p.stock < qty:
        raise HTTPException(status_code=400, detail="库存不足")
    price = int(p.price) if p.price else 0
    if price <= 0:
        raise HTTPException(status_code=400, detail="该商品暂不支持购买")

    coin_service.charge_coins(
        db,
        user,
        price * qty,
        "pet_slot_buy",
        ref_id=str(p.id),
        description=f"购买宠物领养位 ×{qty}",
    )
    p.stock -= qty
    p.sales += qty
    user.pet_extra_slots = (user.pet_extra_slots or 0) + qty
    db.commit()

    cat = db.get(PetCategory, p.category_id)
    return {
        "product": _product_dict(p, cat.name if cat else ""),
        "pet_extra_slots": user.pet_extra_slots,
        "max_owned": MAX_OWNED_PETS + (user.pet_extra_slots or 0),
        "coins": coin_service.get_balance(db, user.id),
    }


def feed_pet(db: Session, user: User, pet_product_id: int, food_id: int | None = None) -> dict:
    """喂食：消耗背包食物 1 份，好感度 +affinity_gain（含递减/每日上限/冷却，封顶 100）。

    - 冷却：30 分钟一次喂食（模拟真实进食频率）
    - 递减：等级越高单次收益越少
    - 每日上限：每只宠物每日最多获得 20 好感
    food_id 为空时自动选背包中好感加成最高的一份（用户点"喂食"默认路径）。
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    # 冷却校验
    cd_err = _apply_cooldown(up, "feed")
    if cd_err:
        db.rollback()
        raise HTTPException(status_code=429, detail={"msg": "宠物还不饿呢，稍后再来喂吧~", "retry_after": cd_err["retry_after"]})

    bag = _bag_qty_map(db, user.id)
    if not bag:
        db.rollback()
        raise HTTPException(status_code=400, detail="背包空空的，先去商城买点零食吧")

    # 选食物：指定 id 或加成最高的
    if food_id is not None and food_id in bag:
        food = db.get(PetProduct, food_id)
    else:
        foods = db.scalars(
            select(PetProduct).where(PetProduct.id.in_(bag.keys()), PetProduct.kind == 2)
        ).all()
        if not foods:
            db.rollback()
            raise HTTPException(status_code=400, detail="背包里没有可喂的食物")
        food = max(foods, key=lambda f: f.affinity_gain or 0)

    gain_raw = food.affinity_gain or 5
    # 扣 1 份
    item = db.scalar(
        select(UserPetItem).where(
            UserPetItem.user_id == user.id, UserPetItem.product_id == food.id
        )
    )
    item.qty -= 1
    if item.qty <= 0:
        db.delete(item)

    # 饱食度恢复（饿虚状态下喂食先救回来）；优先读后台自定义 attrs.satiety，未配则用默认值
    _decay_satiety(up)
    old_satiety = up.satiety if up.satiety is not None else 100
    satiety_gain = _json_dict(food.attrs).get("satiety") or SATIETY_FEED_RESTORE
    up.satiety = min(100, old_satiety + int(satiety_gain))

    # 应用好感度（递减 + 每日上限 + 升级检测）
    result = _apply_affinity(up, gain_raw)
    # 好感满 100 且未进化 → 提示可以进化
    can_evolve = up.affinity >= 100 and not up.evolved
    db.commit()

    return {
        **result,
        "food": _product_dict(food),
        "bag": my_bag(db, user)["items"],
        "can_evolve": can_evolve,
        "satiety": up.satiety,
        "is_hungry": up.satiety < SATIETY_HUNGRY,
    }


def _consume_bag_item(db: Session, user_id: int, product_id: int) -> UserPetItem:
    """扣减背包道具 1 份（数量归零即删除记录），返回被扣的记录（调用方需自行 commit）。"""
    item = db.scalar(
        select(UserPetItem).where(
            UserPetItem.user_id == user_id, UserPetItem.product_id == product_id
        )
    )
    if not item or item.qty <= 0:
        raise HTTPException(status_code=400, detail="背包里没有这个道具了")
    item.qty -= 1
    if item.qty <= 0:
        db.delete(item)
        db.flush()
    return item


def play_with_toy(db: Session, user: User, pet_product_id: int, toy_id: int) -> dict:
    """用背包里的玩具陪玩：消耗玩具 1 份，好感度提升。

    - 冷却：与「玩耍」共用 10 分钟（避免反复刷好感）
    - 收益：优先用道具 attrs.play（玩具对应趣味值），配不到则用 affinity_gain，兜底 +3
    - 递减 / 每日上限 / 封顶 100 与喂食一致
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    cd_err = _apply_cooldown(up, "play")
    if cd_err:
        db.rollback()
        raise HTTPException(status_code=429, detail={"msg": "刚玩过啦，让它歇会儿吧~", "retry_after": cd_err["retry_after"]})

    toy = db.get(PetProduct, toy_id)
    if not toy or (toy.kind or 1) != 2:
        db.rollback()
        raise HTTPException(status_code=404, detail="玩具不存在")
    bag = _bag_qty_map(db, user.id)
    if toy_id not in bag or bag[toy_id] <= 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="背包里没有这个玩具")

    attrs = _json_dict(toy.attrs)
    # 玩具趣味值优先，配不到回退 affinity_gain，兜底 +3
    gain_raw = int(attrs.get("play") or 0) or (toy.affinity_gain or 0) or 3
    _consume_bag_item(db, user.id, toy_id)

    result = _apply_affinity(up, gain_raw)
    can_evolve = up.affinity >= 100 and not up.evolved
    db.commit()
    return {
        **result,
        "toy": _product_dict(toy),
        "bag": my_bag(db, user)["items"],
        "can_evolve": can_evolve,
    }


def interact_pet(db: Session, user: User, pet_product_id: int, action: str = "pet") -> dict:
    """互动（摸摸头 pet / 玩耍 play）：好感度 +1 基础值（含递减/每日上限/冷却）。

    - 摸摸头：5 分钟冷却，基础 +1
    - 玩耍：10 分钟冷却，基础 +2（玩耍有行走动画，收益略高）
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    if action not in ("pet", "play"):
        action = "pet"

    # 冷却校验
    cd_err = _apply_cooldown(up, action)
    if cd_err:
        db.rollback()
        action_name = "摸摸" if action == "pet" else "玩耍"
        raise HTTPException(status_code=429, detail={"msg": f"宠物刚被{action_name}过，让它歇会儿吧~", "retry_after": cd_err["retry_after"]})

    base_gain = 1 if action == "pet" else 2
    result = _apply_affinity(up, base_gain)
    can_evolve = up.affinity >= 100 and not up.evolved
    db.commit()
    return {**result, "can_evolve": can_evolve}


def abandon_pet(db: Session, user: User, pet_product_id: int) -> dict:
    """遗弃宠物：删除领养记录（好感度清零，可重新领养）。"""
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    p = db.get(PetProduct, pet_product_id)
    name = p.name if p else ""
    db.delete(up)
    db.commit()
    left = len(my_pets(db, user)["items"])
    return {"abandoned": pet_product_id, "name": name, "pets_left": left}


def my_bag(db: Session, user: User) -> dict:
    """道具背包：食物/玩具/进化道具等（含数量）。kind=3 进化道具也在背包中。"""
    rows = db.execute(
        select(UserPetItem, PetProduct)
        .join(PetProduct, UserPetItem.product_id == PetProduct.id)
        .where(UserPetItem.user_id == user.id, UserPetItem.qty > 0)
        .order_by(UserPetItem.id.desc())
    ).all()
    cat_map = _resolve_category_map(db)
    items = [
        {**_product_dict(p, cat_map.get(p.category_id, "")), "qty": it.qty}
        for it, p in rows
    ]
    total_qty = sum(it.qty for it, _ in rows)
    return {"items": items, "total": len(items), "total_qty": total_qty}


# ============ 宠物升级方案 / 进化 / 状态 / 需求 ============


def use_item(db: Session, user: User, pet_product_id: int, item_id: int) -> dict:
    """背包道具统一使用（背包页）：食物喂食、玩具陪玩、日用/医疗使用、进化水晶进化。

    区分规则：
    - kind=3 → 进化水晶：好感满100 => 消耗进化（否则报错）
    - kind=2 且带 satiety 或属于食物分类（零食/狗粮/猫粮）→ 喂食
    - kind=2 且带 play → 用玩具陪玩
    - 其余 kind=2 → 通用使用：消耗道具并按 attrs 生效（好感/健康/体力/心情）
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    pet = db.get(PetProduct, pet_product_id)
    item = db.get(PetProduct, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="道具不存在")
    bag = _bag_qty_map(db, user.id)
    if item_id not in bag or bag[item_id] <= 0:
        raise HTTPException(status_code=400, detail="背包里没有这个道具")

    item_cat = db.get(PetCategory, item.category_id).name if item.category_id else ""
    attrs = _json_dict(item.attrs)
    kind = item.kind or 1
    pet_cat = db.get(PetCategory, pet.category_id).name if pet and pet.category_id else ""

    # 进化水晶
    if kind == 3:
        evo = evolve_pet(db, user, pet_product_id)
        return {
            "message": f"使用了「{item.name}」，{evo.get('msg', '进化成功')}",
            "bag": my_bag(db, user)["items"],
            "pet": evo.get("pet") or _user_pet_dict(up, pet, pet_cat),
            "can_evolve": False,
            "evolved": True,
        }

    if kind != 2:
        raise HTTPException(status_code=400, detail="该道具无法使用")

    # 食物
    is_food = bool(attrs.get("satiety")) or item_cat in ("零食", "狗粮", "猫粮")
    if is_food:
        res = feed_pet(db, user, pet_product_id, food_id=item_id)
        msg = f"喂食了「{item.name}」，饱食度+{int(attrs.get('satiety') or 0)}"
        if res.get("gained"):
            msg += f"，好感+{res['gained']}"
        return {**_res_normalize(res, db, user, pet_product_id), "message": msg}

    # 玩具
    if int(attrs.get("play") or 0) > 0:
        res = play_with_toy(db, user, pet_product_id, toy_id=item_id)
        msg = f"用「{item.name}」陪宠物玩，好感+{res.get('gained', 0)}"
        return {**_res_normalize(res, db, user, pet_product_id), "message": msg}

    # 通用使用（日用/医疗等）
    _consume_bag_item(db, user.id, item_id)
    effects: list[str] = []
    gain = int(attrs.get("affinity") or 0) or (item.affinity_gain or 0)
    affinity_res = None
    if gain > 0:
        affinity_res = _apply_affinity(up, gain)
        effects.append(f"好感+{affinity_res['gained']}")
    resf = int(attrs.get("health") or 0)
    ress = int(attrs.get("stamina") or 0)
    resm = int(attrs.get("mood") or 0)
    if resf > 0:
        effects.append(f"健康+{resf}")
    if ress > 0:
        effects.append(f"体力+{ress}")
    if resm > 0:
        effects.append(f"心情+{resm}")

    # 调用方需提交 _consume_bag_item 的变更
    db.commit()
    msg = f"使用了「{item.name}」" + (f"，{'、'.join(effects)}" if effects else "，暂无效果")
    return {
        "message": msg,
        "bag": my_bag(db, user)["items"],
        "pet": _user_pet_dict(up, pet, pet_cat),
        "result": affinity_res,
        "can_evolve": (up.affinity or 0) >= 100 and not up.evolved,
    }


def _res_normalize(res: dict, db: Session, user: User, pet_product_id: int) -> dict:
    """把 feed/play 的返回值规范化为背包页可用的字段（bag + pet 状态）。"""
    up = db.scalar(select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id))
    pet = db.get(PetProduct, pet_product_id)
    pet_cat = db.get(PetCategory, pet.category_id).name if pet and pet.category_id else ""
    return {
        "bag": my_bag(db, user)["items"],
        "pet": _user_pet_dict(up, pet, pet_cat) if up else None,
        "result": {"gained": res.get("gained", 0)},
        "can_evolve": bool(res.get("can_evolve")),
        "satiety": res.get("satiety"),
    }


def upgrade_plan(db: Session, user: User, pet_product_id: int) -> dict:
    """获取宠物的升级方案（当前等级、下一级条件、进化条件等）。"""
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    p = db.get(PetProduct, pet_product_id)
    cat = db.get(PetCategory, p.category_id) if p else None
    pet_dict = _user_pet_dict(up, p, cat.name if cat else "")

    # 构建升级路线
    plan_steps = []
    for i, lv in enumerate(PET_LEVELS):
        is_current = (up.level or 1) == lv["level"]
        is_reached = (up.level or 1) >= lv["level"]
        step = {
            "level": lv["level"],
            "name": lv["name"],
            "affinity_required": lv["affinity_min"],
            "desc": lv["desc"],
            "unlocks": lv["unlocks"],
            "is_current": is_current,
            "is_reached": is_reached,
        }
        # Lv6 需要进化道具
        if lv["level"] == 6:
            # 检查背包是否有进化水晶
            crystal = db.scalar(
                select(UserPetItem)
                .join(PetProduct, UserPetItem.product_id == PetProduct.id)
                .where(
                    UserPetItem.user_id == user.id,
                    PetProduct.kind == 3,
                    UserPetItem.qty > 0,
                )
            )
            step["evolution_item_required"] = True
            step["has_evolution_item"] = crystal is not None
        plan_steps.append(step)

    return {
        "pet": pet_dict,
        "plan": plan_steps,
        "evolved": bool(up.evolved),
    }


def evolve_pet(db: Session, user: User, pet_product_id: int) -> dict:
    """超级进化：好感满100 + 消耗1个进化水晶 → 宠物进化为Lv6灵魂伴侣。"""
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    if up.evolved:
        raise HTTPException(status_code=400, detail="这只宠物已经进化过啦")
    if (up.affinity or 0) < 100:
        raise HTTPException(status_code=400, detail="好感度未满100，还不能进化哦")

    # 查找并消耗进化水晶
    crystal_item = db.scalar(
        select(UserPetItem)
        .join(PetProduct, UserPetItem.product_id == PetProduct.id)
        .where(
            UserPetItem.user_id == user.id,
            PetProduct.kind == 3,
            UserPetItem.qty > 0,
        )
    )
    if not crystal_item:
        raise HTTPException(status_code=400, detail="背包中没有进化水晶，去商城购买吧")

    crystal_item.qty -= 1
    if crystal_item.qty <= 0:
        db.delete(crystal_item)

    up.evolved = True
    up.evolved_at = _now()
    up.level = 6
    db.commit()

    p = db.get(PetProduct, pet_product_id)
    cat = db.get(PetCategory, p.category_id) if p else None
    return {
        "pet": _user_pet_dict(up, p, cat.name if cat else ""),
        "evolved": True,
        "msg": f"恭喜！{up.nickname or p.name}成功进化为灵魂伴侣！🎉",
    }


def set_pet_nickname(db: Session, user: User, pet_product_id: int, nickname: str) -> dict:
    """设置宠物昵称（进化后可自定义）。"""
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    nickname = (nickname or "").strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="昵称不能为空")
    if len(nickname) > 12:
        raise HTTPException(status_code=400, detail="昵称最多12个字")
    up.nickname = nickname
    db.commit()
    return {"nickname": nickname}


def pet_status(db: Session, user: User, pet_product_id: int) -> dict:
    """获取宠物当前状态（用于桌宠判断是否发出需求气泡）。
    返回：当前需求（hungry/playful/lonely/none）+ 冷却剩余 + 好感 + 等级。
    """
    up = db.scalar(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_product_id)
    )
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")
    p = db.get(PetProduct, pet_product_id)
    now = _now()

    def _cd(last, cd):
        if last is None:
            return 0
        return max(0, int(cd - (now - last).total_seconds()))

    cds = {
        "pet": _cd(up.last_pet_at, COOLDOWN_PET),
        "feed": _cd(up.last_feed_at, COOLDOWN_FEED),
        "play": _cd(up.last_play_at, COOLDOWN_PLAY),
    }

    # 饱食度结算（饿虚状态优先发"饿了"需求）
    _decay_satiety(up)
    satiety = up.satiety if up.satiety is not None else 100
    is_hungry = satiety < SATIETY_HUNGRY

    # 确定当前最紧迫的需求（真实状态驱动：低饱食度才想吃，久未互动才邀请玩）。
    # 关键：只有"该项互动的冷却已过"(cd<=0)才会发出对应需求，避免"弹出想要摸摸/喂食，
    # 点了却说冷却中"的自相矛盾。
    import random
    need = "none"
    # 每日好感已到上限：不再主动求摸/求陪玩（点了也只能获得 0 好感，且会误显示"刚刚摸过"）。
    # 喂食（feed）不在此列：它主要解决饥饿，不受好感上限约束。
    aff_today = up.daily_affinity_gained or 0
    if up.daily_affinity_date != _today_str():
        aff_today = 0
    aff_remaining = DAILY_AFFINITY_CAP - aff_today
    # 饿虚状态：必发"饿了"（但若刚喂过、喂食冷却中则不能引导点击，返回 none）
    if is_hungry and cds["feed"] <= 0:
        need = "feed"
    else:
        needs = []
        # 只有低饱食度(30~60)才会想吃东西；越饿越想吃。饱食度≥60 不再主动要饭。喂食冷却中不引导。
        if satiety < 60 and cds["feed"] <= 0:
            weight = max(0.05, round(0.55 * (60 - satiety) / 30, 2))
            needs.append(("feed", weight))
        # 好久没陪玩 / 好久没摸摸（冷却已过）→ 邀请玩耍 / 求摸
        # 主动求陪玩频率降低：需距上次玩耍超过 NEED_PLAY_IDLE_SEC(30min) 才邀请，且权重下调
        play_idle = 999999.0
        if up.last_play_at is not None:
            play_idle = (now - up.last_play_at).total_seconds()
        if cds["play"] <= 0 and play_idle >= NEED_PLAY_IDLE_SEC and aff_remaining > 0:
            needs.append(("play", 0.2))
        if cds["pet"] <= 0 and aff_remaining > 0:
            needs.append(("pet", 0.35))
        if needs:
            total_w = sum(w for _, w in needs)
            r = random.random() * total_w
            acc = 0
            for n, w in needs:
                acc += w
                if r <= acc:
                    need = n
                    break

    cat = db.get(PetCategory, p.category_id) if p else None
    pet_dict = _user_pet_dict(up, p, cat.name if cat else "")
    db.commit()
    return {
        "pet": pet_dict,
        "need": need,
        "cooldowns": cds,
        "satiety": satiety,
        "is_hungry": is_hungry,
        "mood": _calc_mood(up),
    }


# 每人最多拥有的活体宠物数量（基础额度，避免一人囤一堆宠物，1~2 只足够）
# 用户可通过购买"宠物领养位"商品（kind=4）额外 +1 名额，突破此上限
MAX_OWNED_PETS = 2


def adopt_product(db: Session, user: User, product_id: int) -> dict:
    """金币领养宠物（每人限领 MAX_OWNED_PETS + 已购领养位 只，且每只限 1 次）。

    校验：商品存在且上架 / 库存>0 / 未重复领养 / 拥有数未达可用上限 / 金币充足；
    扣费走 coin_service（写 coin_transactions 流水），扣库存、记销量、写 user_pets。
    """
    p = db.get(PetProduct, product_id)
    if not p or p.status != 1:
        raise HTTPException(status_code=404, detail="宠物不存在或已下架")
    already = db.scalar(
        select(UserPet.id).where(UserPet.user_id == user.id, UserPet.product_id == p.id)
    )
    if already:
        raise HTTPException(status_code=400, detail="你已经领养过这只宠物啦")
    if p.stock <= 0:
        raise HTTPException(status_code=400, detail="这只宠物已经被领养完了")
    # 活体宠物数量上限：kind=1 才算宠物（食物/玩具/进化道具进入背包不占用名额）
    owned_pets = db.scalar(
        select(func.count(UserPet.id))
        .select_from(UserPet)
        .join(PetProduct, UserPet.product_id == PetProduct.id)
        .where(UserPet.user_id == user.id, PetProduct.kind == 1)
    ) or 0
    max_owned = MAX_OWNED_PETS + (user.pet_extra_slots or 0)
    if owned_pets >= max_owned:
        raise HTTPException(
            status_code=400,
            detail=f"你已经有 {owned_pets} 只宠物啦，最多同时养 {max_owned} 只；可以先放弃一只，或到商城购买『宠物领养位』扩充",
        )
    price = int(p.price) if p.price else 0
    if price <= 0:
        raise HTTPException(status_code=400, detail="该宠物暂不支持领养")

    coin_service.charge_coins(
        db,
        user,
        price,
        "pet_adopt",
        ref_id=str(p.id),
        description=f"领养宠物：{p.name}",
    )
    p.stock -= 1
    p.sales += 1
    db.add(UserPet(user_id=user.id, product_id=p.id))
    db.commit()

    cat = db.get(PetCategory, p.category_id)
    return {
        "pet": _product_dict(p, cat.name if cat else ""),
        "coins": coin_service.get_balance(db, user.id),
    }


# ============ 管理端 ============


def admin_list_products(
    db: Session,
    keyword: str | None = None,
    category: str | None = None,
    status: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """管理端商品列表（含下架商品）。"""
    query = select(PetProduct)
    if keyword:
        query = query.where(PetProduct.name.contains(keyword))
    if category:
        cat = db.scalar(select(PetCategory).where(PetCategory.name == category))
        if not cat:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        query = query.where(PetProduct.category_id == cat.id)
    if status is not None:
        query = query.where(PetProduct.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(PetProduct.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    cat_map = _resolve_category_map(db)
    items = []
    for p in rows:
        d = _product_dict(p, cat_map.get(p.category_id, ""))
        # 管理端补充：商品类型 + AI 设定（宠物 AI 管理，与商品"放一起"）
        d["kind"] = p.kind or 1
        d["ai_enabled"] = bool(p.ai_enabled)
        d["ai_wake_enabled"] = bool(p.ai_wake_enabled)
        d["ai_persona"] = p.ai_persona
        items.append(d)
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _get_or_create_category(db: Session, name: str) -> PetCategory:
    cat = db.scalar(select(PetCategory).where(PetCategory.name == name))
    if cat:
        return cat
    max_order = db.scalar(select(func.max(PetCategory.sort_order))) or 0
    cat = PetCategory(name=name, sort_order=max_order + 1)
    db.add(cat)
    db.flush()
    return cat


def _parse_price(value, field: str) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"请输入有效的{field}") from None
    if price < 0:
        raise HTTPException(status_code=400, detail=f"{field}不能为负数")
    return price


def admin_create_product(db: Session, payload: dict, admin_id: int) -> dict:
    """新增商品。"""
    name = (payload.get("name") or "").strip()
    category_name = (payload.get("category") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写商品名称")
    if not category_name:
        raise HTTPException(status_code=400, detail="请选择商品分类")
    price = _parse_price(payload.get("price", 0), "售价")
    original_price = payload.get("original_price")
    original_price = _parse_price(original_price, "原价") if original_price else None
    stock = int(payload.get("stock") or 0)
    if stock < 0:
        raise HTTPException(status_code=400, detail="库存不能为负数")

    kind = int(payload.get("kind") or 1)
    if kind not in (1, 2, 3):
        kind = 1
    affinity_gain = int(payload.get("affinity_gain") or 0)
    if affinity_gain < 0:
        raise HTTPException(status_code=400, detail="好感加成不能为负数")

    can_fly = bool(payload.get("can_fly"))
    cat = _get_or_create_category(db, category_name)
    product = PetProduct(
        name=name,
        category_id=cat.id,
        price=price,
        original_price=original_price,
        stock=stock,
        image_url=(payload.get("image_url") or "").strip() or None,
        model_3d_url=(payload.get("model_3d_url") or "").strip() or None,
        description=(payload.get("description") or "").strip() or None,
        status=1 if payload.get("status", 1) == 1 else 0,
        kind=kind,
        affinity_gain=affinity_gain if kind == 2 else 0,
        can_fly=can_fly if kind == 1 else False,
        attrs=_clean_attrs(payload.get("attrs"), kind),
        created_by=admin_id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _product_dict(product, cat.name)


def admin_update_product(db: Session, product_id: int, payload: dict) -> dict:
    """编辑商品。"""
    p = db.get(PetProduct, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="商品名称不能为空")
        p.name = name
    cat_name = None
    if "category" in payload and payload.get("category"):
        cat_name = (payload.get("category") or "").strip()
        cat = _get_or_create_category(db, cat_name)
        p.category_id = cat.id
        cat_name = cat.name
    if "price" in payload and payload.get("price") is not None:
        p.price = _parse_price(payload.get("price"), "售价")
    if "original_price" in payload:
        op = payload.get("original_price")
        p.original_price = _parse_price(op, "原价") if op else None
    if "stock" in payload and payload.get("stock") is not None:
        stock = int(payload.get("stock"))
        if stock < 0:
            raise HTTPException(status_code=400, detail="库存不能为负数")
        p.stock = stock
    if "image_url" in payload:
        p.image_url = (payload.get("image_url") or "").strip() or None
    if "model_3d_url" in payload:
        p.model_3d_url = (payload.get("model_3d_url") or "").strip() or None
    if "description" in payload:
        p.description = (payload.get("description") or "").strip() or None
    if "status" in payload and payload.get("status") is not None:
        p.status = 1 if payload.get("status") == 1 else 0
    if "kind" in payload and payload.get("kind") is not None:
        new_kind = int(payload.get("kind"))
        if new_kind not in (1, 2, 3):
            new_kind = 1
        p.kind = new_kind
        if p.kind != 2:
            p.affinity_gain = 0
    if "affinity_gain" in payload and payload.get("affinity_gain") is not None:
        gain = int(payload.get("affinity_gain"))
        if gain < 0:
            raise HTTPException(status_code=400, detail="好感加成不能为负数")
        p.affinity_gain = gain if (p.kind or 1) == 2 else 0
    # 宠物是否能飞行（仅 kind=1 活体宠物）
    if "can_fly" in payload:
        p.can_fly = bool(payload.get("can_fly")) if (p.kind or 1) == 1 else False
    # 道具按类型定制的数值字段（attrs）
    if "attrs" in payload:
        p.attrs = _clean_attrs(payload.get("attrs"), p.kind or 1)
    # 宠物 AI 人设 / 游戏触发说话常量（自定义宠物，与人设一块编辑）
    if "ai_persona" in payload:
        p.ai_persona = (payload.get("ai_persona") or "").strip() or None
    if "game_speech" in payload:
        gs = payload.get("game_speech")
        if gs is None:
            p.game_speech = None
        else:
            raw = gs.strip() if isinstance(gs, str) else None
            if not raw:
                p.game_speech = None
            else:
                try:
                    obj = json.loads(raw)
                    if not isinstance(obj, dict):
                        raise ValueError
                    # 规范化：只保留字符串值
                    obj = {k: str(v).strip() for k, v in obj.items() if v not in ("", None)}
                    p.game_speech = json.dumps(obj, ensure_ascii=False)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail="游戏触发话术需为合法的 JSON 对象（如 {\"start\":\"开始啦\"}）") from None

    db.commit()
    db.refresh(p)
    cat = db.get(PetCategory, p.category_id)
    return _product_dict(p, cat.name if cat else "")


def admin_toggle_product(db: Session, product_id: int, status: int) -> dict:
    """商品上下架。"""
    p = db.get(PetProduct, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    p.status = 1 if status == 1 else 0
    db.commit()
    db.refresh(p)
    cat = db.get(PetCategory, p.category_id)
    return _product_dict(p, cat.name if cat else "")


def admin_delete_product(db: Session, product_id: int) -> None:
    """删除商品。"""
    p = db.get(PetProduct, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(p)
    db.commit()


# ============ 管理端：DyberPet 宠物制作（开源项目资源导入） ============

# act_conf.json 动作 key → (统一动作 key, 中文 label)
# None = 跳过（方向重复 / 系统动作 drag·fall / 换向行走取一个方向）
_ACT_CONF_MAP: dict[str, tuple[str, str] | None] = {
    "default": ("stand", "待机"),
    "up": None,
    "down": None,
    "left": None,
    "right": None,
    "right_walk": ("walk", "散步"),
    "left_walk": None,
    "walk": ("walk", "散步"),
    "sleep": ("sleep", "睡觉"),
    "fall_asleep": None,
    "drag": None,
    "fall": None,
    "onfloor": ("interact", "趴趴"),
    "angry": ("interact", "生气"),
    "interact": ("interact", "互动"),
    "touch": ("interact", "摸摸"),
    "patpat": ("interact", "摸摸"),
    "fly": ("fly", "飞行"),
    "fly2": ("fly", "飞行"),
}
# 未知动作 key 的中文映射（兜底：没有就显示原 key）
_ACT_LABEL_FALLBACK = {
    "cc": "扑腾",
    "jump": "跳跃",
    "happy": "开心",
    "eat": "干饭",
}
# 动作优先级：stand > walk > sleep > fly > interact，最多收录 5 个（防动作栏溢出）
_ACT_PRIORITY = {"stand": 0, "walk": 1, "sleep": 2, "fly": 3, "interact": 4}
_MAX_ACTIONS = 5


def _dyber_res() -> Path | None:
    if DYBER_RES_DIR and DYBER_RES_DIR.exists():
        return DYBER_RES_DIR
    return None


def _collect_frames(action_dir: Path, prefix: str) -> list[Path]:
    """按前缀收集帧文件（自然数字排序）。"""
    frames: list[Path] = []
    for f in action_dir.iterdir():
        if not f.is_file() or f.suffix.lower() != ".png":
            continue
        m = re.match(rf"^{re.escape(prefix)}_(\d+)\.png$", f.name)
        if m:
            frames.append(f)
    frames.sort(key=lambda f: int(re.search(r"_(\d+)\.png$", f.name).group(1)))
    return frames


def _parse_dyber_actions(action_dir: Path, conf: dict) -> list[dict]:
    """解析 act_conf.json → 统一动作列表（去重、限 5 个、按优先级排序）。"""
    acts: dict[str, dict] = {}
    for conf_key, cfg in conf.items():
        if not isinstance(cfg, dict):
            continue
        mapped = _ACT_CONF_MAP.get(conf_key, False)
        if mapped is None:
            continue  # 显式跳过（方向重复 / 系统动作）
        if mapped is False:
            act_key, label = "interact", _ACT_LABEL_FALLBACK.get(conf_key, conf_key)
        else:
            act_key, label = mapped
        if act_key in acts:
            continue
        prefix = str(cfg.get("images") or conf_key)
        frames = _collect_frames(action_dir, prefix)
        if not frames:
            continue
        try:
            interval = int(float(cfg.get("frame_refresh") or 0.2) * 1000)
        except (TypeError, ValueError):
            interval = 200
        interval = max(40, min(2000, interval))
        acts[act_key] = {"key": act_key, "label": label, "prefix": prefix, "interval": interval, "frame_count": len(frames)}
    ordered = sorted(acts.values(), key=lambda a: _ACT_PRIORITY.get(a["key"], 9))
    return ordered[:_MAX_ACTIONS]


def admin_list_dyber_pets() -> dict:
    """扫描 DyberPet 资源目录，列出可制作（导入）的宠物。

    返回每个宠物的源目录、动作清单（统一 key/label/帧数）与总帧数。
    """
    res = _dyber_res()
    if not res:
        raise HTTPException(status_code=400, detail="服务器未配置 DyberPet 资源目录")
    items: list[dict] = []
    for sub in ("pet", "role"):
        base = res / sub
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name == "sys":
                continue
            conf_path = d / "act_conf.json"
            action_dir = d / "action"
            if not conf_path.exists() or not action_dir.exists():
                continue
            try:
                conf = json.loads(conf_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            acts = _parse_dyber_actions(action_dir, conf)
            if not acts:
                continue
            items.append(
                {
                    "source_dir": f"{sub}/{d.name}",
                    "name": d.name,
                    "actions": [{"key": a["key"], "label": a["label"], "frames": a["frame_count"]} for a in acts],
                    "total_frames": sum(a["frame_count"] for a in acts),
                }
            )
    return {"items": items, "total": len(items)}


def admin_import_dyber_pet(db: Session, payload: dict, admin_id: int) -> dict:
    """制作宠物：从 DyberPet 资源目录导入帧动画并上架商品。

    流程：校验源目录（防路径穿越）→ 复制帧图到 uploads/pets/{slug}/
    → 生成 anim_json → 创建/更新商品（同名更新）。
    """
    source_dir = (payload.get("source_dir") or "").strip().replace("\\", "/")
    if not source_dir or ".." in source_dir.split("/"):
        raise HTTPException(status_code=400, detail="无效的资源目录")
    res = _dyber_res()
    if not res:
        raise HTTPException(status_code=400, detail="服务器未配置 DyberPet 资源目录")
    src = res / source_dir
    action_dir = src / "action"
    conf_path = src / "act_conf.json"
    if not conf_path.exists() or not action_dir.exists():
        raise HTTPException(status_code=404, detail="该宠物资源不存在或缺少动作帧")
    try:
        conf = json.loads(conf_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="动作配置文件解析失败") from None

    acts = _parse_dyber_actions(action_dir, conf)
    selected = payload.get("actions")
    if isinstance(selected, list) and selected:
        wanted = {str(k) for k in selected}
        acts = [a for a in acts if a["key"] in wanted]
    if not acts:
        raise HTTPException(status_code=400, detail="该宠物没有可用的动作帧")

    name = (payload.get("name") or "").strip() or src.name
    price = _parse_price(payload.get("price", 0), "售价")
    original_price = payload.get("original_price")
    original_price = _parse_price(original_price, "原价") if original_price else None
    stock = int(payload.get("stock") or 0)
    category_name = (payload.get("category") or "萌宠领养").strip()

    # 复制帧图 + 生成 anim_json
    slug = "dyber_" + hashlib.md5(source_dir.encode("utf-8")).hexdigest()[:10]
    dst_dir = UPLOADS_PETS_DIR / slug
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    anim_actions = []
    first_frame_url: str | None = None
    for a in acts:
        frames = _collect_frames(action_dir, a["prefix"])
        urls = []
        for f in frames:
            shutil.copy2(f, dst_dir / f.name)
            copied += 1
            urls.append(f"/uploads/pets/{slug}/{f.name}")
        if first_frame_url is None:
            first_frame_url = urls[0]
        anim_actions.append({"key": a["key"], "label": a["label"], "frames": urls, "interval": a["interval"]})
    anim_json = json.dumps({"slug": slug, "actions": anim_actions}, ensure_ascii=False)

    cat = _get_or_create_category(db, category_name)
    product = db.scalar(select(PetProduct).where(PetProduct.name == name))
    if product:
        product.anim_json = anim_json
        product.image_url = first_frame_url
        product.price = price
        product.original_price = original_price
        product.category_id = cat.id
        if payload.get("description"):
            product.description = payload["description"]
        db.add(product)
        action = "update"
    else:
        product = PetProduct(
            name=name,
            category_id=cat.id,
            price=price,
            original_price=original_price,
            stock=stock if stock > 0 else 999,
            image_url=first_frame_url,
            anim_json=anim_json,
            description=(payload.get("description") or "").strip() or None,
            sales=0,
            status=1,
            kind=1,
            created_by=admin_id,
        )
        db.add(product)
        action = "create"
    db.commit()
    db.refresh(product)
    return {
        "product": _product_dict(product, cat.name),
        "action": action,
        "slug": slug,
        "frames_copied": copied,
        "actions": [a["key"] for a in anim_actions],
    }


# ============ 管理端：上传 ZIP 制作宠物 ============

# 压缩后总大小上限（帧图压缩后仍超过则拒绝上传）
MAX_PET_ZIP_COMPRESSED_BYTES = 20 * 1024 * 1024
# 单帧压缩后的最大边长（等比缩放，像素宠物渲染约 120px，256 足够清晰且省流量）
_FRAME_MAX_SIDE = 256


def _extract_archive_to(tmp_path: Path, raw: bytes) -> None:
    """解压 ZIP / RAR / 7z 压缩包到 tmp_path；不支持或损坏时抛出带明确提示的 400。

    DyberPet 宠物资源常见 .zip 发布，但也常被三方打成 RAR/7z 分发，
    穿上一层 .zip 后缀便无法用 zipfile 打开（如「纳西妲.zip」实际是 RAR）。
    这里按魔数识别真实格式：ZIP→内置 zipfile；RAR/7z→命令行 unrar/7z；
    其它→给出可操作的修复提示（改后缀无效，需重新打包）。
    """
    import io as _io
    import os
    import shutil
    import subprocess
    import tempfile
    import zipfile as _zf

    # 1) ZIP：内置 zipfile 直接解
    if raw[:2] == b"PK":
        try:
            with _zf.ZipFile(_io.BytesIO(raw)) as zf:
                zf.extractall(tmp_path)
            return
        except (zipfile.BadZipFile, OSError):  # noqa: BLE001
            raise HTTPException(status_code=400, detail="上传的压缩包已损坏（无效的 ZIP），请重新打包后上传") from None

    magic = raw[:7]
    is_rar = magic[:4] == b"Rar!"  # Rar!\x1a\x07
    is_7z = magic[:3] == b"7z\xbc"  # 7z\xbc\xaf\x27\x1c
    kind = "RAR" if is_rar else "7Z" if is_7z else "未知"
    suffix = ".rar" if is_rar else ".7z"

    # 2) 查找可用的解压工具（unrar / 7z 任选其一）
    tool = None
    for exe in ("unrar", "rar", "7z", "7za", "7zr"):
        p = shutil.which(exe)
        if p:
            tool = p
            break
    if not tool:
        for p in (
            r"C:\Program Files\WinRAR\unrar.exe",
            r"C:\Program Files\WinRAR\rar.exe",
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ):
            if Path(p).exists():
                tool = p
                break
    if not tool:
        raise HTTPException(
            status_code=400,
            detail=f"检测到这是一个{kind}压缩包，但服务端没有解压{kind}的工具。"
            f"请用 WinRAR / 7-Zip 把宠物文件夹重新打包成 ZIP 格式后再上传（直接改后缀名无效）。",
        ) from None

    # 3) 写入临时压缩文件后用命令行解压（避免 unrar 从 stdin 读档的歧义）
    tmp_arc = None
    try:
        fd, tmp_arc = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        is_7z_tool = Path(tool).name.lower().startswith("7z")
        if is_7z_tool:
            cmd = [tool, "x", tmp_arc, "-o" + str(tmp_path), "-y", "-bd"]
        else:  # unrar 的目标目录必须以分隔符结尾
            cmd = [tool, "x", "-y", tmp_arc, str(tmp_path) + os.sep]
        res = subprocess.run(cmd, capture_output=True, timeout=600)
        if res.returncode != 0:
            err = (res.stderr or b"").decode("utf-8", "ignore")[:160]
            raise HTTPException(
                status_code=400,
                detail=f"{kind} 压缩包解压失败：{err or '请确认文件完整后重试'}",
            ) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{kind} 压缩包解压失败：{exc}") from None
    finally:
        if tmp_arc:
            try:
                os.remove(tmp_arc)
            except OSError:
                pass


def _compress_frame_bytes(raw: bytes) -> bytes | None:
    """压缩单帧：缩至不超过 _FRAME_MAX_SIDE 并转 WebP（透明像素宠物 q85 视觉无差，约省 70%+ 流量）。

    返回压缩后的字节；无法解码（非图片/损坏）返回 None（该帧跳过）。
    """
    import io as _io

    from PIL import Image as _PILImage
    try:
        img = _PILImage.open(_io.BytesIO(raw))
        img.thumbnail((_FRAME_MAX_SIDE, _FRAME_MAX_SIDE), _PILImage.LANCZOS)
        if img.mode not in ("RGBA", "RGB", "P"):
            img = img.convert("RGBA")
        buf = _io.BytesIO()
        img.save(buf, format="WEBP", quality=85, method=6)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def admin_import_pet_zip(db: Session, zip_bytes: bytes, meta: dict, admin_id: int) -> dict:
    """管理员上传 ZIP 制作宠物并上架商品。

    约定 ZIP 内含 act_conf.json（DyberPet 动作配置）与帧图 PNG（与 act_conf.json 同级或
    在其 action/ 子目录下，帧命名形如 <prefix>_0.png）。流程：
    解压到临时目录 → 复用 _parse_dyber_actions 解析动作 → 逐帧 Pillow 自动压缩落盘到
    uploads/pets/{slug}/ → 若压缩后总大小仍 >20MB 则拒绝（413）并清理 → 生成 anim_json
    → 按宠物名创建/更新 pet_products（kind=1）。复用 admin_import_dyber_pet 的解析逻辑。
    """
    import io as _io
    import shutil as _shutil
    import tempfile
    import zipfile

    if not zip_bytes:
        raise HTTPException(status_code=400, detail="上传的 ZIP 为空")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _extract_archive_to(tmp_path, zip_bytes)

        conf_path = None
        for p in tmp_path.rglob("act_conf.json"):
            if "__MACOSX" not in str(p):
                conf_path = p
                break
        if not conf_path:
            raise HTTPException(status_code=400, detail="ZIP 内未找到 act_conf.json 动作配置")
        try:
            conf = json.loads(conf_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="act_conf.json 动作配置解析失败") from None

        # 帧图目录：优先 conf 同级 action/，否则与 act_conf.json 同级
        conf_dir = conf_path.parent
        frame_dir = conf_dir / "action"
        if not frame_dir.exists():
            frame_dir = conf_dir
        acts = _parse_dyber_actions(frame_dir, conf)
        if not acts:
            raise HTTPException(status_code=400, detail="ZIP 中没有可用的动作帧")

        name = (meta.get("name") or "").strip() or conf_dir.name.strip() or "自制宠物"
        slug = "zip_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        dst_dir = UPLOADS_PETS_DIR / slug
        if dst_dir.exists():
            _shutil.rmtree(dst_dir, ignore_errors=True)
        dst_dir.mkdir(parents=True, exist_ok=True)

        total_bytes = 0
        written = 0
        anim_actions: list[dict] = []
        first_frame_url: str | None = None
        for a in acts:
            frames = _collect_frames(frame_dir, a["prefix"])
            urls: list[str] = []
            for f in frames:
                comp = _compress_frame_bytes(f.read_bytes())
                if comp is None:
                    continue
                webp_name = f.name[:-4] + ".webp"  # 输出 WebP，浏览器直显
                total_bytes += len(comp)
                (dst_dir / webp_name).write_bytes(comp)
                written += 1
                u = f"/uploads/pets/{slug}/{webp_name}"
                urls.append(u)
                if first_frame_url is None:
                    first_frame_url = u
            if urls:
                anim_actions.append({"key": a["key"], "label": a["label"], "frames": urls, "interval": a["interval"]})

        # 压缩后仍超限 → 拒绝并清理已落盘
        if total_bytes > MAX_PET_ZIP_COMPRESSED_BYTES:
            _shutil.rmtree(dst_dir, ignore_errors=True)
            raise HTTPException(
                status_code=413,
                detail="宠物资源过大：帧图压缩后总大小仍超过 20MB，请精简帧图数量/尺寸后重试",
            )
        if not anim_actions:
            _shutil.rmtree(dst_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="ZIP 中没有可用的动作帧")

        anim_json = json.dumps({"slug": slug, "actions": anim_actions}, ensure_ascii=False)
        category_name = (meta.get("category") or "萌宠领养").strip()
        cat = _get_or_create_category(db, category_name)
        price = _parse_price(meta.get("price", 0), "售价")
        stock = int(meta.get("stock") or 0)

        product = db.scalar(select(PetProduct).where(PetProduct.name == name))
        if product:
            product.anim_json = anim_json
            product.image_url = first_frame_url
            product.price = price
            product.category_id = cat.id
            if meta.get("description"):
                product.description = meta["description"]
            db.add(product)
            action = "update"
        else:
            product = PetProduct(
                name=name,
                category_id=cat.id,
                price=price,
                stock=stock if stock > 0 else 999,
                image_url=first_frame_url,
                anim_json=anim_json,
                description=(meta.get("description") or "").strip() or None,
                sales=0,
                status=1,
                kind=1,
                created_by=admin_id,
            )
            db.add(product)
            action = "create"
        db.commit()
        db.refresh(product)
        return {
            "product": _product_dict(product, cat.name),
            "action": action,
            "slug": slug,
            "frames_written": written,
            "compressed_bytes": total_bytes,
            "actions": [a["key"] for a in anim_actions],
        }
