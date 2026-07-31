"""漂流瓶 API 路由。

- GET  /bottles/tags：获取预设兴趣标签
- POST /bottles：投放瓶子
- POST /bottles/pick：拾取瓶子（按标签匹配）
- POST /bottles/{bottle_id}/recall：作者收回瓶子
- GET  /bottles/mine：我投放的瓶子列表
- GET  /bottles/picks：我拾取过的瓶子列表
- GET  /bottles/pick-status：今日拾取状态（剩余次数）
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import bottle_service

router = APIRouter(prefix="/bottles", tags=["bottles"])


class BottleCreatePayload(BaseModel):
    content: str | None = Field(default=None, max_length=2000)
    image_urls: list[str] = Field(default_factory=list)
    # 旧字段：grade（可选，向后兼容；新逻辑以年龄为主）
    grade: str | None = Field(default=None, pattern="^(初一|初二|初三|高一|高二|高三)$")
    school_id: int
    tags: list[str] = Field(default_factory=list)
    # 联系方式（QQ/微信/手机等），拾取成功后对拾取者可见
    contact: str | None = Field(default=None, max_length=100)


class BottlePickPayload(BaseModel):
    # 旧字段：grades（向后兼容，已不推荐使用）
    grades: list[str] = Field(default_factory=list)
    school_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # 必须有的标签：瓶子必须包含这些标签才能匹配到
    tag_required: list[str] = Field(default_factory=list)
    # 尽量有的标签：候选中按重叠度排序优先
    tag_preferred: list[str] = Field(default_factory=list)
    target_gender: str = Field(default="any", pattern="^(male|female|any)$")
    # 年龄系统：期望作者年龄范围（13-18，None 表示不限）
    age_min: int | None = Field(default=None, ge=13, le=18)
    age_max: int | None = Field(default=None, ge=13, le=18)


@router.get("/tags")
def list_tags() -> dict:
    """获取预设兴趣标签列表。"""
    return ok(bottle_service.list_interest_tags())


@router.post("")
def create_bottle(
    payload: BottleCreatePayload,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """投放漂流瓶：需要 verified 状态（已填邀请码）。

    author_age 自动从 user.birthday 计算，前端无需传年龄。
    """
    return ok(bottle_service.create_bottle(
        db,
        user,
        content=payload.content,
        image_urls=payload.image_urls,
        school_id=payload.school_id,
        tags=payload.tags,
        contact=payload.contact,
        grade=payload.grade,
    ))


@router.post("/pick")
def pick_bottle(
    payload: BottlePickPayload,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """拾取漂流瓶：需要 verified 状态（已填邀请码）。"""
    return ok(bottle_service.pick_bottle(
        db,
        user,
        school_ids=payload.school_ids,
        tags=payload.tags,
        tag_required=payload.tag_required,
        tag_preferred=payload.tag_preferred,
        target_gender=payload.target_gender,
        age_min=payload.age_min,
        age_max=payload.age_max,
        grades=payload.grades,
    ))


@router.get("/mine")
def my_bottles(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我投放的瓶子列表。"""
    return ok(bottle_service.my_bottles(db, user))


@router.post("/{bottle_id}/recall")
def recall_bottle(
    bottle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """作者主动收回瓶子，收回后不再可被拾取。"""
    return ok(bottle_service.recall_bottle(db, user, bottle_id))


@router.get("/picks")
def my_picks(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """我拾取过的瓶子列表。"""
    return ok(bottle_service.my_picks(db, user))


@router.get("/pick-status")
def pick_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """今日拾取状态（剩余次数）。"""
    return ok(bottle_service.get_pick_status(db, user))
