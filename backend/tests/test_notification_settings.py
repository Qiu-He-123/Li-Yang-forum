"""通知偏好设置接口回归测试。"""

from tests.conftest import register


def test_notification_settings_default_and_update(client):
    """首次读取应返回默认全开，更新后返回最新值。"""
    register(client, "ns00000001", "通知设置用户A")

    # 默认全开
    r = client.get("/notifications/settings").json()
    assert r["code"] == 0
    s = r["data"]
    for key in ("like", "comment", "mention", "follow", "system", "dm"):
        assert s[key] is True

    # 更新部分字段
    r = client.put(
        "/notifications/settings",
        json={"like": False, "dm": False},
    ).json()
    assert r["code"] == 0
    s = r["data"]
    assert s["like"] is False
    assert s["dm"] is False
    assert s["comment"] is True
    assert s["follow"] is True

    # 再次读取保持一致
    r = client.get("/notifications/settings").json()
    assert r["data"]["like"] is False
    assert r["data"]["dm"] is False
    assert r["data"]["comment"] is True

    # 未知字段被忽略，不影响已有设置
    r = client.put("/notifications/settings", json={"not_a_real_key": True}).json()
    assert r["code"] == 0
    assert r["data"]["like"] is False


def test_notification_settings_requires_auth(client):
    """未登录访问设置接口应返回业务错误码（-100 未登录）。"""
    assert client.get("/notifications/settings").json()["code"] == -100
    assert client.put("/notifications/settings", json={"like": False}).json()["code"] == -100
