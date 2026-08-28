"""临时脚本：注册测试账号并验证留言 API 端到端。用完即删。"""
import sqlite3

import requests

BASE = "http://127.0.0.1:8000"
DB = "ly_community.sqlite3"


def get_captcha_answer(captcha_id: str) -> str:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT answer FROM captcha_tickets WHERE ticket_id = ?", (captcha_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""


s = requests.Session()


def fetch_captcha() -> dict:
    r = s.get(f"{BASE}/captcha")
    cap = r.json()["data"]
    cap["answer"] = get_captcha_answer(cap["captcha_id"])
    return cap


# 1. 注册测试账号（请求体直接带 captcha_id + captcha_text）
cap = fetch_captcha()
r = s.post(f"{BASE}/auth/register", json={
    "nickname": "测试同学",
    "username": "testuser01",
    "password": "test12345678",
    "confirm_password": "test12345678",
    "school_id": 1,
    "agreed": True,
    "captcha_id": cap["captcha_id"],
    "captcha_text": cap["answer"],
})
print("register:", r.status_code, r.json())

# 2. 登录（同样带验证码）
cap = fetch_captcha()
r = s.post(f"{BASE}/auth/login", json={
    "username": "testuser01",
    "password": "test12345678",
    "captcha_id": cap["captcha_id"],
    "captcha_text": cap["answer"],
})
print("login:", r.status_code, r.json())

# 4. 组局留言板：发表一级留言 + 回复
r = s.post(f"{BASE}/comments/gathering/1", json={"content": "端到端测试留言：这个组局还有人吗？"})
print("create comment:", r.status_code, r.json())
cid = r.json()["data"]["id"]
r = s.post(f"{BASE}/comments/gathering/1", json={"content": "端到端测试回复：加我一个！", "parent_id": cid})
print("reply:", r.status_code, r.json())
rid = r.json()["data"]["id"]

# 5. 游客视角查列表
r = requests.get(f"{BASE}/comments/gathering/1")
print("list:", r.status_code, r.json())

# 6. 删除回复与根留言
r = s.delete(f"{BASE}/comments/gathering/1/{rid}")
print("delete reply:", r.status_code, r.json())
r = s.delete(f"{BASE}/comments/gathering/1/{cid}")
print("delete root:", r.status_code, r.json())

# 7. 热门玩法留言板（match 类型）
r = s.post(f"{BASE}/comments/match/1", json={"content": "玩法区测试留言"})
print("match create:", r.status_code, r.json())
mcid = r.json()["data"]["id"]
r = requests.get(f"{BASE}/comments/match/1")
print("match list:", r.status_code, r.json())
r = s.delete(f"{BASE}/comments/match/1/{mcid}")
print("match delete:", r.status_code, r.json())
