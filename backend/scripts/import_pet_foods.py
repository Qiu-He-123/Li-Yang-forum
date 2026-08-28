"""导入宠物食物道具（商城道具分类，kind=2）。

道具：小鱼干(+5 好感/20金币)、营养罐头(+12/50)、豪华大餐(+30/120)。
幂等：同名商品更新，否则插入。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PetCategory, PetProduct

CATEGORY_NAME = "宠物食物"

# (名称, 金币价, 原价, 好感加成, emoji 图标, 描述)
FOODS = [
    ("小鱼干", 20, 30, 5, "🐟", "香喷喷的小鱼干，零食入门首选。喂食好感度 +5。"),
    ("营养罐头", 50, 68, 12, "🥫", "满口肉香的精品罐头，营养均衡。喂食好感度 +12。"),
    ("豪华大餐", 120, 168, 30, "🍱", "顶级食材精心烹制的大餐！喂食好感度 +30。"),
]


def main() -> None:
    db = SessionLocal()
    try:
        cat = db.scalar(select(PetCategory).where(PetCategory.name == CATEGORY_NAME))
        if not cat:
            max_order = db.scalar(select(PetCategory.sort_order).order_by(PetCategory.sort_order.desc())) or 0
            cat = PetCategory(name=CATEGORY_NAME, icon="🍱", sort_order=max_order + 1)
            db.add(cat)
            db.flush()

        for name, price, original, gain, emoji, desc in FOODS:
            p = db.scalar(select(PetProduct).where(PetProduct.name == name))
            if p:
                p.kind = 2
                p.affinity_gain = gain
                p.price = float(price)
                p.original_price = float(original)
                p.image_url = emoji
                p.description = desc
                p.category_id = cat.id
                p.status = 1
                db.add(p)
                print(f"更新道具：{name}")
            else:
                db.add(
                    PetProduct(
                        name=name,
                        category_id=cat.id,
                        price=float(price),
                        original_price=float(original),
                        stock=9999,
                        image_url=emoji,
                        description=desc,
                        sales=0,
                        status=1,
                        kind=2,
                        affinity_gain=gain,
                    )
                )
                print(f"新增道具：{name}")
        db.commit()
        print("完成")
    finally:
        db.close()


if __name__ == "__main__":
    main()
