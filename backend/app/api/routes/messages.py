"""好友与私信路由（抖音/快手风格重构）。

路径设计：
- /friends/*          好友关系管理（保留，个人主页也可申请）
- /friends/requests   好友请求
- /friends/search     搜索用户
- /messages/*         私信（基于互关 + 权限）
- /messages/permission 私信权限管理
- /messages/check/{user_id} 预检能否发消息

稳定性设计：
- /messages POST 发送成功后，通过 WebSocket 实时推送 dm_message 事件给接收方，
  避免接收方依赖 5 秒轮询才能看到新消息（参考大厂网页聊天实现）。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import message_service
from app.services.connection_manager import manager

router = APIRouter(tags=["friends-messages"])


# ============ Schema ============
class FriendRequestIn(BaseModel):
    to_id: int
    message: str | None = Field(default=None, max_length=200)


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    msg_type: str = Field(default="text", pattern="^(text|image|voice)$")


class MessagePermissionIn(BaseModel):
    message_permission: str = Field(pattern="^(everyone|mutual_only|stranger_once|no_stranger)$")


# ============ 好友请求接口 ============

@router.post("/friends/requests")
def send_friend_request(
    payload: FriendRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """发送好友请求。"""
    return ok(message_service.send_friend_request(db, user, payload.to_id, payload.message))


@router.patch("/friends/requests/{request_id}/accept")
def accept_friend_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """接受好友请求。"""
    return ok(message_service.accept_friend_request(db, user, request_id))


@router.patch("/friends/requests/{request_id}/reject")
def reject_friend_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """拒绝好友请求。"""
    return ok(message_service.reject_friend_request(db, user, request_id))


@router.get("/friends/requests")
def list_friend_requests(
    direction: str = Query(default="incoming", pattern="^(incoming|outgoing)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取好友请求列表。"""
    return ok(message_service.list_friend_requests(db, user, direction))


@router.get("/friends")
def list_friends(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取好友列表。"""
    return ok(message_service.list_friends(db, user))


@router.get("/friends/search")
def search_users(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """搜索用户（添加好友用）。"""
    return ok(message_service.search_users(db, user, q))


# ============ 私信权限管理 ============

@router.get("/messages/permission")
def get_message_permission(
    user: User = Depends(current_user),
) -> dict:
    """获取当前用户的私信权限设置。"""
    return ok(message_service.get_message_permission(user))


@router.patch("/messages/permission")
def update_message_permission(
    payload: MessagePermissionIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """更新当前用户的私信权限设置。"""
    return ok(message_service.update_message_permission(db, user, payload.message_permission))


@router.get("/messages/check/{user_id}")
def check_can_send(
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """预检：当前用户能否给 user_id 发消息。"""
    return ok(message_service.check_can_send(db, user, user_id))


# ============ 私信接口 ============

@router.post("/messages")
async def send_message(
    payload: SendMessageIn,
    receiver_id: int = Query(..., description="接收者用户 ID"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """发送私信（互关自由发，陌生人受权限控制）。

    稳定性优化：写库成功后通过 WebSocket 实时推送 dm_message 事件给接收方，
    接收方前端无需等待 5 秒轮询即可看到新消息。WS 推送失败不影响消息持久化。
    """
    result = message_service.send_message(db, user, receiver_id, payload.content, payload.msg_type)
    # 实时推送：通知接收方有新消息（即使接收方不在线也忽略，下次进入页面会拉取）
    try:
        await manager.send_to_user(receiver_id, {
            "type": "dm_message",
            "id": result["id"],
            "sender_id": result["sender_id"],
            "receiver_id": result["receiver_id"],
            "content": result["content"],
            "msg_type": result["msg_type"],
            "read_at": result.get("read_at"),
            "created_at": result["created_at"],
        })
    except Exception:
        # WS 推送失败不影响 HTTP 响应（消息已持久化，接收方下次拉取能拿到）
        pass
    return ok(result)


@router.get("/messages/{friend_id}")
def get_messages(
    friend_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取与用户的聊天记录（含关系状态）。"""
    return ok(message_service.get_messages(db, user, friend_id, page, page_size))


@router.get("/messages")
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取会话列表（仅包含有消息记录的会话）。"""
    return ok(message_service.list_conversations(db, user))
