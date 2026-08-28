"""数据迁移：重新分类食物、删除冗余分类、扩充商品品种。"""
import sqlite3
from datetime import datetime

DB_PATH = "ly_community.sqlite3"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

# 1. 更新现有食物分类
cur.execute("UPDATE pet_products SET category_id=3 WHERE id=10")  # 小鱼干→零食
cur.execute("UPDATE pet_products SET category_id=1, name=? WHERE id=11", ("猫罐头",))
cur.execute("UPDATE pet_products SET category_id=2, name=? WHERE id=12", ("狗粮大餐",))

# 2. 新商品列表: (name, category_id, kind, price, affinity_gain, stock, image_url/emoji, description)
new_items = [
    # 猫粮
    ("高级猫粮", 1, 2, 35, 8, 9999, "🥩", "优质蛋白配方，猫咪最爱"),
    ("幼猫奶糕", 1, 2, 15, 3, 9999, "🍼", "软糯易嚼，适合幼猫"),
    ("三文鱼猫粮", 1, 2, 45, 10, 9999, "🐟", "深海三文鱼，美毛护肤"),
    # 狗粮
    ("高级狗粮", 2, 2, 35, 8, 9999, "🥩", "营养均衡，活力满满"),
    ("幼犬奶糕", 2, 2, 15, 3, 9999, "🍼", "小颗粒易吸收，幼犬专用"),
    ("牛肉狗粮", 2, 2, 50, 12, 9999, "🥩", "精选牛肉配方，强壮骨骼"),
    # 零食
    ("鸡肉条", 3, 2, 25, 6, 9999, "🍗", "纯鸡肉制作，训练奖励好帮手"),
    ("奶酪块", 3, 2, 18, 4, 9999, "🧀", "香浓奶酪，补钙佳品"),
    ("冻干鹌鹑", 3, 2, 45, 10, 9999, "🐦", "整只冻干，高蛋白营养"),
    ("磨牙棒", 3, 2, 12, 3, 9999, "🦴", "耐啃咬，清洁牙齿"),
    ("冻干蛋黄", 3, 2, 30, 7, 9999, "🥚", "卵磷脂丰富，亮毛护肤"),
    # 玩具
    ("逗猫棒", 4, 2, 30, 5, 9999, "🎣", "羽毛逗猫棒，猫咪超爱"),
    ("毛线球", 4, 2, 25, 4, 9999, "🧶", "彩色毛线球，解闷神器"),
    ("飞盘", 4, 2, 40, 6, 9999, "🥏", "互动飞盘，狗狗最爱"),
    ("激光笔", 4, 2, 55, 8, 9999, "🔴", "红外线激光笔，追逐乐趣"),
    ("发声玩具", 4, 2, 35, 5, 9999, "🔔", "BB发声玩具，吸引注意力"),
    # 日用
    ("宠物香波", 5, 2, 20, 3, 9999, "🧴", "温和配方，洗护二合一"),
    ("宠物尿垫", 5, 2, 15, 2, 9999, "📦", "加厚吸水，保持清洁"),
    ("柔软小窝", 5, 2, 80, 5, 999, "🛏️", "温暖舒适，安睡一整晚"),
    ("宠物梳子", 5, 2, 25, 2, 9999, "🪮", "去浮毛神器，按摩皮肤"),
    # 医疗
    ("营养膏", 6, 2, 40, 7, 9999, "💊", "多维营养，快速补充体力"),
    ("驱虫药", 6, 2, 30, 4, 9999, "💉", "内外同驱，健康守护"),
    ("益生菌", 6, 2, 35, 5, 9999, "🦠", "调理肠胃，消化好吸收"),
    # 进化道具 (kind=3, 放在玩具分类)
    ("进化水晶", 4, 3, 500, 0, 999, "💎", "神秘的进化水晶，宠物好感度满100后可使用，使其进化为灵魂伴侣"),
]

for name, cat_id, kind, price, affinity, stock, icon, desc in new_items:
    cur.execute("SELECT id FROM pet_products WHERE name=? AND category_id=?", (name, cat_id))
    if not cur.fetchone():
        cur.execute(
            """INSERT INTO pet_products (name, category_id, kind, price, original_price, stock, image_url, description, sales, status, affinity_gain, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, 0, 1, ?, ?, ?)""",
            (name, cat_id, kind, price, stock, icon, desc, affinity, now, now)
        )
        print(f"Added: {name} (cat={cat_id}, kind={kind}, price={price}, affinity=+{affinity})")
    else:
        print(f"Skipped (exists): {name}")

# 3. 删除「宠物食物」分类
cur.execute("SELECT COUNT(*) FROM pet_products WHERE category_id=8")
count = cur.fetchone()[0]
if count == 0:
    cur.execute("DELETE FROM pet_categories WHERE id=8")
    print("Deleted category: 宠物食物(id=8)")
else:
    print(f"WARNING: {count} products still in category 8")

conn.commit()

# 验证结果
print("\n=== 最终分类列表 ===")
cur.execute("SELECT * FROM pet_categories ORDER BY sort_order, id")
cats = cur.fetchall()
for r in cats:
    print(f"  id={r[0]} name={r[1]} icon={r[2]}")

print("\n=== 分类商品统计 ===")
cur.execute("""SELECT c.name, COUNT(p.id) FROM pet_categories c 
              LEFT JOIN pet_products p ON c.id=p.category_id AND p.status=1 
              GROUP BY c.id ORDER BY c.sort_order""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} 件商品")

print("\n=== 所有商品 ===")
cur.execute("""SELECT p.id, p.name, c.name as cat, p.kind, p.price, p.affinity_gain, p.stock, p.image_url 
              FROM pet_products p JOIN pet_categories c ON c.id=p.category_id 
              WHERE p.status=1 ORDER BY c.sort_order, p.id""")
kind_map = {1: "宠物", 2: "道具", 3: "进化"}
for r in cur.fetchall():
    print(f"  id={r[0]:2d} {r[1]:8s} | {r[2]:4s} | {kind_map.get(r[3], '?'):2s} | {r[4]:>4}c | +{r[5]:>2} | stock={r[6]} | {r[7]}")

conn.close()
print("\nDone!")
