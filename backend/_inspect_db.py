import sqlite3
conn = sqlite3.connect("ly_community.sqlite3")
cur = conn.cursor()
print("=== 分类 ===")
for r in cur.execute("SELECT id,name,icon FROM pet_categories ORDER BY id"):
    print(r)
print("=== 道具商品 kind=2 ===")
for r in cur.execute("SELECT id,name,category_id,kind,price,affinity_gain,stock,image_url,status,COALESCE(attrs,'') FROM pet_products WHERE kind=2 ORDER BY category_id"):
    print(r)
conn.close()