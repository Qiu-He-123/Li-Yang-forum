from datetime import date

from pydantic import BaseModel, Field


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


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=5000)
    school_id: int | None = None
    is_active: bool = True
