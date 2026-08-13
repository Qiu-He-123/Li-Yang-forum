"""端到端测试脚本：验证新增接口功能正常。"""
import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path


BASE = "http://127.0.0.1:8765"
DB = str(Path(__file__).resolve().parent / "ly_community.sqlite3")

cookie = ""


def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """发送 HTTP 请求，返回 (status_code, json_response)。"""
    global cookie
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # 收集 Set-Cookie
            set_cookie = resp.headers.get_all("Set-Cookie") or []
            for sc in set_cookie:
                # 只取 key=value，去掉 Path/HttpOnly 等
                kv = sc.split(";")[0]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    # 简单合并：保留最新的 access_token / refresh_token
                    if "access_token" in k or "refresh_token" in k:
                        cookie = cookie + "; " + kv if cookie else kv
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, {"raw": text}


def test_login() -> int:
    """登录返回 user_id。"""
    global cookie
    cookie = ""
    status, data = request("POST", "/auth/login", {"phone": "13900000001", "password": "test12345"})
    assert data["code"] == 0, f"login failed: {data}"
    # 第一次请求需要从 set-cookie 拿到 access_token
    # urllib 不会自动管理 cookie，需要从响应里提取
    print(f"[LOGIN] user_id={data['data']['user_id']}")
    # 直接用 access_token 作为 cookie
    access = data["data"]["access_token"]
    cookie = f"access_token={access}"
    return data["data"]["user_id"]


def test_circles():
    """圈子相关测试。"""
    # 列表
    _, data = request("GET", "/circles")
    assert data["code"] == 0, f"GET /circles failed: {data}"
    circles = data["data"]
    print(f"[CIRCLES] count={len(circles)}")
    assert len(circles) == 8, f"expected 8 circles, got {len(circles)}"
    # 验证字段
    c = circles[0]
    assert c["slug"] == "default", f"first circle slug wrong: {c['slug']}"
    assert "is_joined" in c, "is_joined missing"
    assert "color" in c, "color missing"
    assert "member_count" in c, "member_count missing"

    # 详情
    _, data = request("GET", "/circles/default")
    assert data["code"] == 0, f"GET /circles/default failed: {data}"
    assert data["data"]["slug"] == "default"
    assert "created_at" in data["data"], "created_at missing in detail"

    # 加入圈子
    _, data = request("POST", "/circles/default/join")
    assert data["code"] == 0, f"POST join failed: {data}"
    assert data["data"]["is_joined"] is True
    assert data["data"]["member_count"] >= 1

    # 二次加入（幂等）
    _, data = request("POST", "/circles/default/join")
    assert data["code"] == 0, f"idempotent join failed: {data}"
    assert data["data"]["member_count"] == 1, f"idempotent failed: {data}"

    # 圈子内帖子
    _, data = request("GET", "/circles/default/posts")
    assert data["code"] == 0, f"GET circle posts failed: {data}"
    assert "items" in data["data"]
    assert "circle" in data["data"]

    # 退出圈子
    _, data = request("DELETE", "/circles/default/join")
    assert data["code"] == 0, f"DELETE join failed: {data}"
    assert data["data"]["is_joined"] is False

    print("[CIRCLES] all passed")


def test_search():
    """搜索相关测试。"""
    # 触发一次搜索
    _, data = request("GET", "/posts?q=hello")
    assert data["code"] == 0, f"search posts failed: {data}"

    # 搜索历史
    _, data = request("GET", "/search/history")
    assert data["code"] == 0, f"GET search history failed: {data}"
    keywords = [h["keyword"] for h in data["data"]]
    assert "hello" in keywords, f"hello not in history: {keywords}"

    # 删除单条
    _, data = request("DELETE", "/search/history/hello")
    assert data["code"] == 0, f"DELETE single history failed: {data}"
    assert data["data"]["deleted"] >= 1

    # 热搜榜
    _, data = request("GET", "/search/hot")
    assert data["code"] == 0, f"GET hot failed: {data}"
    assert len(data["data"]) == 10, f"expected 10 hot, got {len(data['data'])}"

    # 清空
    _, data = request("DELETE", "/search/history")
    assert data["code"] == 0, f"DELETE history failed: {data}"
    print("[SEARCH] all passed")


def test_follow():
    """关注相关测试。"""
    # 关注用户 2
    _, data = request("POST", "/users/2/follow")
    assert data["code"] == 0, f"follow failed: {data}"
    assert data["data"]["is_following"] is True

    # 是否已关注
    _, data = request("GET", "/users/2/is-following")
    assert data["code"] == 0, f"is-following failed: {data}"
    assert data["data"]["is_following"] is True

    # 二次关注（幂等）
    _, data = request("POST", "/users/2/follow")
    assert data["code"] == 0, f"idempotent follow failed: {data}"

    # 关注列表
    _, data = request("GET", "/users/24/following")
    assert data["code"] == 0, f"following list failed: {data}"
    following_ids = [u["user_id"] for u in data["data"]]
    assert 2 in following_ids, f"user 2 not in following: {following_ids}"

    # 粉丝列表
    _, data = request("GET", "/users/2/followers")
    assert data["code"] == 0, f"followers list failed: {data}"
    follower_ids = [u["user_id"] for u in data["data"]]
    assert 24 in follower_ids, f"user 24 not in user 2 followers: {follower_ids}"

    # 取关
    _, data = request("DELETE", "/users/2/follow")
    assert data["code"] == 0, f"unfollow failed: {data}"
    assert data["data"]["is_following"] is False

    print("[FOLLOW] all passed")


