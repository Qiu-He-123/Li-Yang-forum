from datetime import date

from pydantic import BaseModel, Field, field_validator


def _validate_profile_image_url(url: str | None) -> str | None:
    """头像/背景图 URL 校验（防外链追踪去匿名化 + 防 XSS via URL）。

    只允许站内同源路径：
    - /uploads/（本地存储）
    - /minio/（MinIO 同源反代）
    禁止外部 http(s) 绝对 URL（可被攻击者用于 IP 记录/去匿名化）、
    以及 javascript:/data:/vbscript:/file: 等危险协议。
    """
    if not url:
        return url
    url_lower = url.lower().strip()
    if url_lower.startswith(("/uploads/", "/minio/")):
        return url
    raise ValueError("头像/背景图 URL 仅支持站内路径（/uploads/ 或 /minio/）")


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: int | None = None


class ReportCreate(BaseModel):
    target_type: str = Field(pattern="^(post|comment|user)$")
    target_id: int
    reason: str = Field(min_length=1, max_length=200)


class ProfileUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=500)
    background_url: str | None = Field(default=None, max_length=500)
    bio: str | None = Field(default=None, max_length=200)
    # 校区切换（我的页点头校区直接修改）
    school_id: int | None = Field(default=None)
    grade: str | None = Field(default=None, max_length=20)
    # 生日（设置后动态计算年龄，替代 grade）
    birthday: date | None = Field(default=None)
    # 性别：male / female / unknown（用于漂流瓶和实时匹配）
    gender: str | None = Field(default=None, pattern="^(male|female|unknown)$")

    @field_validator("avatar_url", "background_url")
    @classmethod
    def validate_profile_image_url(cls, v: str | None) -> str | None:
        return _validate_profile_image_url(v)


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=5000)
    school_id: int | None = None
    is_active: bool = True
    # 可见范围：all=所有人 / guest=仅游客(同一IP只投递一次) / user=仅登录用户
    scope: str = Field(default="all", pattern="^(all|guest|user)$")
