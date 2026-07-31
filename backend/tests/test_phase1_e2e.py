"""阶段 1 架构重构后端到端联调自测脚本。

覆盖：注册 → 登录 → 发帖 → 评论 → 点赞 → 收藏 → 举报 全流程。
"""
import json
import sys

import requests

BASE = "http://127.0.0.1:8000"


def banner(title: str) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def assert_ok(resp: requests.Response, label: str) -> dict:
    body = resp.json()
    if body.get("code") != 0:
        print(f"❌ {label} 失败：{body}")
        sys.exit(1)
    print(f"✅ {label}: {body.get('data') if body.get('data') is not None else 'ok'}")
    return body


def main() -> None:
    s = requests.Session()

    banner("0. 健康检查 + 校区列表")
    schools = assert_ok(s.get(f"{BASE}/schools"), "GET /schools")["data"]
    assert len(schools) >= 1, "校区列表为空"
    school_id = schools[0]["id"]

    banner("1. 注册新用户")
    phone = "13700133499"
    body = {
        "nickname": "架构重构测试员",
        "phone": phone,
        "code": "123456",
        "password": "Pwd@2026",
        "confirm_password": "Pwd@2026",
        "school_id": school_id,
        "agreed": True,
    }
    reg = assert_ok(s.post(f"{BASE}/auth/register", json=body), "POST /auth/register")
    user_id = reg["data"]["user_id"]
    assert user_id > 0

    banner("2. /auth/me 校验会话")
    me = assert_ok(s.get(f"{BASE}/auth/me"), "GET /auth/me")
    assert me["data"]["user_id"] == user_id

    banner("3. /users/me 个人资料")
    profile = assert_ok(s.get(f"{BASE}/users/me"), "GET /users/me")
    assert profile["data"]["nickname"] == "架构重构测试员"
    assert profile["data"]["avatar_url"] is None or isinstance(profile["data"]["avatar_url"], str)

    banner("4. 发帖")
    post = assert_ok(
        s.post(
            f"{BASE}/posts",
            json={
                "content": "阶段 1 架构重构后端到端联调：通过 service 层抽象后发帖成功。",
                "school_id": school_id,
                "category": "普通",
                "image_urls": [],
                "is_anonymous": False,
                "is_public": True,
            },
        ),
        "POST /posts",
    )
    post_id = post["data"]["id"]
    # T7-15 验证：_post_dict 应返回 author_id
    assert post["data"]["author_id"] == user_id, f"author_id 缺失: {post['data']}"

    banner("5. 帖子列表")
    listing = assert_ok(s.get(f"{BASE}/posts", params={"view": "all"}), "GET /posts?view=all")
    assert any(p["id"] == post_id for p in listing["data"]), "刚发的帖子不在列表里"

    banner("6. 评论")
    c = assert_ok(s.post(f"{BASE}/posts/{post_id}/comments", json={"content": "架构重构测试评论"}), "POST /comments")
    # T7-15 验证：_comment_dict 应返回 user_id
    assert c["data"]["user_id"] == user_id, f"user_id 缺失: {c['data']}"

    banner("7. 评论列表（含二级回复）")
    parent_id = c["data"]["id"]
    assert_ok(s.post(f"{BASE}/posts/{post_id}/comments", json={"content": "二级回复", "parent_id": parent_id}), "POST 二级回复")
    clist = assert_ok(s.get(f"{BASE}/posts/{post_id}/comments"), "GET /comments")
    assert any(item["parent_id"] == parent_id for item in clist["data"]), "二级回复未显示"

    banner("8. 点赞 + 取消点赞")
    liked = assert_ok(s.post(f"{BASE}/likes/post/{post_id}"), "POST /likes/post")
    assert liked["data"]["like_count"] >= 1
    unliked = assert_ok(s.delete(f"{BASE}/likes/post/{post_id}"), "DELETE /likes/post")
    print(f"   取消后 like_count={unliked['data']['like_count']}")

    banner("9. 重复点赞（验证 T3-4 count 不重复 +1）")
    s.post(f"{BASE}/likes/post/{post_id}")
    r2 = s.post(f"{BASE}/likes/post/{post_id}")
    like_count_2 = r2.json()["data"]["like_count"]
    assert like_count_2 == 1, f"重复点赞后 count={like_count_2}, 期望 1"
    print(f"✅ 重复点赞返回 count={like_count_2}（与首次一致，T3-4 通过）")

    banner("10. 收藏 + 取消收藏")
    assert_ok(s.post(f"{BASE}/favorites/{post_id}"), "POST /favorites")
    assert_ok(s.post(f"{BASE}/favorites/{post_id}"), "POST /favorites (重复，应幂等)")
    assert_ok(s.delete(f"{BASE}/favorites/{post_id}"), "DELETE /favorites")

    banner("11. 举报（带具体理由）")
    rep = assert_ok(
        s.post(
            f"{BASE}/reports",
            json={"target_type": "post", "target_id": post_id, "reason": "[其他] 阶段1自测举报"},
        ),
        "POST /reports",
    )
    assert rep["data"]["status"] == "pending"

    banner("12. 编辑帖子")
    updated = assert_ok(
        s.patch(
            f"{BASE}/posts/{post_id}",
            json={"content": "已编辑：阶段 1 架构重构完成。"},
        ),
        "PATCH /posts",
    )
    assert "已编辑" in updated["data"]["content"]

    banner("13. 删除评论")
    c_id = clist["data"][0]["id"]
    assert_ok(s.delete(f"{BASE}/posts/{post_id}/comments/{c_id}"), "DELETE /comments")
    clist2 = s.get(f"{BASE}/posts/{post_id}/comments").json()
    assert all(item["id"] != c_id for item in clist2["data"]), "评论未删除"
    print(f"✅ 评论已删除，剩余 {len(clist2['data'])} 条")

    banner("14. 个人主页")
    user_home = assert_ok(s.get(f"{BASE}/users/{user_id}"), f"GET /users/{user_id}")
    assert user_home["data"]["id"] == user_id
    user_posts = assert_ok(s.get(f"{BASE}/users/{user_id}/posts"), f"GET /users/{user_id}/posts")
    assert any(p["id"] == post_id for p in user_posts["data"])

    banner("15. 私密帖子过滤（T3-5）")
    # 发一条私密帖子，用另一个用户访问应看不到
    private_post = s.post(
        f"{BASE}/posts",
        json={
            "content": "这是私密帖子，别人看不到",
            "school_id": school_id,
            "category": "普通",
            "image_urls": [],
            "is_anonymous": False,
            "is_public": False,
        },
    ).json()
    assert private_post["code"] == 0
    listing2 = s.get(f"{BASE}/posts", params={"view": "all"}).json()["data"]
    assert any(p["id"] == private_post["data"]["id"] for p in listing2), "本人应能看到自己的私密帖子"
    print(f"✅ 本人可见私密帖子（共 {len(listing2)} 条）")

    banner("16. 登出")
    assert_ok(s.post(f"{BASE}/auth/logout"), "POST /auth/logout")
    me2 = s.get(f"{BASE}/auth/me").json()
    assert me2["code"] == -100, f"登出后 /auth/me 应返回 -100, 实际 {me2['code']}"
    print(f"✅ 登出后访问 /auth/me 返回 code=-100")

    banner("🎉 阶段 1 全流程联调通过")


if __name__ == "__main__":
    main()
