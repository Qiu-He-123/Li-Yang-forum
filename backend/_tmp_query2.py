# -*- coding: utf-8 -*-
import sqlite3

DB = "ly_community.sqlite3"
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute(
    "SELECT id, nickname, username FROM users WHERE username=? OR nickname LIKE ? OR nickname LIKE ? OR nickname LIKE ?",
    ("qiuhe", "%qiuhe%", "%求贺%", "%秋禾%"),
)
users = cur.fetchall()
print("USERS:", [dict(u) for u in users])
if not users:
    db.close()
    raise SystemExit(0)

uid = users[0]["id"]
print("== uid =", uid)

cur.execute(
    "SELECT pet_id, COUNT(*) c FROM pet_ai_messages WHERE user_id=? GROUP BY pet_id ORDER BY c DESC LIMIT 10",
    (uid,),
)
print("MSG COUNT BY PET:", [dict(r) for r in cur.fetchall()])

cur.execute(
    "SELECT id, user_id, pet_id, role, substr(content,1,50) c, is_read, created_at FROM pet_ai_messages WHERE user_id=? ORDER BY id DESC LIMIT 40",
    (uid,),
)
for r in cur.fetchall():
    print(dict(r))

print("== AI states ==")
cur.execute(
    "SELECT pet_id, daily_proactive_count, daily_date, last_message_at, next_proactive_at, sleeping_until FROM pet_ai_state WHERE user_id=?",
    (uid,),
)
for r in cur.fetchall():
    print(dict(r))
db.close()
