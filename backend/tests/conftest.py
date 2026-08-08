"""T9-1 回归测试公共 fixtures。

测试用 in-memory SQLite + AI 关闭，确保隔离、快速、可重复。
每个 test_xxx.py 通过 `client` fixture 拿到独立的 TestClient（带应用 startup 建表）。

注意：
- T7-9 IP 限流（每分钟 10 次）在测试场景下会快速触发，
  所以测试环境需放宽限流（设为 100000 次/窗口）。
- 每个测试函数执行前清空 rate_limits / login_failures 表，
  确保测试之间互不影响。
"""
import os
import sys
from pathlib import Path

# 确保环境变量在任何 app.* import 之前生效
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_TIMEOUT_SECONDS"] = "1"
os.environ["ENV"] = "dev"

# 让 tests/ 能 import app（如果从 backend/ 跑 pytest 已 OK，这里兜底）
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import app
from app.core.database import Base, SessionLocal, engine
from app.services import rate_limit_service

# 放宽测试环境的限流（避免快速注册/登录触发 429）
rate_limit_service.RATE_LIMIT_MAX_REQUESTS = 100000
rate_limit_service.RATE_LIMIT_WINDOW_SECONDS = 1
rate_limit_service.LOGIN_FAIL_THRESHOLD = 100000  # 测试中不锁定


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """session 级：在所有测试前确保 schema 已创建。

    关键修复：原 conftest 在 client fixture 中尝试 DELETE FROM rate_limits，
    但表直到 TestClient 进入 with 才由 startup 创建，第一个测试会触发
    `no such table: rate_limits`。这里先手动 create_all 一次（仅 in-memory 测试 DB），
    后续 TestClient 启动时 ensure_schema 会跳过（已有 alembic_version 表）。
    """
    import app.models  # noqa: F401  保证所有模型注册到 Base.metadata

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables or "alembic_version" not in existing_tables:
        # 空库：直接 create_all 建全部表（dev 兜底路径）
        Base.metadata.create_all(bind=engine)
        # 写入 alembic_version 标记为 head，避免后续 TestClient 启动重复迁移
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
            conn.exec_driver_sql("DELETE FROM alembic_version")
            # 用参数化查询避免 B608 SQL 注入误报
            conn.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES (?)",
                ("head",),
            )
    yield


def _safe_clear(table_name: str) -> None:
    """安全清空表（表不存在时跳过）。"""
    with SessionLocal() as db:
        try:
            db.execute(text(f"DELETE FROM {table_name}"))
            db.commit()
        except Exception:
            # 表可能尚未创建（首个测试），忽略
            db.rollback()


@pytest.fixture()
def client():
    """每个测试函数独立 client（共享 in-memory DB，但清空限流表）。"""
    # 清空限流表，确保上一个测试的计数不污染当前测试
    _safe_clear("rate_limits")
    _safe_clear("login_failures")

    with TestClient(app) as c:
        yield c

    # 测试结束后再次清空
    _safe_clear("rate_limits")
    _safe_clear("login_failures")


# ============ 通用辅助 ============

def register(
    client: TestClient,
    username: str,
    nickname: str = "测试员",
    password: str = "Pwd@2026",
    invite_code: str | None = "__seed__",
) -> dict:
    """注册并返回 {school_id, user_id}（当前契约为 用户名+密码，邀请码选填）。

    默认 invite_code="__seed__"：自动消耗一个种子邀请码，注册即 verified，
    保证发帖/评论等测试可执行；需要测 unverified 场景时显式传 invite_code=None。
    """
    if invite_code == "__seed__":
        from sqlalchemy import select
        from app.core.database import SessionLocal
        from app.models import SeedInviteCode

        with SessionLocal() as db:
            seed = db.scalar(
                select(SeedInviteCode).where(SeedInviteCode.used_by.is_(None))
            )
            assert seed is not None, "测试环境应存在种子邀请码"
            invite_code = seed.code
    schools = client.get("/schools").json()["data"]
    school_id = schools[0]["id"]
    body = {
        "nickname": nickname,
        "username": username,
        "password": password,
        "confirm_password": password,
        "school_id": school_id,
        "agreed": True,
        "invite_code": invite_code,
    }
    resp = client.post("/auth/register", json=body).json()
    assert resp["code"] == 0, f"register failed: {resp}"
    return {"school_id": school_id, "user_id": resp["data"]["user_id"]}


def create_post(client: TestClient, school_id: int, content: str, is_public: bool = True, is_draft: bool = False, category: str = "普通") -> dict:
    body = {
        "content": content,
        "school_id": school_id,
        "category": category,
        "image_urls": [],
        "is_anonymous": False,
        "is_public": is_public,
        "is_draft": is_draft,
    }
    resp = client.post("/posts", json=body).json()
    assert resp["code"] == 0, f"create post failed: {resp}"
    return resp["data"]
