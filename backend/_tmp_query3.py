# -*- coding: utf-8 -*-
"""查询宠物商品 id/名称 对照 + 派蒙/纳西妲。"""
import sqlite3

db = sqlite3.connect("file:ly_community.sqlite3?mode=ro", uri=True)
db.row_factory = sqlite3.Row
cur = db.cursor()
cur.execute("SELECT id, name, kind, ai_enabled, image_url FROM pet_products WHERE id IN (1,53,55) OR name LIKE '%纳西妲%' OR name LIKE '%派蒙%'")
for r in cur.fetchall():
    print(dict(r))
db.close()
