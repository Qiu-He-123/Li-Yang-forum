# -*- coding: utf-8 -*-
"""临时查询脚本：检查 qiuhe 账户宠物 AI 消息情况。"""
import sqlite3

DB = "ly_community.sqlite3"
db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
db.row_factory = sqlite3.Row
cur = db.cursor()

# 1. 找用户
cur.execute(
    "SELECT id, nickname, username FROM users WHERE username=? OR nickname LIKE ? OR nickname LIKE ? OR nickname LIKE ?",
    ("qiuhe", "%qiuhe%", "%求贺%", "%秋禾%"),
)
users = cur.fetchall()
print("USERS:", [dict(u) for u in users])

if not users:
    # 列出所有用户便于排查
    cur.execute("SELECT id, nickname, username FROM users LIMIT 50")
    print("ALL USERS:", [dict(u) for u in cur.fetchall()])
    db.close()
    raise SystemExit(0)

uid = users[0]["id"]
print("== 使用 uid =", uid)

# 2. 宠物 AI 状态
cur.execute(
    "SELECT pet_id, daily_token, daily_proactive_count, daily_date, last_message_at, next_proactive_at, sleeping_until FROM pet_ai_state WHERE user_id=? ORDER BY pet_id",
    (uid,),
)
print("PET AI STATE:")
for r in cur.fetchall():
    print("  ", dict(r))

# 3. 消息统计（按天/角色）
cur.execute(
    "SELECT date(created_at) d, role, count(*) n FROM pet_ai_messages WHERE user_id=? GROUP BY d, role ORDER BY d",
    (uid,),
)
print("MESSAGES BY DAY/ROLE:")
for r in cur.fetchall():
    print("  ", dict(r))

# 4. 最近 40 条消息
cur.execute(
    "SELECT id, pet_id, role, content, is_read, created_at FROM pet_ai_messages WHERE user_id=? ORDER BY id DESC LIMIT 40",
    (uid,),
)
print("RECENT 40:")
for r in cur.fetchall():
    print("  ", dict(r))

# 5. tool 消息统计
cur.execute(
    "SELECT pet_id, meta, content, created_at FROM pet_ai_messages WHERE user_id=? AND role='tool' ORDER BY id DESC LIMIT 30",
    (uid,),
)
print("TOOL MESSAGES:")
for r in cur.fetchall():
    print("  ", dict(r))

db.close()
