from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


CATEGORIES = {"普通", "表白", "表白墙", "树洞", "匿名树洞", "失物招领", "二手", "二手市场", "跳蚤市场", "学习", "学习互助", "活动", "吐槽", "校园美食", "游戏开黑", "摄影", "随机匹配", "校园问答"}


def _validate_image_url(url: str) -> str:
    """T7-11：校验图片 URL 合法性，防止 XSS via image URL。

    允许：
    - http:// 或 https:// 开头的绝对 URL
    - /uploads/ 开头的相对路径（本地存储）
    禁止：
    - javascript: 协议
    - data: 协议（避免 base64 大图）
    - 其他非 HTTP 协议
    """
    if not url:
        raise ValueError("图片 URL 不能为空")
    url_lower = url.lower().strip()
    if url_lower.startswith(("http://", "https://")):
        return url
    if url_lower.startswith("/uploads/"):
        return url
    if url_lower.startswith(("javascript:", "data:", "vbscript:", "file:")):
        raise ValueError("图片 URL 不允许使用该协议")
    raise ValueError(f"图片 URL 必须以 http(s):// 或 /uploads/ 开头：{url[:50]}")


class PollCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    multi_vote: bool = False
    deadline: datetime | None = None
    options: list[str] = Field(min_length=2, max_length=6)


class PostCreate(BaseModel):
    # 草稿允许空 content（仅有标题/图片/投票也可保存）；正式发布需 content 非空
    content: str = Field(default="", max_length=5000)
    image_urls: list[str] = Field(default_factory=list, max_length=9)
    is_anonymous: bool = False
    is_public: bool = True
    school_id: int
    category: str = "普通"
    is_draft: bool = False
    # 圈子扩展：标题（可选）+ 是否原创 + 含AI内容声明
    title: str | None = Field(default=None, max_length=100)
    is_original: bool = False
    has_ai_content: bool = False
    # 阶段二新增字段
    topic_name: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=100)
    mention_user_ids: list[int] = Field(default_factory=list)
    poll: PollCreate | None = None

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, v: list[str]) -> list[str]:
        """T7-11：校验每个图片 URL，防止 XSS。"""
        return [_validate_image_url(url) for url in v]

    @model_validator(mode="after")
    def check_content_for_publish(self) -> "PostCreate":
        """正式发布（is_draft=False）时 content 不能为空；草稿允许空。"""
        if not self.is_draft and not self.content.strip():
            raise ValueError("内容不能为空")
        return self


class PostUpdate(BaseModel):
    # 草稿允许空 content；正式发布需 content 非空（在 model_validator 中校验）
    content: str | None = Field(default=None, max_length=5000)
    image_urls: list[str] | None = Field(default=None, max_length=9)
    is_anonymous: bool | None = None
    is_public: bool | None = None
    school_id: int | None = None
    category: str | None = None
    is_draft: bool | None = None
    # 圈子扩展字段
    title: str | None = Field(default=None, max_length=100)
    is_original: bool | None = None
    has_ai_content: bool | None = None
    # 阶段二新增字段
    topic_name: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=100)
    mention_user_ids: list[int] | None = None
    poll: PollCreate | None = None

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, v: list[str] | None) -> list[str] | None:
        """T7-11：校验每个图片 URL，防止 XSS。"""
        if v is None:
            return v
        return [_validate_image_url(url) for url in v]

    @model_validator(mode="after")
    def check_content_for_publish(self) -> "PostUpdate":
        """更新时：若显式设为正式发布（is_draft=False）且 content 为空字符串，则报错；
        草稿（is_draft=True）或未提供 content（None）时允许通过。"""
        if self.is_draft is False and self.content is not None and not self.content.strip():
            raise ValueError("内容不能为空")
        return self


class PostOut(BaseModel):
    id: int
    content: str
    image_urls: list[str]
    is_anonymous: bool
    category: str
    school: str
    author: str
    like_count: int
    comment_count: int
    tags: list[str]


# ============ 圈子（Category）相关 Schema ============
class CircleOut(BaseModel):
    """圈子列表项（含 is_joined 字段，由路由层填充）。"""

    id: int
    name: str
    slug: str
    icon: str | None = None
    description: str | None = None
    color: str = "#007aff"
    post_count: int = 0
    member_count: int = 0
    sort_order: int = 0
    is_active: bool = True
    is_joined: bool = False


class CircleDetailOut(BaseModel):
    """圈子详情。"""

    id: int
    name: str
    slug: str
    icon: str | None = None
    description: str | None = None
    color: str = "#007aff"
    post_count: int = 0
    member_count: int = 0
    sort_order: int = 0
    is_active: bool = True
    is_joined: bool = False
    created_at: datetime | None = None


# ============ 搜索相关 Schema ============
class SearchHistoryOut(BaseModel):
    """搜索历史项。"""

    id: int
    keyword: str
    created_at: datetime | None = None


class HotSearchOut(BaseModel):
    """热搜项。"""

    id: int | None = None
    keyword: str
    count: int = 0


# ============ 关注相关 Schema ============
class FollowOut(BaseModel):
    """关注/粉丝列表项。"""

    id: int
    user_id: int
    nickname: str
    avatar_url: str | None = None
    bio: str | None = None
    school: str | None = None
    grade: str | None = None
    created_at: datetime | None = None
