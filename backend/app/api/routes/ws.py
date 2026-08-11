"""WebSocket 端点。

支持鉴权（query 参数 access_token）和心跳，注册到全局 ConnectionManager。

消息协议（客户端发送）：
- {"type": "ping"}：心跳，服务端返回 {"type":"pong"}
- {"type": "match_chat", "session_id": int, "content": str}：临时会话发消息
- {"type": "match_follow", "session_id": int}：临时会话关注对方
- {"type": "match_request_follow", "session_id": int}：临时会话求关注
- {"type": "match_end", "session_id": int}：主动结束会话

服务端推送消息类型：
- {"type": "pong"}
- {"type": "match_found", "session_id": int, "peer": {...}, "expires_at": iso}
- {"type": "match_chat", "session_id": int, "sender_id": int, "content": str, "created_at": iso}
- {"type": "match_follow_event", "session_id": int, "follower_id": int, "is_mutual": bool}
- {"type": "match_request_follow", "session_id": int, "from_id": int}
- {"type": "match_end", "session_id": int, "reason": "timeout"|"manual"|"mutual_follow"}
- {"type": "match_timeout", "session_id": int}（未匹配到对方时）
"""
import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import jwt

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models import User
from app.services.connection_manager import manager
from app.services import match_service

router = APIRouter(tags=["websocket"])


async def _delayed_cleanup(uid: int) -> None:
    """WS 断开后延迟 5 秒清理匹配状态。

    容忍 WS 短暂断开重连（如网络抖动、页面切换）：
    5 秒后如果用户重新上线（is_online=True），则不清理 waiting/session。
    """
    await asyncio.sleep(5)
    with SessionLocal() as db:
        match_service.cleanup_user_waiting(db, uid)
        match_service.cleanup_user_session(db, uid)


def _authenticate(token: str | None) -> int | None:
    """从 access_token 解析 user_id；失败返回 None。"""
    if not token:
        return None
    try:
        return int(decode_token(token))
    except (jwt.InvalidTokenError, ValueError):
        return None


def _extract_token(websocket: WebSocket, query_token: str | None) -> str | None:
    """从 query 参数或 Cookie 中提取 access_token。

    WebSocket 请求会自动携带同源 Cookie（包括 httponly 的 access_token），
    所以优先从 Cookie 头解析；query 参数作为兼容方案保留。
    """
    if query_token:
        return query_token
    # 从 Cookie 头解析 access_token
    cookie_header = websocket.headers.get("cookie", "")
    if not cookie_header:
        return None
    for item in cookie_header.split(";"):
        item = item.strip()
        if item.startswith("access_token="):
            return item[len("access_token="):]
    return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """主 WebSocket 端点。

    鉴权方式（优先级）：
    1. query 参数 token（兼容方案）
    2. Cookie 中的 access_token（浏览器 WebSocket 自动携带同源 Cookie）

    未登录用户以游客身份连接（user_id=0），仅参与在线人数统计和心跳，
    不能使用匹配相关功能。
    """
    # P2：Origin 校验，禁止跨站 WebSocket 连接（配合 SameSite=Strict 双保险）
    settings = get_settings()
    allowed_origins = {settings.frontend_origin}
    if settings.extra_origins:
        allowed_origins.update(
            o.strip() for o in settings.extra_origins.split(",") if o.strip()
        )
    origin = websocket.headers.get("origin")
    if origin and origin not in allowed_origins:
        # 同源请求直接放行（本机 127.0.0.1:8000 / 2599、任意穿透域名都能用），
        # 否则 Origin 不在白名单时 WebSocket 被掐断，在线统计永远为 0
        origin_host = urlparse(origin).netloc
        request_host = websocket.headers.get("host", "")
        if origin_host != request_host:
            await websocket.close(code=4403)
            return

    user_id = _authenticate(_extract_token(websocket, token))
    is_visitor = False
    if not user_id:
        # 游客连接：允许建立 WebSocket，但只能做心跳，不能用匹配功能
        user_id = manager.VISITOR_USER_ID
        is_visitor = True
    else:
        # 校验登录用户存在且未封号
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if not user:
                await websocket.close(code=4401)
                return
            from app.api.deps import _is_user_banned
            if _is_user_banned(user):
                await websocket.close(code=4403)
                return

    client_id = await manager.connect(user_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif is_visitor:
                # 游客只能发心跳，其他操作忽略
                continue
            elif msg_type == "match_chat":
                session_id = message.get("session_id")
                content = (message.get("content") or "").strip()
                if session_id and content:
                    await match_service.handle_match_chat(user_id, int(session_id), content)
            elif msg_type == "match_follow":
                session_id = message.get("session_id")
                if session_id:
                    await match_service.handle_match_follow(user_id, int(session_id))
            elif msg_type == "match_request_follow":
                session_id = message.get("session_id")
                if session_id:
                    await match_service.handle_match_request_follow(user_id, int(session_id))
            elif msg_type == "match_end":
                session_id = message.get("session_id")
                if session_id:
                    await match_service.handle_match_end(user_id, int(session_id))
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, client_id)
        # 登录用户断开 WebSocket 时，延迟 5 秒清理匹配状态
        # 延迟是为了容忍 WS 短暂断开重连（如网络抖动、页面切换）：
        # 5 秒内用户重连则 is_online=True，cleanup_user_waiting 不取消匹配
        if not is_visitor:
            asyncio.create_task(_delayed_cleanup(user_id))
