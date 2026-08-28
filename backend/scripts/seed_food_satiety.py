"""数据修复：为商城所有粮食/道具商品补齐 attrs（好感 + 饱腹度）。

后台商品列表里道具(食物)只标注了 affinity_gain，未写入 attrs.satiety，
导致喂食时全部走默认饱腹恢复量(40)、商城/喂食面板也看不到"饱腹+N"。

本脚本按"价格越贵恢复越多"的原则为食物类商品（kind=2 且属于猫粮/狗粮/零食分类）
生成 attrs={"affinity":N,"satiety":M}，幂等可重复执行。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PetCategory, PetProduct

# 只给这些分类下的道具标记为"粮食"（可喂食），它们会获得 satiety 饱腹度数值
FOOD_CATEGORY_NAMES = {"猫粮", "狗粮", "零食"}


def _json_dict(v):
    import json

    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except Exception:
        return {}


def _satiety_for(price: float) -> int:
    """价格越高，单次补充的饱腹度越多（20~90）。"""
    p = float(price or 0)
    s = int(round(28 + p * 0.6))
    return max(20, min(90, s))


def main() -> None:
    db = SessionLocal()
    try:
        food_cat_ids = set(
            db.scalars(
                select(PetCategory.id).where(PetCategory.name.in_(FOOD_CATEGORY_NAMES))
            ).all()
        )
        if not food_cat_ids:
            print("未找到猫粮/狗粮/零食分类，跳过")
            return

        pros = db.scalars(
            select(PetProduct).where(
                PetProduct.category_id.in_(food_cat_ids), PetProduct.kind == 2
            )
        ).all()

        updated = 0
        for p in pros:
            attrs = _json_dict(p.attrs)
            affinity = int(p.affinity_gain or 0)
            satiety = _satiety_for(p.price)
            # 仅补齐缺失/不一致，避免覆盖后台手填值
            changed = False
            if attrs.get("affinity") != affinity:
                attrs["affinity"] = affinity
                changed = True
            if attrs.get("satiety") != satiety:
                attrs["satiety"] = satiety
                changed = True
            if changed:
                import json as _json

                p.attrs = _json.dumps(attrs, ensure_ascii=False)
                db.add(p)
                updated += 1
                print(f"修复：{p.name} → 饱腹+{satiety} 好感+{affinity}")

        db.commit()
        print(f"\n共修复 {updated} 件粮食商品")
    finally:
        db.close()


if __name__ == "__main__":
    main()