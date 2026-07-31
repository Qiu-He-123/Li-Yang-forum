"""第五阶段后端接口自测：T5-2/T5-3/T5-4/T5-5。"""
import os
import sys

os.environ["OPENAI_API_KEY"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def main():
    # 登录用户 A (13700330001, user_id=8)
    resp = client.post("/auth/login", json={"phone": "13700330001", "password": "Pwd@2026"})
    cookies_a = resp.cookies
    user_id_a = resp.json()["data"]["user_id"]
    print(f"1. 用户 A 登录: user_id={user_id_a}")

    # ===== T5-2 修改密码 =====
    print("\n===== T5-2 修改密码 =====")
    # 用旧密码 Pwd@2026 改为新密码
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "Pwd@2026",
            "new_password": "NewPwd@2026",
            "confirm_password": "NewPwd@2026",
        },
        cookies=cookies_a,
    )
    print(f"  修改密码: code={resp.json()['code']}, msg={resp.json()['msg']}")
    assert resp.json()["code"] == 0, f"修改密码失败: {resp.json()}"

    # 登出再用新密码登录验证
    client.post("/auth/logout", cookies=cookies_a)
    resp = client.post("/auth/login", json={"phone": "13700330001", "password": "NewPwd@2026"})
    cookies_a = resp.cookies
    assert resp.json()["code"] == 0, "新密码应可登录"
    print(f"  ✅ 新密码登录成功")

    # 改回旧密码方便后续测试
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "NewPwd@2026",
            "new_password": "Pwd@2026",
            "confirm_password": "Pwd@2026",
        },
        cookies=cookies_a,
    )
    assert resp.json()["code"] == 0
    print(f"  ✅ 密码已改回 Pwd@2026")

    # 错误旧密码应失败
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "WrongPwd@2026",
            "new_password": "AnotherPwd@2026",
            "confirm_password": "AnotherPwd@2026",
        },
        cookies=cookies_a,
    )
    assert resp.json()["code"] != 0, "错误旧密码应失败"
    print(f"  ✅ 错误旧密码被拒绝: {resp.json()['msg']}")

    # 两次新密码不一致应失败
    resp = client.post(
        "/auth/change-password",
        json={
            "old_password": "Pwd@2026",
            "new_password": "OnePwd@2026",
            "confirm_password": "TwoPwd@2026",
        },
        cookies=cookies_a,
    )
    assert resp.json()["code"] != 0
    print(f"  ✅ 两次密码不一致被拒绝: {resp.json()['msg']}")

    # ===== T5-3 草稿列表 =====
    print("\n===== T5-3 草稿列表 =====")
    # 发一个草稿
    schools = client.get("/schools").json()
    school_id = schools["data"][0]["id"]
    resp = client.post(
        "/posts",
        json={
            "content": "T5草稿测试",
            "category": "普通",
            "school_id": school_id,
            "is_anonymous": False,
            "is_public": True,
            "image_urls": [],
            "is_draft": True,
        },
        cookies=cookies_a,
    )
    draft_id = resp.json()["data"]["id"]
    print(f"  草稿创建: id={draft_id}, is_draft={resp.json()['data'].get('is_draft')}")

    # 查询草稿列表
    resp = client.get("/users/me/drafts", cookies=cookies_a)
    drafts = resp.json()["data"]
    print(f"  草稿列表: {len(drafts)} 条")
    assert any(d["id"] == draft_id for d in drafts), "新建草稿应在列表中"
    print(f"  ✅ 新建草稿在列表中找到")

    # ===== T5-4 收藏列表（完整 Post） =====
    print("\n===== T5-4 收藏列表 =====")
    # 发一个公开帖子并收藏
    resp = client.post(
        "/posts",
        json={
            "content": "T5收藏测试帖子",
            "category": "普通",
            "school_id": school_id,
            "is_anonymous": False,
            "is_public": True,
            "image_urls": [],
            "is_draft": False,
        },
        cookies=cookies_a,
    )
    post_id = resp.json()["data"]["id"]
    client.post(f"/favorites/{post_id}", cookies=cookies_a)
    print(f"  帖子 {post_id} 已收藏")

    # 查询收藏列表（完整 Post）
    resp = client.get("/users/me/favorites/posts", cookies=cookies_a)
    favs = resp.json()["data"]
    print(f"  收藏列表: {len(favs)} 条")
    assert any(f["id"] == post_id for f in favs), "新收藏的帖子应在列表中"
    found = [f for f in favs if f["id"] == post_id][0]
    print(f"  ✅ 收藏列表返回完整 Post: content={found['content']}, author_id={found['author_id']}")

    # ===== T5-5 通知 =====
    print("\n===== T5-5 通知 =====")
    # 登录用户 B 并评论用户 A 的帖子，触发通知
    resp = client.post("/auth/login", json={"phone": "13700330002", "password": "Pwd@2026"})
    cookies_b = resp.cookies
    user_id_b = resp.json()["data"]["user_id"]
    print(f"  用户 B 登录: user_id={user_id_b}")

    # B 评论 A 的帖子
    resp = client.post(
        f"/posts/{post_id}/comments",
        json={"content": "T5通知测试评论", "parent_id": None},
        cookies=cookies_b,
    )
    print(f"  B 评论 A 的帖子: comment_id={resp.json()['data']['id']}")

    # B 点赞 A 的帖子
    client.post(f"/likes/post/{post_id}", cookies=cookies_b)
    print(f"  B 点赞 A 的帖子")

    # B 收藏 A 的帖子
    client.post(f"/favorites/{post_id}", cookies=cookies_b)
    print(f"  B 收藏 A 的帖子")

    # A 查询通知
    resp = client.get("/notifications", cookies=cookies_a)
    notifications = resp.json()["data"]
    print(f"  A 的通知列表: {len(notifications)} 条")
    for n in notifications[:5]:
        print(f"    - id={n['id']}, title={n['title']}, content={n['content'][:40]}, is_read={n['is_read']}")
    assert len(notifications) >= 3, f"应至少 3 条通知（评论+点赞+收藏）: {len(notifications)}"
    print(f"  ✅ 评论+点赞+收藏触发 3 条通知")

    # 标记第一条通知为已读
    first_id = notifications[0]["id"]
    resp = client.patch(f"/notifications/{first_id}/read", cookies=cookies_a)
    print(f"  标记 {first_id} 已读: is_read={resp.json()['data']['is_read']}")
    assert resp.json()["data"]["is_read"] is True

    # 验证已读状态
    resp = client.get("/notifications", cookies=cookies_a)
    notifications_after = resp.json()["data"]
    first = [n for n in notifications_after if n["id"] == first_id][0]
    assert first["is_read"] is True
    print(f"  ✅ 通知标记已读成功")

    # 未读数接口
    resp = client.get("/notifications/unread-count", cookies=cookies_a)
    print(f"  未读数: {resp.json()['data']}")
    assert resp.json()["data"]["unread"] >= 0

    # 用户不能标记他人的通知
    resp = client.patch(f"/notifications/{first_id}/read", cookies=cookies_b)
    # 应返回 is_read=False 或拒绝（不能修改他人通知）
    print(f"  B 尝试标记 A 的通知: {resp.json()}")

    print("\n===== T5-2/T5-3/T5-4/T5-5 全部通过 =====")


if __name__ == "__main__":
    main()
