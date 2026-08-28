"""数据迁移脚本 v3：
1. 运行 alembic 迁移到 0047（增加 level/cooldowns 等字段）
2. 确保分类正确（删除冗余分类，添加新分类）
3. 重新分类现有食物道具（猫粮/狗粮/零食/玩具/日用/医疗）
4. 扩充新商品（多种食物、玩具、日用品、进化水晶）
5. 删除「宠物食物」分类（如果存在）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.database import SessionLocal, engine
from app.models import PetCategory, PetProduct, UserPet, UserPetItem
from sqlalchemy import select, func, text

def run():
    db = SessionLocal()
    try:
        # ====== 1. 确保分类 ======
        desired_cats = [
            ("猫粮", "🐱", 1),
            ("狗粮", "🐶", 2),
            ("零食", "🍪", 3),
            ("玩具", "🎾", 4),
            ("日用", "🏠", 5),
            ("医疗", "💊", 6),
            ("萌宠领养", "🐾", 7),
        ]
        cat_map = {}
        for name, icon, order in desired_cats:
            cat = db.scalar(select(PetCategory).where(PetCategory.name == name))
            if not cat:
                cat = PetCategory(name=name, icon=icon, sort_order=order)
                db.add(cat)
                db.flush()
            else:
                if cat.icon != icon or cat.sort_order != order:
                    cat.icon = icon
                    cat.sort_order = order
            cat_map[name] = cat.id

        # 删除「宠物食物」冗余分类（如果存在）
        old_food_cat = db.scalar(select(PetCategory).where(PetCategory.name == "宠物食物"))
        if old_food_cat:
            # 将该分类下商品移到「零食」分类
            snack_cat_id = cat_map.get("零食")
            if snack_cat_id:
                db.execute(
                    text("UPDATE pet_products SET category_id = :new_id WHERE category_id = :old_id"),
                    {"new_id": snack_cat_id, "old_id": old_food_cat.id}
                )
            db.delete(old_food_cat)
            print("已删除冗余分类「宠物食物」，商品已迁移到「零食」")

        # 删除其他可能的冗余分类
        for old_name in ["食物", "宠物", "全部"]:
            old_cat = db.scalar(select(PetCategory).where(PetCategory.name == old_name))
            if old_cat:
                snack_cat_id = cat_map.get("零食")
                if snack_cat_id:
                    db.execute(
                        text("UPDATE pet_products SET category_id = :new_id WHERE category_id = :old_id"),
                        {"new_id": snack_cat_id, "old_id": old_cat.id}
                    )
                db.delete(old_cat)
                print(f"已删除冗余分类「{old_name}」")

        db.commit()

        # ====== 2. 重新分类现有道具（ID 10-12 是之前的食物） ======
        # 根据记忆：小鱼干(10)→零食, 营养罐头/薛定谔罐头(11)→猫粮, 豪华大餐(12)→狗粮
        recategorize = {
            10: ("零食", 2, 5, "🍪", "香脆小鱼干，猫咪最爱", 20),     # 小鱼干 → 零食
            11: ("猫粮", 2, 12, "🥫", "薛定谔罐头，营养丰富", 50),     # 罐头 → 猫粮
            12: ("狗粮", 2, 30, "🍖", "豪华大餐，狗狗最爱", 120),      # 大餐 → 狗粮
        }
        for pid, (cat_name, kind, price, img, desc, affinity) in recategorize.items():
            p = db.get(PetProduct, pid)
            if p:
                p.category_id = cat_map[cat_name]
                p.kind = kind
                p.price = price
                p.image_url = img
                p.description = desc
                p.affinity_gain = affinity
                p.status = 1
                p.name = {10: "小鱼干", 11: "薛定谔罐头", 12: "豪华大餐"}.get(pid, p.name)
                print(f"已重新分类商品#{pid}: {p.name} → {cat_name} (kind={kind}, 好感+{affinity})")

        db.commit()

        # ====== 3. 添加新商品 ======
        new_products = [
            # === 猫粮 ===
            {"name": "高级猫粮", "category": "猫粮", "kind": 2, "price": 80, "image_url": "🐱",
             "description": "优质天然猫粮，营养均衡", "affinity_gain": 20, "stock": 9999, "sales": 0},
            {"name": "猫条", "category": "猫粮", "kind": 2, "price": 15, "image_url": "🥩",
             "description": "流质猫条，互动训练奖励", "affinity_gain": 3, "stock": 9999, "sales": 0},
            {"name": "冻干鸡胸肉", "category": "猫粮", "kind": 2, "price": 60, "image_url": "🍗",
             "description": "冻干锁鲜，高蛋白", "affinity_gain": 15, "stock": 9999, "sales": 0},
            {"name": "猫罐头·金枪鱼", "category": "猫粮", "kind": 2, "price": 35, "image_url": "🐟",
             "description": "金枪鱼肉块罐头", "affinity_gain": 8, "stock": 9999, "sales": 0},

            # === 狗粮 ===
            {"name": "高级狗粮", "category": "狗粮", "kind": 2, "price": 75, "image_url": "🐕",
             "description": "全价狗粮，适合各年龄段", "affinity_gain": 18, "stock": 9999, "sales": 0},
            {"name": "肉干零食", "category": "狗粮", "kind": 2, "price": 40, "image_url": "🥓",
             "description": "手工烘焙肉干", "affinity_gain": 10, "stock": 9999, "sales": 0},
            {"name": "洁齿骨", "category": "狗粮", "kind": 2, "price": 25, "image_url": "🦴",
             "description": "磨牙洁齿，清新口气", "affinity_gain": 5, "stock": 9999, "sales": 0},
            {"name": "牛肉粒", "category": "狗粮", "kind": 2, "price": 50, "image_url": "🥩",
             "description": "精选牛肉粒，训练奖励", "affinity_gain": 12, "stock": 9999, "sales": 0},

            # === 零食（通用） ===
            {"name": "奶酪块", "category": "零食", "kind": 2, "price": 30, "image_url": "🧀",
             "description": "香浓奶酪小块", "affinity_gain": 7, "stock": 9999, "sales": 0},
            {"name": "小饼干", "category": "零食", "kind": 2, "price": 10, "image_url": "🍪",
             "description": "酥脆小饼干", "affinity_gain": 2, "stock": 9999, "sales": 0},
            {"name": "布丁", "category": "零食", "kind": 2, "price": 18, "image_url": "🍮",
             "description": "滑嫩布丁", "affinity_gain": 4, "stock": 9999, "sales": 0},

            # === 玩具 ===
            {"name": "毛线球", "category": "玩具", "kind": 2, "price": 25, "image_url": "🧶",
             "description": "经典毛线球，猫咪最爱追逐", "affinity_gain": 3, "stock": 9999, "sales": 0},
            {"name": "逗猫棒", "category": "玩具", "kind": 2, "price": 35, "image_url": "🎣",
             "description": "羽毛逗猫棒，互动神器", "affinity_gain": 5, "stock": 9999, "sales": 0},
            {"name": "飞盘", "category": "玩具", "kind": 2, "price": 30, "image_url": "🥏",
             "description": "软胶飞盘，狗狗户外玩耍", "affinity_gain": 4, "stock": 9999, "sales": 0},
            {"name": "球球", "category": "玩具", "kind": 2, "price": 15, "image_url": "⚽",
             "description": "弹力橡胶球", "affinity_gain": 2, "stock": 9999, "sales": 0},
            {"name": "激光笔", "category": "玩具", "kind": 2, "price": 20, "image_url": "🔴",
             "description": "红点激光笔", "affinity_gain": 3, "stock": 9999, "sales": 0},

            # === 日用 ===
            {"name": "宠物窝", "category": "日用", "kind": 2, "price": 200, "image_url": "🛏️",
             "description": "柔软舒适的宠物窝", "affinity_gain": 8, "stock": 9999, "sales": 0},
            {"name": "猫砂", "category": "日用", "kind": 2, "price": 45, "image_url": "🏖️",
             "description": "膨润土猫砂10L", "affinity_gain": 0, "stock": 9999, "sales": 0},
            {"name": "牵引绳", "category": "日用", "kind": 2, "price": 55, "image_url": "🦮",
             "description": "反光牵引绳", "affinity_gain": 0, "stock": 9999, "sales": 0},
            {"name": "食盆", "category": "日用", "kind": 2, "price": 20, "image_url": "🥣",
             "description": "不锈钢双碗食盆", "affinity_gain": 0, "stock": 9999, "sales": 0},
            {"name": "宠物衣服", "category": "日用", "kind": 2, "price": 80, "image_url": "👕",
             "description": "可爱宠物卫衣", "affinity_gain": 2, "stock": 9999, "sales": 0},

            # === 医疗 ===
            {"name": "驱虫药", "category": "医疗", "kind": 2, "price": 60, "image_url": "💊",
             "description": "体内外驱虫", "affinity_gain": 1, "stock": 9999, "sales": 0},
            {"name": "营养膏", "category": "医疗", "kind": 2, "price": 55, "image_url": "🧴",
             "description": "综合营养膏，增强体质", "affinity_gain": 6, "stock": 9999, "sales": 0},
            {"name": "维生素片", "category": "医疗", "kind": 2, "price": 40, "image_url": "💉",
             "description": "宠物复合维生素", "affinity_gain": 3, "stock": 9999, "sales": 0},

            # === 进化道具 ===
            {"name": "进化水晶", "category": "萌宠领养", "kind": 3, "price": 500, "image_url": "💎",
             "description": "神秘水晶，好感度满100后可使宠物超级进化为灵魂伴侣", "affinity_gain": 0, "stock": 9999, "sales": 0},
        ]

        added = 0
        for prod in new_products:
            cat_id = cat_map[prod["category"]]
            # 检查是否已存在
            existing = db.scalar(
                select(PetProduct).where(
                    PetProduct.name == prod["name"],
                    PetProduct.category_id == cat_id,
                    PetProduct.kind == prod["kind"]
                )
            )
            if existing:
                # 更新库存和描述
                existing.stock = 9999
                existing.description = prod["description"]
                existing.image_url = prod["image_url"]
                existing.affinity_gain = prod["affinity_gain"]
                existing.price = prod["price"]
                existing.status = 1
                continue
            p = PetProduct(
                name=prod["name"],
                category_id=cat_id,
                kind=prod["kind"],
                price=prod["price"],
                stock=prod["stock"],
                image_url=prod["image_url"],
                description=prod["description"],
                affinity_gain=prod["affinity_gain"],
                status=1,
                sales=prod["sales"],
            )
            db.add(p)
            added += 1

        db.commit()
        print(f"已新增 {added} 个新商品")

        # ====== 4. 统计输出 ======
        total_products = db.scalar(select(func.count()).select_from(PetProduct).where(PetProduct.status == 1))
        total_cats = db.scalar(select(func.count()).select_from(PetCategory))
        print(f"\n=== 数据迁移完成 ===")
        print(f"分类数量: {total_cats}")
        for cat in db.scalars(select(PetCategory).order_by(PetCategory.sort_order)).all():
            cnt = db.scalar(select(func.count()).select_from(PetProduct).where(
                PetProduct.category_id == cat.id, PetProduct.status == 1
            ))
            print(f"  {cat.icon or ''} {cat.name}: {cnt}件商品")
        print(f"上架商品总数: {total_products}")

    finally:
        db.close()

if __name__ == "__main__":
    run()