def test_notifications_via_db():
    """通过 DB 验证通知写入是否正确。"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 先关注用户 2，触发通知
    request("POST", "/users/2/follow")
    # 查 user 2 是否收到 follow 通知
    cur.execute(
        "SELECT id, type, sender_id, reference_type, reference_id, is_read FROM notifications "
        "WHERE user_id = 2 AND type = 'follow' ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    assert row is not None, "user 2 should have a follow notification"
    nid, ntype, sender, ref_type, ref_id, is_read = row
    assert ntype == "follow", f"type wrong: {ntype}"
    assert sender == 24, f"sender wrong: {sender}"
    assert ref_type == "user", f"reference_type wrong: {ref_type}"
    assert ref_id == 24, f"reference_id wrong: {ref_id}"
    assert is_read == 0, f"is_read should be 0: {is_read}"
    print(f"[NOTIF_DB] follow notification OK (id={nid}, type={ntype}, sender={sender}, ref={ref_type}:{ref_id})")

    # 清理：取关
    request("DELETE", "/users/2/follow")
    conn.close()


def test_notifications_patch():
    """测试 PATCH read-all 接口（通过测试用户自己的通知）。"""
    # 让用户 24 收到通知：用户 1 关注用户 24？不行，我们没法操作用户 1
    # 替代方案：直接在 DB 插入一条通知给用户 24，然后测试 read-all
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notifications (user_id, title, content, is_read, type, sender_id, reference_type, reference_id, created_at, updated_at) "
        "VALUES (24, '测试通知', '测试内容', 0, 'system', NULL, NULL, NULL, datetime('now'), datetime('now'))"
    )
    cur.execute(
        "INSERT INTO notifications (user_id, title, content, is_read, type, sender_id, reference_type, reference_id, created_at, updated_at) "
        "VALUES (24, '测试点赞', '有人赞了你', 0, 'like', 1, 'post', 84, datetime('now'), datetime('now'))"
    )
    conn.commit()
    conn.close()

    # 列表（带 type 过滤）
    _, data = request("GET", "/notifications?type=like")
    assert data["code"] == 0, f"GET notifications?type=like failed: {data}"
    assert data["data"]["total"] >= 1, f"like notifications should >= 1: {data['data']}"
    items = data["data"]["items"]
    assert all(item["type"] == "like" for item in items), "all should be like type"

    # 全部已读（按 type）
    _, data = request("PATCH", "/notifications/read-all?type=like")
    assert data["code"] == 0, f"PATCH read-all?type=like failed: {data}"
    assert data["data"]["updated"] >= 1, f"should update >= 1: {data['data']}"

    # 验证已读
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT is_read, read_at FROM notifications WHERE user_id = 24 AND type = 'like'")
    rows = cur.fetchall()
    assert all(r[0] == 1 and r[1] is not None for r in rows), f"all like notifications should be read: {rows}"
    conn.close()

    # 全部已读
    _, data = request("PATCH", "/notifications/read-all")
    assert data["code"] == 0, f"PATCH read-all failed: {data}"

    # 标记单条已读（幂等）
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id FROM notifications WHERE user_id = 24 LIMIT 1")
    nid = cur.fetchone()[0]
    conn.close()
    _, data = request("PATCH", f"/notifications/{nid}/read")
    assert data["code"] == 0, f"PATCH single read failed: {data}"
    assert data["data"]["is_read"] is True

    print("[NOTIF] all passed")


def test_post_extensions():
    """帖子扩展字段测试（view/share/related）。"""
    # 找一个已存在的帖子 id
    _, data = request("GET", "/posts?page=1&page_size=1")
    assert data["code"] == 0
    pid = data["data"]["items"][0]["id"]

    # view
    _, data = request("POST", f"/posts/{pid}/view")
    assert data["code"] == 0, f"view failed: {data}"
    assert data["data"]["view_count"] >= 1

    # share
    _, data = request("POST", f"/posts/{pid}/share")
    assert data["code"] == 0, f"share failed: {data}"
    assert data["data"]["share_count"] >= 1

    # related
    _, data = request("GET", f"/posts/{pid}/related")
    assert data["code"] == 0, f"related failed: {data}"
    assert isinstance(data["data"], list)
    assert all(p["id"] != pid for p in data["data"]), "related should exclude current"

    # 验证 post_dict 包含新字段
    _, data = request("GET", f"/posts/{pid}")
    assert data["code"] == 0, f"get post failed: {data}"
    p = data["data"]
    assert "title" in p, "title missing"
    assert "is_original" in p, "is_original missing"
    assert "view_count" in p, "view_count missing"
    assert "share_count" in p, "share_count missing"
    assert "last_reply_at" in p, "last_reply_at missing"

    print("[POST_EXT] all passed")


def test_create_post_with_new_fields():
    """测试创建帖子时支持 title 和 is_original。"""
    # 取一个已存在的 school_id
    _, data = request("GET", "/schools")
    school_id = data["data"][0]["id"]

    body = {
        "content": "测试带标题的原创帖子",
        "school_id": school_id,
        "category": "普通",
        "title": "测试标题",
        "is_original": True,
    }
    _, data = request("POST", "/posts", body)
    assert data["code"] == 0, f"create post failed: {data}"
    pid = data["data"]["id"]
    assert data["data"]["title"] == "测试标题", f"title wrong: {data['data'].get('title')}"
    assert data["data"]["is_original"] is True, f"is_original wrong: {data['data'].get('is_original')}"
    print(f"[POST_NEW] created post id={pid} title={data['data']['title']} is_original={data['data']['is_original']}")


if __name__ == "__main__":
    print(f"=== Testing against {BASE} ===")
    user_id = test_login()

    test_circles()
    test_search()
    test_follow()
    test_post_extensions()
    test_create_post_with_new_fields()
    test_notifications_via_db()
    test_notifications_patch()

    print("\n========== ALL TESTS PASSED ==========")
