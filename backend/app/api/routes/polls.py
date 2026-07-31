"""投票路由（阶段二）。

提供投票、获取投票详情。投票 CRUD 通过发帖流程创建，本路由仅做投票与查询。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.models import User
from app.schemas.common import ok
from app.services import poll_service

router = APIRouter(prefix="/polls", tags=["polls"])


class VoteRequest(BaseModel):
    """投票请求体（支持单选/多选）。"""
    option_ids: list[int] = Field(min_length=1, max_length=6)


@router.post("/{post_id}/vote")
def vote(
    post_id: int,
    payload: VoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """对帖子 {post_id} 关联的投票进行投票（需登录）。

    请求体：option_ids（必填，数组）
    - 单选投票（multi_vote=False）：option_ids 仅取第一个；用户已投过任意选项则 400
    - 多选投票（multi_vote=True）：允许提交多个选项；同一选项重复投递由唯一约束拦截
    - 投票已截止：403
    """
    poll = poll_service.vote(db, user, post_id, payload.option_ids)
    return ok({"poll": poll})


@router.get("/{post_id}")
def get_poll(
    post_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    """获取帖子 {post_id} 关联的投票详情（含选项、投票数、当前用户是否已投）。

    未登录用户 voted 字段全为 False。
    """
    data = poll_service.get_poll_detail(db, post_id, user=user)
    if data is None:
        raise HTTPException(status_code=404, detail=ErrorCode.POST_NOT_FOUND)
    return ok(data)
