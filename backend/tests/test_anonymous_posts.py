"""匿名帖隐私：他人无法在作者主页看到匿名帖，仅作者本人可见。"""

from tests.conftest import create_post, register


def test_anonymous_post_hidden_on_profile_for_others(client):
    c = register(client, "anon_author")
    # 匿名发一篇帖子
    body = {
        "content": "这是匿名发布的帖子内容，内容足够长满足最小字数",
        "school_id": c["school_id"],
        "category": "普通",
        "image_urls": [],
        "is_anonymous": True,
        "is_public": True,
        "is_draft": False,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] == 0, resp
    anon_post_id = resp["data"]["id"]
    # 再发一条实名帖作对照
    normal = create_post(client, c["school_id"], "这是实名发布的帖子内容，内容足够长")

    # D 查看 C 主页：看不到匿名帖，但能看到实名帖
    register(client, "anon_viewer_d")
    resp = client.get(f"/users/{c['user_id']}/posts").json()
    assert resp["code"] == 0, resp
    ids = [p["id"] for p in resp["data"]["items"]]
    assert normal["id"] in ids
    assert anon_post_id not in ids

    # C 本人登录后可见自己的匿名帖
    resp = client.post("/auth/login", json={"username": "anon_author", "password": "Pwd@2026"}).json()
    assert resp["code"] == 0, resp
    resp = client.get(f"/users/{c['user_id']}/posts").json()
    assert resp["code"] == 0, resp
    ids2 = [p["id"] for p in resp["data"]["items"]]
    assert anon_post_id in ids2
