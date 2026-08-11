"""WebSocket 连接管理器。

管理用户与 WebSocket 连接的映射，支持：
- 用户上线/下线注册
- 点对点消息推送（实时匹配会话通知、匹配成功通知等）
- 在线用户数统计（首页/匹配页透明展示）
- 临时会话广播（match_session 内双方消息推送）

设计说明：
- 同一用户可能有多个连接（多端登录），用 set 保存所有 client_id
- 连接断开时清理对应的 client_id；当用户没有连接时从 online_users 移除
- 所有发送操作都捕获异常，避免单个连接断开影响其他连接
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """全局 WebSocket 连接管理器（单例）。"""

    # 游客 user_id 特殊值
    VISITOR_USER_ID = 0

    def __init__(self) -> None:
        # user_id -> {client_id -> websocket}
        self._connections: dict[int, dict[str, WebSocket]] = {}
        # user_id -> {client_id -> 连接时间戳}（在线列表展示"上线时间"用）
        self._connected_at: dict[int, dict[str, float]] = {}
        # user_id -> 当前所在 match_session_id（用于匹配系统定位）
        self._user_session: dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> str:
        """接受连接并注册到 online_users。返回 client_id 用于断开时清理。

        user_id=0 表示游客（未登录用户），游客以 client_id 区分。
        """
        await websocket.accept()
        client_id = uuid.uuid4().hex
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = {}
            self._connections[user_id][client_id] = websocket
            if user_id not in self._connected_at:
                self._connected_at[user_id] = {}
            self._connected_at[user_id][client_id] = time.time()
        logger.info("[WS] user={} connected client={}", user_id, client_id)
        return client_id

    async def disconnect(self, user_id: int, client_id: str) -> None:
        """断开连接并清理。"""
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns and client_id in conns:
                conns.pop(client_id, None)
                at = self._connected_at.get(user_id)
                if at:
                    at.pop(client_id, None)
                    if not at:
                        self._connected_at.pop(user_id, None)
                if not conns:
                    self._connections.pop(user_id, None)
                    self._connected_at.pop(user_id, None)
                    # 用户全部连接断开时，清理 session 状态
                    self._user_session.pop(user_id, None)
        logger.info("[WS] user={} disconnected client={}", user_id, client_id)

    def is_online(self, user_id: int) -> bool:
        """用户是否在线（至少有一个活动连接）。"""
        conns = self._connections.get(user_id)
        return bool(conns)

    def online_count(self) -> int:
        """当前在线总人数（登录用户去重 + 游客按连接数计数）。

        - 登录用户：按 user_id 去重（同一用户多端登录算1人）
        - 游客：按连接数计数（每个游客连接算1人）
        """
        total = 0
        for uid, conns in self._connections.items():
            if uid == self.VISITOR_USER_ID:
                # 游客：按连接数计数
                total += len(conns)
            else:
                # 登录用户：按 user_id 去重
                total += 1
        return total

    def logged_in_count(self) -> int:
        """当前在线登录用户数（去重）。"""
        return sum(1 for uid in self._connections if uid != self.VISITOR_USER_ID)

    def visitor_count(self) -> int:
        """当前在线游客数（按连接数）。"""
        conns = self._connections.get(self.VISITOR_USER_ID)
        return len(conns) if conns else 0

    def online_user_ids(self) -> list[int]:
        return [uid for uid in self._connections if uid != self.VISITOR_USER_ID]

    def online_users_detail(self) -> list[tuple[int, float]]:
        """(user_id, 最早连接时间戳) 列表：登录用户按 user_id 去重。"""
        result: list[tuple[int, float]] = []
        for uid, conns in self._connections.items():
            if uid == self.VISITOR_USER_ID or not conns:
                continue
            times = [self._connected_at.get(uid, {}).get(cid, 0.0) for cid in conns]
            result.append((uid, min(times)))
        return result

    def online_guests_detail(self) -> list[tuple[str, float]]:
        """(client_id, 连接时间戳) 列表：游客按连接计数。"""
        conns = self._connections.get(self.VISITOR_USER_ID) or {}
        return [
            (cid, self._connected_at.get(self.VISITOR_USER_ID, {}).get(cid, 0.0))
            for cid in conns
        ]

    def set_user_session(self, user_id: int, session_id: int | None) -> None:
        """记录用户当前所在的 match_session_id（None 表示清除）。"""
        if session_id is None:
            self._user_session.pop(user_id, None)
        else:
            self._user_session[user_id] = session_id

    def get_user_session(self, user_id: int) -> int | None:
        return self._user_session.get(user_id)

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> bool:
        """向指定用户的所有连接推送消息。返回是否至少送达一个连接。"""
        conns = self._connections.get(user_id)
        if not conns:
            return False
        sent = False
        dead: list[str] = []
        for client_id, ws in list(conns.items()):
            try:
                await ws.send_json(message)
                sent = True
            except Exception as exc:
                logger.warning("[WS] send_to_user failed user={} client={} err={}", user_id, client_id, exc)
                dead.append(client_id)
        if dead:
            async with self._lock:
                conns = self._connections.get(user_id, {})
                for cid in dead:
                    conns.pop(cid, None)
                if not conns:
                    self._connections.pop(user_id, None)
                    self._user_session.pop(user_id, None)
        return sent

    async def send_to_session(self, session_id: int, user_a: int, user_b: int, message: dict[str, Any]) -> None:
        """向 match_session 双方推送消息。"""
        await asyncio.gather(
            self.send_to_user(user_a, message),
            self.send_to_user(user_b, message),
            return_exceptions=True,
        )


# 全局单例
manager = ConnectionManager()
