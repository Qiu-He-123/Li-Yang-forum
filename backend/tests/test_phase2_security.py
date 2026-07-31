"""阶段 2 安全与鉴权修复 端到端测试。

覆盖：
- T2-1 admin 鉴权依赖（未带 Cookie 访问 /admin/* 返回 401）
- T2-2 admin 登录改 Body + 下发 Cookie
- T2-3 移除默认后门 + CLI 脚本
- T2-4 jwt_secret 校验（仅检查代码逻辑，不真的启动 prod）
- T2-5 logout 撤销 refresh_token
- T2-6 refresh token 接口
"""
import subprocess
import sys

import requests

BASE = "http://127.0.0.1:8000"


def banner(title: str) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def assert_code(body: dict, expected_code: int, label: str) -> None:
    if body.get("code") != expected_code:
        print(f"❌ {label} 失败：期望 code={expected_code}, 实际 {body}")
        sys.exit(1)
    print(f"✅ {label}: code={expected_code}")


def main() -> None:
    s = requests.Session()

    banner("T2-1 未带 Cookie 访问 /admin/posts 返回 -100 NOT_LOGGED_IN")
    body = s.get(f"{BASE}/admin/posts").json()
    assert_code(body, -100, "GET /admin/posts (未鉴权)")

    banner("T2-1 未带 Cookie 访问 /admin/users 返回 -100")
    body = s.get(f"{BASE}/admin/users").json()
    assert_code(body, -100, "GET /admin/users (未鉴权)")

    banner("T2-1 未带 Cookie 访问 /admin/reports 返回 -100")
    body = s.get(f"{BASE}/admin/reports").json()
    assert_code(body, -100, "GET /admin/reports (未鉴权)")

    banner("T2-1 未带 Cookie 访问 /admin/logs 返回 -100")
    body = s.get(f"{BASE}/admin/logs").json()
    assert_code(body, -100, "GET /admin/logs (未鉴权)")

    banner("T2-3 空数据库访问 /admin/login 返回 -103 LOGIN_FAILED（后门已移除）")
    # 注：当前数据库可能已有 admin，先尝试登录错误密码
    body = s.post(
        f"{BASE}/admin/login",
        json={"username": "nonexistent_admin_xyz", "password": "wrong_pwd"},
    ).json()
    assert_code(body, -103, "POST /admin/login (不存在用户)")

    banner("T2-2 旧式 URL query 登录应失败（密码不再走 URL）")
    # 旧式：?username=admin&password=xxx 应该返回 Pydantic 校验错误（缺少 Body）
    body = s.post(f"{BASE}/admin/login?username=admin&password=admin123456").json()
    # FastAPI 会因为缺少 Body 报 PARAM_ERROR
    assert body["code"] != 0, f"URL query 登录应失败：{body}"
    print(f"✅ URL query 登录被拒绝: code={body['code']}")

    banner("T2-3 通过 CLI 脚本创建管理员")
    result = subprocess.run(
        [sys.executable, "scripts/create_admin.py", "phase2_admin", "Admin@2026Pwd"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    if result.returncode != 0 and "已存在" not in result.stderr:
        print(f"❌ CLI 创建失败：{result.stderr}")
        sys.exit(1)
    print(f"✅ CLI 脚本执行成功: {result.stdout.strip() or result.stderr.strip()}")

    banner("T2-2 用 Body + 正确密码登录，应返回 admin_token Cookie")
    resp = s.post(
        f"{BASE}/admin/login",
        json={"username": "phase2_admin", "password": "Admin@2026Pwd"},
    )
    body = resp.json()
    assert_code(body, 0, "POST /admin/login (正确密码)")
    assert "admin_token" in resp.cookies, "Set-Cookie 未下发 admin_token"
    print(f"✅ admin_token Cookie 已下发: {resp.cookies['admin_token'][:30]}...")

    banner("T2-2 带 admin_token Cookie 访问 /admin/posts 应成功")
    body = s.get(f"{BASE}/admin/posts").json()
    assert_code(body, 0, "GET /admin/posts (已鉴权)")

    banner("T2-2 带 admin_token Cookie 访问 /admin/logs 应成功")
    body = s.get(f"{BASE}/admin/logs").json()
    assert_code(body, 0, "GET /admin/logs (已鉴权)")
    # 验证 T7-6：日志含 admin_id
    if body["data"]:
        admin_logs = [log for log in body["data"] if log.get("admin_id")]
        if admin_logs:
            print(f"✅ T7-6: 日志含 admin_id（最新一条 admin_id={admin_logs[0]['admin_id']}）")

    banner("T2-2 用错误密码登录应返回 -103 LOGIN_FAILED")
    body = s.post(
        f"{BASE}/admin/login",
        json={"username": "phase2_admin", "password": "wrong_password"},
    ).json()
    assert_code(body, -103, "POST /admin/login (错误密码)")

    banner("T2-2 admin 登出（清 admin_token Cookie）")
    body = s.post(f"{BASE}/admin/logout").json()
    assert_code(body, 0, "POST /admin/logout")
    # 登出后再访问应 401
    body = s.get(f"{BASE}/admin/posts").json()
    assert_code(body, -100, "GET /admin/posts (登出后)")

    banner("T2-5 + T2-6 用户 refresh_token 流程")
    # 先注册一个用户
    schools = s.get(f"{BASE}/schools").json()
    school_id = schools["data"][0]["id"]
    phone = "13700233456"
    s.post(
        f"{BASE}/auth/register",
        json={
            "nickname": "T2-测试员",
            "phone": phone,
            "code": "123456",
            "password": "Pwd@2026",
            "confirm_password": "Pwd@2026",
            "school_id": school_id,
            "agreed": True,
        },
    )

    # 登录拿 access_token + refresh_token
    login_resp = s.post(f"{BASE}/auth/login", json={"phone": phone, "password": "Pwd@2026"})
    body = login_resp.json()
    assert_code(body, 0, "POST /auth/login")
    assert "refresh_token" in login_resp.cookies, "登录未下发 refresh_token Cookie"
    refresh_token = login_resp.cookies["refresh_token"]
    print(f"✅ refresh_token Cookie 已下发: {refresh_token[:30]}...")

    banner("T2-6 用 refresh_token 调 /auth/refresh 应返回新 access_token")
    refresh_resp = s.post(f"{BASE}/auth/refresh")
    body = refresh_resp.json()
    assert_code(body, 0, "POST /auth/refresh")
    assert "access_token" in refresh_resp.cookies, "refresh 未下发新 access_token"
    assert "refresh_token" in refresh_resp.cookies, "refresh 未下发新 refresh_token"
    new_refresh = refresh_resp.cookies["refresh_token"]
    print(f"✅ 新 access_token 下发: {refresh_resp.cookies['access_token'][:30]}...")
    print(f"✅ 轮转后新 refresh_token: {new_refresh[:30]}...")

    banner("T2-6 旧 refresh_token 已 revoked，再用应失败 -101")
    # 用旧 refresh_token 单独请求
    s2 = requests.Session()
    s2.cookies.set("refresh_token", refresh_token, domain="127.0.0.1")
    body = s2.post(f"{BASE}/auth/refresh").json()
    assert_code(body, -101, "POST /auth/refresh (旧已 revoke)")

    banner("T2-5 登出后用 refresh_token 调 /auth/refresh 应失败 -101")
    s.post(f"{BASE}/auth/logout")
    body = s.post(f"{BASE}/auth/refresh").json()
    assert_code(body, -101, "POST /auth/refresh (登出后)")

    banner("T2-4 jwt_secret 校验代码逻辑（静态检查）")
    with open("app/main.py", encoding="utf-8") as f:
        content = f.read()
    if "jwt_secret == \"change-me\"" in content and "RuntimeError" in content:
        print("✅ main.py 含 jwt_secret 校验逻辑")
    else:
        print("❌ main.py 缺少 jwt_secret 校验逻辑")
        sys.exit(1)

    banner("T2-3 CLI 脚本文件存在")
    import os
    if os.path.exists("scripts/create_admin.py"):
        print("✅ scripts/create_admin.py 存在")
    else:
        print("❌ scripts/create_admin.py 不存在")
        sys.exit(1)

    banner("🎉 阶段 2 安全与鉴权修复 全部通过")


if __name__ == "__main__":
    main()
