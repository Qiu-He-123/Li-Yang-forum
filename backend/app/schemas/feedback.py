from datetime import datetime
from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    category: str = Field(default="other", max_length=50)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    contact: str | None = Field(default=None, max_length=200)
    image_urls: list[str] | None = None


class FeedbackReplyCreate(BaseModel):
    content: str = Field(min_length=1)


class FeedbackReplyOut(BaseModel):
    id: int
    feedback_id: int
    replier_id: int
    replier_name: str | None = None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    category: str
    title: str
    content: str
    contact: str | None = None
    status: str
    image_urls: list[str] | None = None
    replies: list[FeedbackReplyOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackListOut(BaseModel):
    total: int
    items: list[FeedbackOut]
