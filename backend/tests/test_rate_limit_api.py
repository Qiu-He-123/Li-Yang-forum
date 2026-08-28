"""反爬限流中间件测试：写接口按 IP 限流，超限返回 RATE_LIMITED。"""

import app.main as main_mod
from app.core.errors import ErrorCode
from app.services import rate_limit_service


def test_write_api_rate_limit(client):
    """同一 IP 的写请求超过阈值后，第 3 次返回 RATE_LIMITED。"""
    original_action = main_mod._write_limit_for
    original_window = rate_limit_service.RATE_LIMIT_WINDOW_SECONDS
    main_mod._write_limit_for = lambda path: ("test_write", 2)
    rate_limit_service.RATE_LIMIT_WINDOW_SECONDS = 60
    try:
        body = {"username": "nobody", "password": "BadPwd@1"}
        headers = {"X-Forwarded-For": "203.0.113.55"}
        for _ in range(2):
            resp = client.post("/api/auth/login", json=body, headers=headers)
            assert resp.status_code == 200  # 前两次放行，业务侧返回登录失败
        resp = client.post("/api/auth/login", json=body, headers=headers)
        data = resp.json()
        assert data["code"] == ErrorCode.RATE_LIMITED
        assert "频繁" in data["msg"]
    finally:
        main_mod._write_limit_for = original_action
        rate_limit_service.RATE_LIMIT_WINDOW_SECONDS = original_window
