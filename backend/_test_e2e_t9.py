"""T9-1 E2E API 测试脚本：验证核心场景的后端接口正确性。

覆盖：
1. 注册 + 会话校验
2. 发帖 + 列表刷新验证
3. 发评论 + 计数同步
4. 回复评论 + 计数同步
5. 删除根评论 + 级联删除 + 计数回 0
6. 搜索功能（两次不同关键词）
"""
import json
import sys
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar

BASE = "http://127.0.0.1:8000"


def make_session():
    """创建带 Cookie 管理的 opener。"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj


def request(opener, method, path, body=None):
    """发起 HTTP 请求，返回解析后的 JSON。

    自动 URL-encode query string 中的中文，避免 ASCII 编码错误。
    """
    # 对 path 中的 query string 进行 URL encode（支持中文关键词）
    if "?" in path:
        base_path, query = path.split("?", 1)
        # 先按 & 拆分键值对，再对每个值做 quote
        parts = []
        for kv in query.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                parts.append(f"{k}={urllib.parse.quote(v, safe='')}")
            else:
                parts.append(urllib.parse.quote(kv, safe=''))
        url = BASE + base_path + "?" + "&".join(parts)
    else:
        url = BASE + path
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with opener.open(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        return {"http_error": e.code, "body": body_text}


def main():
    opener, _ = make_session()

    print("=" * 60)
    print("T9-1 E2E API 测试开始")
    print("=" * 60)

    # 1. 获取校区
    schools = request(opener, "GET", "/schools")
    school_id = schools["data"][0]["id"]
    print(f"[1] Get schools: OK (school_id={school_id})")

    # 2. 注册新用户
    import time
    phone = f"139{int(time.time()) % 100000000:08d}"
    reg_body = {
        "nickname": "T9E2E测试员",
        "phone": phone,
        "code": "123456",
        "password": "Test@2026",
        "confirm_password": "Test@2026",
        "school_id": school_id,
        "agreed": True,
    }
    reg = request(opener, "POST", "/auth/register", reg_body)
    assert reg["code"] == 0, f"注册失败: {reg}"
    user_id = reg["data"]["user_id"]
    print(f"[2] Register: OK (user_id={user_id}, phone={phone})")

    # 3. 验证会话
    me = request(opener, "GET", "/auth/me")
    assert me["code"] == 0, f"会话校验失败: {me}"
    assert me["data"]["nickname"] == "T9E2E测试员", f"昵称不匹配: {me['data']['nickname']}"
    print(f"[3] Validate session: OK (nickname={me['data']['nickname']})")

    # 4. 发布帖子
    post_body = {
        "content": "T9E2E测试发帖-验证刷新",
        "image_urls": [],
        "is_anonymous": False,
        "is_public": True,
        "school_id": school_id,
        "category": "普通",
        "is_draft": False,
    }
    post = request(opener, "POST", "/posts", post_body)
    assert post["code"] == 0, f"发帖失败: {post}"
    post_id = post["data"]["id"]
    print(f"[4] Create post: OK (post_id={post_id})")

    # 5. 验证帖子出现在列表顶部（验证发布后刷新逻辑）
    listing = request(opener, "GET", "/posts?page=1&page_size=5")
    # 兼容两种返回结构：裸数组 或 {items, total, ...}
    if isinstance(listing["data"], dict):
        posts_list = listing["data"]["items"]
    else:
        posts_list = listing["data"]
    first_post_id = posts_list[0]["id"]
    assert first_post_id == post_id, f"新帖未出现在列表顶部: first={first_post_id}, expected={post_id}"
    print(f"[5] List posts: OK (新帖在列表顶部)")

    # 6. 发表评论
    comment = request(opener, "POST", f"/posts/{post_id}/comments", {"content": "T9E2E测试评论"})
    assert comment["code"] == 0, f"发评论失败: {comment}"
    comment_id = comment["data"]["id"]
    assert comment["data"]["post_comment_count"] == 1, f"评论计数应为 1，实际 {comment['data']['post_comment_count']}"
    print(f"[6] Create comment: OK (comment_id={comment_id}, count=1)")

    # 7. 回复评论
    reply = request(opener, "POST", f"/posts/{post_id}/comments", {
        "content": "T9E2E测试回复",
        "parent_id": comment_id,
    })
    assert reply["code"] == 0, f"回复失败: {reply}"
    assert reply["data"]["post_comment_count"] == 2, f"评论计数应为 2，实际 {reply['data']['post_comment_count']}"
    print(f"[7] Create reply: OK (count=2)")

    # 8. 获取评论列表验证分层
    list_c = request(opener, "GET", f"/posts/{post_id}/comments")
    # 兼容两种返回结构：裸数组 或 {items, total, ...}
    if isinstance(list_c["data"], dict):
        items = list_c["data"]["items"]
        total_c = list_c["data"]["total"]
    else:
        items = list_c["data"]
        total_c = len(items)
    assert total_c == 2, f"评论总数应为 2，实际 {total_c}"
    roots = [it for it in items if not it["parent_id"]]
    replies = [it for it in items if it["parent_id"] == comment_id]
    assert len(roots) == 1 and len(replies) == 1, f"分层错误: roots={len(roots)}, replies={len(replies)}"
    print(f"[8] List comments: OK (total=2, roots=1, replies=1)")

    # 9. 删除根评论 - 验证级联删除（关键 Bug 修复点）
    del_resp = request(opener, "DELETE", f"/posts/{post_id}/comments/{comment_id}")
    print(f"    [debug] delete response: {del_resp}")
    assert del_resp["code"] == 0, f"删除失败: {del_resp}"
    assert del_resp["data"]["post_comment_count"] == 0, (
        f"级联删除后计数应为 0，实际 {del_resp['data']['post_comment_count']}（这是之前 Bug 的关键点）"
    )
    print(f"[9] Delete root comment (cascade): OK (count=0, 根评论+回复全部删除)")

    # 10. 验证评论列表为空
    list_c2 = request(opener, "GET", f"/posts/{post_id}/comments")
    if isinstance(list_c2["data"], dict):
        items2 = list_c2["data"]["items"]
        total_c2 = list_c2["data"]["total"]
    else:
        items2 = list_c2["data"]
        total_c2 = len(items2)
    assert total_c2 == 0, f"删除后评论总数应为 0，实际 {total_c2}"
    assert len(items2) == 0, f"删除后评论列表应为空"
    print(f"[10] List comments after delete: OK (total=0, 列表为空)")

    # 11. 搜索功能 - 第一次搜索
    s1 = request(opener, "GET", "/posts?q=T9E2E&page=1&page_size=10")
    if isinstance(s1["data"], dict):
        s1_results = len(s1["data"]["items"])
    else:
        s1_results = len(s1["data"])
    assert s1_results >= 1, f"第一次搜索应有结果，实际 {s1_results}"
    print(f"[11] Search 'T9E2E': OK (results={s1_results})")

    # 12. 搜索功能 - 第二次搜索（不同关键词，验证刷新）
    s2 = request(opener, "GET", "/posts?q=不存在的关键词XYZ_T9&page=1&page_size=10")
    if isinstance(s2["data"], dict):
        s2_results = len(s2["data"]["items"])
    else:
        s2_results = len(s2["data"])
    assert s2_results == 0, f"第二次搜索应无结果，实际 {s2_results}"
    print(f"[12] Search '不存在的关键词XYZ_T9': OK (results=0, 第二次搜索正确刷新)")

    # 13. 验证帖子 comment_count 字段已回 0（DB 一致性）
    listing2 = request(opener, "GET", "/posts?page=1&page_size=5")
    if isinstance(listing2["data"], dict):
        posts_list2 = listing2["data"]["items"]
    else:
        posts_list2 = listing2["data"]
    target_post = next((p for p in posts_list2 if p["id"] == post_id), None)
    assert target_post is not None, "帖子不在列表中"
    assert target_post["comment_count"] == 0, (
        f"帖子 comment_count 字段应为 0，实际 {target_post['comment_count']}（DB 不一致）"
    )
    print(f"[13] Verify post.comment_count in DB: OK (count=0, DB 一致)")

    print()
    print("=" * 60)
    print("E2E 测试全部通过！13 个场景均验证成功。")
    print("=" * 60)
    print()
    print("关键 Bug 修复验证：")
    print(f"  - 发布帖子后列表刷新: OK（新帖出现在列表顶部）")
    print(f"  - 评论计数同步: OK（1 -> 2 -> 0，全部正确）")
    print(f"  - 级联删除子回复: OK（删除根评论后回复也消失，count 回 0）")
    print(f"  - 第二次搜索刷新: OK（不同关键词返回不同结果）")
    print(f"  - DB 一致性: OK（post.comment_count 字段与实际评论数一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
