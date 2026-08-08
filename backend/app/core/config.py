from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "立洋校园社区"
    env: str = "dev"
    database_url: str = "sqlite:///./ly_community.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 180
    refresh_token_expire_days: int = 30
    frontend_origin: str = "http://localhost:5173"
    # 额外允许的前端来源（多个用逗号分隔），用于内网穿透/外网域名场景
    extra_origins: str = ""
    ai_provider: str = "OpenAI"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ly-community"
    minio_private_bucket: str = "ly-community-private"
    minio_secure: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 30
    # 邀请码系统：管理员微信号（前端弹窗展示，用于学生获取种子邀请码）
    admin_wechat: str = "qhsqq2623655749"
    # 启动时自动生成的种子邀请码数量（冷启动用，已存在则跳过）
    seed_invite_code_count: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
