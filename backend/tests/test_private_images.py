"""P0-1 / P1-3 回归测试：私密图片访问控制 + 学生认证图片归属校验。"""
import base64

from tests.conftest import register

# 1x1 透明 PNG（通过 magic bytes 校验）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_private_verification_image_access_control(client):
    """私密图片只能本人读取，他人/未登录均 403。"""
    register(client, "user_pv_a", "隐私A")
    resp = client.post(
        "/images/verification",
        files={"file": ("id.png", PNG_1PX, "image/png")},
    ).json()
    assert resp["code"] == 0, f"私密上传失败: {resp}"
    url = resp["data"]["url"]
    assert url.startswith("/images/private/"), "私密图片应走 /images/private/* 鉴权路径"

    # 本人可读
    r = client.get(url)
    assert r.status_code == 200

    # 他人不可读
    client.post("/auth/logout")
    register(client, "user_pv_b", "隐私B")
    r = client.get(url)
    assert r.json()["code"] != 0, "他人访问私密图片应被拒绝"

    # 未登录不可读
    client.post("/auth/logout")
    r = client.get(url)
    assert r.json()["code"] != 0, "未登录访问私密图片应被拒绝"


def test_verification_submit_requires_own_private_image(client):
    """学生认证必须使用本人私密上传的图片，拒绝公开图片与他人图片。"""
    register(client, "user_vs_a", "认证A", invite_code=None)
    priv = client.post(
        "/images/verification",
        files={"file": ("id.png", PNG_1PX, "image/png")},
    ).json()["data"]
    pub = client.post(
        "/images",
        files={"file": ("p.png", PNG_1PX, "image/png")},
    ).json()["data"]

    # 公开图片 id 不能用于认证
    r = client.post("/users/me/verification", json={"image_id": pub["id"]}).json()
    assert r["code"] != 0, "公开图片不应能用于学生认证"

    # 自己的私密图片可以
    r = client.post("/users/me/verification", json={"image_id": priv["id"]}).json()
    assert r["code"] == 0, f"本人私密图片认证应成功: {r}"

    # 引用他人私密图片被拒
    client.post("/auth/logout")
    register(client, "user_vs_b", "认证B", invite_code=None)
    r = client.post("/users/me/verification", json={"image_id": priv["id"]}).json()
    assert r["code"] != 0, "不应能引用他人私密图片"
