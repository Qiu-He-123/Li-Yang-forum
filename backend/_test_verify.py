"""临时脚本：将测试账号标记为 verified。用完即删。"""
import sqlite3

conn = sqlite3.connect("ly_community.sqlite3")
cur = conn.cursor()
cur.execute("UPDATE users SET verification_status='verified' WHERE username='testuser01'")
conn.commit()
cur.execute("SELECT username, verification_status FROM users WHERE username='testuser01'")
print(cur.fetchall())
conn.close()
