import sqlite3

con = sqlite3.connect("ly_community.sqlite3")
cur = con.cursor()
cur.execute("SELECT version_num FROM alembic_version")
print("alembic_version:", cur.fetchall())
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='games'")
print("games table:", cur.fetchall())
cur.execute("SELECT count(*) FROM games")
print("games count:", cur.fetchall())
cur.execute(
    "SELECT name, slug, type, reward_coins, daily_limit, is_active, status, sort_order FROM games ORDER BY sort_order"
)
for r in cur.fetchall():
    print(r)
con.close()
