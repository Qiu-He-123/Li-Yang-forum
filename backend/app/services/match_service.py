"""实时匹配业务逻辑层（类似假装情侣）。

实现规则：
- 入队：用户设置筛选条件（年级/校区/兴趣标签/性别筛选）后加入匹配队列
- 匹配：寻找同时满足双方条件、且当前也在队列中的其他用户配对
- 临时会话：匹配成功后创建 180 秒会话，双方进入临时聊天窗口
- 聊天：通过 WebSocket 实时推送文本消息；超时/主动结束则关闭会话
- 关注：聊天过程中可单向关注对方；求关注：发送让对方关注自己的请求
- 互关：若双方互相关注，则成为好友（沿用现有 Follow 系统），匹配结束后仍可联系
- 超时清理：等待队列超过 600 秒（10 分钟）未匹配则超时；会话超过 180 秒自动结束

数据库设计见 0018 迁移：match_queue / match_sessions / match_messages
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import calculate_age, now_utc, to_iso_zh
from app.models import Follow, MatchMessage, MatchQueue, MatchSession, School, User
from app.services.connection_manager import manager
from app.services import follow_service

# 会话时长 180 秒
SESSION_DURATION_SECONDS = 180
# 等待匹配超时 600 秒（10 分钟），给用户更充足的等待时间
WAIT_TIMEOUT_SECONDS = 600


def _fire_and_forget(message: dict, *user_ids: int) -> None:
    """在 HTTP 同步路由中安全地异步推送 WebSocket 消息。

    HTTP 同步路由运行在线程池中，不在事件循环内；
    使用 run_coroutine_threadsafe 把协程提交到主事件循环。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            for uid in user_ids:
                asyncio.run_coroutine_threadsafe(manager.send_to_user(uid, message), loop)
        else:
            # 没有运行中的事件循环，直接创建任务（理论上不会走到这里）
            for uid in user_ids:
                asyncio.create_task(manager.send_to_user(uid, message))
    except RuntimeError:
        # No event loop in current thread - 无法推送，跳过
        pass


def _parse_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _user_brief(u: User) -> dict:
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar_url": u.avatar_url,
        "school_id": u.school_id,
        "grade": u.grade,
        "age": calculate_age(u.birthday),
        "gender": u.gender or "unknown",
    }


def _session_dict(s: MatchSession, peer: User | None = None) -> dict:
    return {
        "id": s.id,
        "user_a": s.user_a,
        "user_b": s.user_b,
        "status": s.status,
        "expires_at": to_iso_zh(s.expires_at),
        "ended_at": to_iso_zh(s.ended_at) if s.ended_at else None,
        "mutual_follow": s.mutual_follow,
        "created_at": to_iso_zh(s.created_at),
        "peer": _user_brief(peer) if peer else None,
    }


def enqueue_match(
    db: Session,
    user: User,
    grades: list[str],
    school_ids: list[int],
    tags: list[str],
    target_gender: str,
    tag_required: list[str] | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
) -> dict:
    """加入匹配队列。

    - 校验用户性别已设置（未设置则按 unknown，target_gender 必填）
    - 若用户已在队列中且 status=waiting，更新条件而非重复插入
    - 入队后立即尝试匹配

    三态标签：
    - tags（尽量有，软排序）：候选中按重叠度排序优先
    - tag_required（必须有，硬过滤）：对方必须也选了这个标签（任意状态）

    年龄系统：
    - age_min / age_max 为期望对方的年龄范围（None 表示不限）
    - 对方年龄从 birthday 动态计算
    """
    if target_gender not in ("male", "female", "any"):
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)

    # 用户的 gender 必须为 male/female，否则引导去完善资料
    if user.gender not in ("male", "female"):
        raise HTTPException(status_code=400, detail="请先在设置中完善性别信息后再匹配")

    tag_required = tag_required or []

    # 检查是否已在等待队列
    existing = db.scalar(
        select(MatchQueue).where(
            MatchQueue.user_id == user.id,
            MatchQueue.status == "waiting",
        )
    )
    if existing:
        # 更新条件
        existing.target_gender = target_gender
        existing.grades = json.dumps(grades or [], ensure_ascii=False)
        existing.age_min = age_min
        existing.age_max = age_max
        existing.school_ids = json.dumps(school_ids or [], ensure_ascii=False)
        existing.tags = json.dumps(tags or [], ensure_ascii=False)
        existing.tag_required = json.dumps(tag_required or [], ensure_ascii=False)
        # 重置 created_at 为当前 UTC 时间，与 cleanup loop 的 now_utc() 保持一致
        existing.created_at = now_utc()
        existing.updated_at = now_utc()
        db.commit()
        db.refresh(existing)
        queue_item = existing
    else:
        # 注意：created_at 用 now_utc() 设置（naive UTC），与 cleanup loop 保持一致。
        # 不依赖 server_default=func.now()，因为 SQLite 的 func.now() 返回 UTC，
        # 而 Python datetime.now() 返回本地时间，混用会导致刚入队就被误判超时。
        queue_item = MatchQueue(
            user_id=user.id,
            gender=user.gender,
            target_gender=target_gender,
            grades=json.dumps(grades or [], ensure_ascii=False),
            age_min=age_min,
            age_max=age_max,
            school_ids=json.dumps(school_ids or [], ensure_ascii=False),
            tags=json.dumps(tags or [], ensure_ascii=False),
            tag_required=json.dumps(tag_required or [], ensure_ascii=False),
            status="waiting",
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

    # 同步触发匹配尝试
    matched_session = _try_match(db, queue_item)
    if matched_session:
        return {
            "status": "matched",
            "session": _session_dict(
                matched_session,
                peer=db.get(User, matched_session.user_b if matched_session.user_a == user.id else matched_session.user_a),
            ),
        }
    return {"status": "waiting", "queue_id": queue_item.id}


def _all_tags(q: MatchQueue) -> set[str]:
    """用户选过的所有标签（"尽量有" + "必须有"），代表该用户声明的兴趣。"""
    tags = set(_parse_json(q.tags, []))
    tags.update(_parse_json(q.tag_required, []))
    return tags


def _has_matched_before(db: Session, user_a: int, user_b: int) -> bool:
    """检查两个用户是否曾经匹配过（任意状态的会话）。

    用于实现"两人匹配过一次，同一个号不能匹配第二次"。
    """
    existed = db.scalar(
        select(func.count())
        .select_from(MatchSession)
        .where(
            ((MatchSession.user_a == user_a) & (MatchSession.user_b == user_b))
            | ((MatchSession.user_a == user_b) & (MatchSession.user_b == user_a)),
        )
    )
    return bool(existed and existed > 0)


def _conditions_match(
    me: MatchQueue,
    other: MatchQueue,
    other_user: User,
    me_user: User,
) -> bool:
    """检查 other 是否满足 me 的匹配条件（双向）。

    双向匹配：me 满足 other 的条件 AND other 满足 me 的条件。

    三态标签（同漂流瓶拾取）：
    - 必须有（tag_required）：硬过滤，对方必须也选了这个标签（任意状态）
    - 尽量有（tags）：软排序，在 _try_match 中按重叠度排序
    - 无所谓：不影响匹配
    """
    # 性别双向匹配
    if me.target_gender != "any":
        if other_user.gender != me.target_gender:
            return False
    if other.target_gender != "any":
        if me_user.gender != other.target_gender:
            return False

    # 年龄筛选（双向）：me.age_min/age_max 为 None 表示不限
    # 对方年龄从 birthday 动态计算
    me_age_min = me.age_min
    me_age_max = me.age_max
    other_age_min = other.age_min
    other_age_max = other.age_max
    me_user_age = calculate_age(me_user.birthday)
    other_user_age = calculate_age(other_user.birthday)
    # me 要求的年龄范围 → other_user 的年龄必须落在范围内
    if me_age_min is not None and (other_user_age is None or other_user_age < me_age_min):
        return False
    if me_age_max is not None and (other_user_age is None or other_user_age > me_age_max):
        return False
    # other 要求的年龄范围 → me_user 的年龄必须落在范围内
    if other_age_min is not None and (me_user_age is None or me_user_age < other_age_min):
        return False
    if other_age_max is not None and (me_user_age is None or me_user_age > other_age_max):
        return False

    # 年级筛选（旧字段，向后兼容）：me.grades 为空表示不限；非空则 other_user.grade 必须在其中
    me_grades = set(_parse_json(me.grades, []))
    other_grades = set(_parse_json(other.grades, []))
    if me_grades and other_user.grade not in me_grades:
        return False
    if other_grades and me_user.grade not in other_grades:
        return False

    # 校区筛选（双向）
    me_schools = set(_parse_json(me.school_ids, []))
    other_schools = set(_parse_json(other.school_ids, []))
    if me_schools and other_user.school_id not in me_schools:
        return False
    if other_schools and me_user.school_id not in other_schools:
        return False

    # 标签"必须有"双向硬过滤：
    # me 要求"必须有"的标签，other 必须也选过（任意状态）
    # other 要求"必须有"的标签，me 必须也选过（任意状态）
    me_all_tags = _all_tags(me)
    other_all_tags = _all_tags(other)
    me_required = set(_parse_json(me.tag_required, []))
    other_required = set(_parse_json(other.tag_required, []))
    if me_required and not me_required.issubset(other_all_tags):
        return False
    if other_required and not other_required.issubset(me_all_tags):
        return False

    return True


def _tag_overlap_score(me: MatchQueue, other: MatchQueue) -> int:
    """计算"尽量有"标签的重叠得分，用于候选排序。

    得分 = me.tags 与 other 全部标签的交集大小 + other.tags 与 me 全部标签的交集大小。
    """
    me_preferred = set(_parse_json(me.tags, []))
    other_preferred = set(_parse_json(other.tags, []))
    me_all = _all_tags(me)
    other_all = _all_tags(other)
    score = 0
    if me_preferred:
        score += len(me_preferred & other_all)
    if other_preferred:
        score += len(other_preferred & me_all)
    return score


def _try_match(db: Session, queue_item: MatchQueue) -> MatchSession | None:
    """尝试为 queue_item 找到一个匹配的对方。

    匹配池：所有 status=waiting 的其他用户
    匹配条件：
      1. 双向满足对方条件（含三态标签硬过滤）
      2. 两人未曾匹配过（同一对用户不能匹配第二次）
    匹配成功：创建 MatchSession，双方 queue 状态改为 matched
    候选排序：按"尽量有"标签重叠度降序，优先匹配兴趣更相近的用户
    """
    me_user = db.get(User, queue_item.user_id)
    if not me_user:
        return None

    candidates = db.scalars(
        select(MatchQueue).where(
            MatchQueue.status == "waiting",
            MatchQueue.user_id != queue_item.user_id,
        )
    ).all()

    # 收集所有通过基础条件筛选的候选，并按标签重叠度排序
    scored_candidates: list[tuple[int, MatchQueue, User]] = []
    for other in candidates:
        other_user = db.get(User, other.user_id)
        if not other_user:
            continue
        if not _conditions_match(queue_item, other, other_user, me_user):
            continue
        # 同一用户不能重复匹配
        if _has_matched_before(db, queue_item.user_id, other.user_id):
            continue
        score = _tag_overlap_score(queue_item, other)
        scored_candidates.append((score, other, other_user))

    # 按得分降序（兴趣更相近的优先）
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    for _score, other, other_user in scored_candidates:
        # 匹配成功，创建会话
        # 使用 now_utc() 保持与 to_iso_zh 的时区假设一致（naive UTC），
        # 否则 datetime.now() 返回北京本地时间，to_iso_zh 再加 +08:00 会多出 8 小时
        now = now_utc()
        expires_at = now + timedelta(seconds=SESSION_DURATION_SECONDS)
        session = MatchSession(
            user_a=queue_item.user_id,
            user_b=other.user_id,
            status="active",
            expires_at=expires_at,
        )
        db.add(session)
        queue_item.status = "matched"
        queue_item.matched_with = other.user_id
        other.status = "matched"
        other.matched_with = queue_item.user_id
        db.commit()
        db.refresh(session)

        # 注册到 ConnectionManager 的 session 映射
        manager.set_user_session(queue_item.user_id, session.id)
        manager.set_user_session(other.user_id, session.id)

        # 通过 WebSocket 推送匹配成功通知给双方
        peer_for_a = _user_brief(other_user)
        peer_for_b = _user_brief(me_user)
        # 推给 user_a（发起方）
        _fire_and_forget({
            "type": "match_found",
            "session_id": session.id,
            "peer": peer_for_a,
            "expires_at": to_iso_zh(expires_at),
        }, queue_item.user_id)
        # 推给 user_b（被动匹配方）
        _fire_and_forget({
            "type": "match_found",
            "session_id": session.id,
            "peer": peer_for_b,
            "expires_at": to_iso_zh(expires_at),
        }, other.user_id)

        return session
    return None


def cancel_match(db: Session, user: User) -> dict:
    """取消等待中的匹配。"""
    item = db.scalar(
        select(MatchQueue).where(
            MatchQueue.user_id == user.id,
            MatchQueue.status == "waiting",
        )
    )
    if item:
        item.status = "cancelled"
        db.commit()
    return {"ok": True}


def get_active_session(db: Session, user: User) -> dict | None:
    """查询当前用户的活动会话（如有）。"""
    session = db.scalar(
        select(MatchSession).where(
            MatchSession.status == "active",
            (MatchSession.user_a == user.id) | (MatchSession.user_b == user.id),
        ).order_by(MatchSession.created_at.desc())
    )
    if not session:
        return None
    # 检查是否已超时（expires_at 以 UTC 存储，用 now_utc() 比较）
    if session.expires_at < now_utc():
        _expire_session(db, session)
        return None
    peer_id = session.user_b if session.user_a == user.id else session.user_a
    peer = db.get(User, peer_id)
    return _session_dict(session, peer=peer)


def list_session_messages(db: Session, session_id: int, user: User) -> list[dict]:
    """查询会话历史消息。"""
    session = db.get(MatchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    if session.user_a != user.id and session.user_b != user.id:
        raise HTTPException(status_code=403, detail=ErrorCode.NO_PERMISSION)
    rows = db.scalars(
        select(MatchMessage)
        .where(MatchMessage.session_id == session_id)
        .order_by(MatchMessage.created_at.asc())
    ).all()
    return [_message_dict(m) for m in rows]


def _message_dict(m: MatchMessage) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "sender_id": m.sender_id,
        "content": m.content,
        "created_at": to_iso_zh(m.created_at),
    }


async def handle_match_chat(user_id: int, session_id: int, content: str) -> None:
    """WebSocket 处理临时会话消息发送。"""
    with SessionLocal_ctx() as db:
        session = db.get(MatchSession, session_id)
        if not session or session.status != "active":
            return
        if session.user_a != user_id and session.user_b != user_id:
            return
        # 检查是否超时（expires_at 以 UTC 存储）
        if session.expires_at < now_utc():
            _expire_session(db, session)
            return
        # 存储消息
        msg = MatchMessage(
            session_id=session_id,
            sender_id=user_id,
            content=content,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        # 推送给对方（不回传给发送者：发送者已在本地乐观更新显示）
        # 之前同时推给双方导致发送者消息重复显示（本地时间戳与服务端时间戳不一致，去重失败）
        peer_id = session.user_b if session.user_a == user_id else session.user_a
        msg_payload = {
            "type": "match_chat",
            "session_id": session_id,
            "sender_id": user_id,
            "content": content,
            "created_at": to_iso_zh(msg.created_at),
            "message_id": msg.id,  # 带上服务端消息 ID，便于前端去重
        }
        await manager.send_to_user(peer_id, msg_payload)


async def handle_match_follow(user_id: int, session_id: int) -> None:
    """WebSocket 处理临时会话关注对方（同意互关）。

    统一逻辑：双方必须在 180 秒会话内点同意互关。会话结束后不再允许同意，
    避免逻辑混乱。结束后根据双方同意状态显示结果。
    """
    with SessionLocal_ctx() as db:
        session = db.get(MatchSession, session_id)
        if not session:
            return
        if session.user_a != user_id and session.user_b != user_id:
            return
        # 仅在会话进行中（active）允许同意互关
        if session.status != "active":
            return
        peer_id = session.user_b if session.user_a == user_id else session.user_a
        # 关注对方
        follower = db.get(User, user_id)
        if not follower:
            return
        try:
            follow_service.follow_user(db, follower, peer_id)
        except HTTPException:
            # 已关注过，幂等
            pass
        # 检查是否互关
        is_mutual = follow_service.is_mutual_follow(db, user_id, peer_id)
        if is_mutual:
            session.mutual_follow = True
            db.commit()
        # 推送事件给双方
        event = {
            "type": "match_follow_event",
            "session_id": session_id,
            "follower_id": user_id,
            "is_mutual": is_mutual,
        }
        await manager.send_to_user(user_id, event)
        await manager.send_to_user(peer_id, event)


async def handle_match_request_follow(user_id: int, session_id: int) -> None:
    """WebSocket 处理临时会话求关注（请求对方关注自己）。

    统一逻辑：仅会话进行中（active）允许发送求关注请求。
    """
    with SessionLocal_ctx() as db:
        session = db.get(MatchSession, session_id)
        if not session:
            return
        if session.user_a != user_id and session.user_b != user_id:
            return
        # 仅在会话进行中（active）允许
        if session.status != "active":
            return
        peer_id = session.user_b if session.user_a == user_id else session.user_a
        # 推送求关注请求给对方
        await manager.send_to_user(peer_id, {
            "type": "match_request_follow",
            "session_id": session_id,
            "from_id": user_id,
        })


async def handle_match_end(user_id: int, session_id: int) -> None:
    """WebSocket 处理主动结束会话。"""
    with SessionLocal_ctx() as db:
        session = db.get(MatchSession, session_id)
        if not session or session.status != "active":
            return
        if session.user_a != user_id and session.user_b != user_id:
            return
        _end_session(db, session, reason="manual")


def _expire_session(db: Session, session: MatchSession) -> None:
    """会话超时：状态改为 expired，清理 ConnectionManager 中的 session 映射。"""
    session.status = "expired"
    session.ended_at = now_utc()
    db.commit()
    manager.set_user_session(session.user_a, None)
    manager.set_user_session(session.user_b, None)
    # 推送给双方
    _fire_and_forget({
        "type": "match_end",
        "session_id": session.id,
        "reason": "timeout",
    }, session.user_a, session.user_b)


def _end_session(db: Session, session: MatchSession, reason: str = "manual") -> None:
    """主动结束会话。"""
    session.status = "ended"
    session.ended_at = now_utc()
    db.commit()
    manager.set_user_session(session.user_a, None)
    manager.set_user_session(session.user_b, None)
    _fire_and_forget({
        "type": "match_end",
        "session_id": session.id,
        "reason": reason,
    }, session.user_a, session.user_b)


def cleanup_user_waiting(db: Session, user_id: int) -> None:
    """用户断开 WebSocket 时，清理正在等待的匹配队列。

    仅当用户完全不在线（没有任何 WS 连接）时才执行，
    容忍 WS 短暂断开重连（如网络抖动、页面切换）。
    """
    # 如果用户还有其他连接在线（如重连的新连接），不取消匹配
    if manager.is_online(user_id):
        return
    item = db.scalar(
        select(MatchQueue).where(
            MatchQueue.user_id == user_id,
            MatchQueue.status == "waiting",
        )
    )
    if item:
        item.status = "cancelled"
        db.commit()


def cleanup_user_session(db: Session, user_id: int) -> None:
    """用户断开 WebSocket 且不再有其他连接时，结束其活动匹配会话并通知对方。

    - 仅当用户完全不在线（没有任何 WS 连接）时才执行
    - 结束 status=active 的会话，推送 match_end reason=peer_left 给对方
    """
    # 如果用户还有其他连接在线，不处理
    if manager.is_online(user_id):
        return
    session = db.scalar(
        select(MatchSession).where(
            MatchSession.status == "active",
            (MatchSession.user_a == user_id) | (MatchSession.user_b == user_id),
        )
    )
    if not session:
        return
    peer_id = session.user_b if session.user_a == user_id else session.user_a
    session.status = "ended"
    session.ended_at = now_utc()
    db.commit()
    manager.set_user_session(session.user_a, None)
    manager.set_user_session(session.user_b, None)
    # 通知对方：对方已退出
    _fire_and_forget({
        "type": "match_end",
        "session_id": session.id,
        "reason": "peer_left",
    }, peer_id)


def list_my_match_history(db: Session, user: User, page: int = 1, page_size: int = 20) -> dict:
    """查询历史匹配会话列表（已结束的）。"""
    total = db.scalar(
        select(func.count())
        .select_from(MatchSession)
        .where(
            (MatchSession.user_a == user.id) | (MatchSession.user_b == user.id),
            MatchSession.status.in_(["ended", "expired"]),
        )
    ) or 0
    rows = db.scalars(
        select(MatchSession)
        .where(
            (MatchSession.user_a == user.id) | (MatchSession.user_b == user.id),
            MatchSession.status.in_(["ended", "expired"]),
        )
        .order_by(MatchSession.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for s in rows:
        peer_id = s.user_b if s.user_a == user.id else s.user_a
        peer = db.get(User, peer_id)
        items.append(_session_dict(s, peer=peer))
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


# ============ SessionLocal 上下文管理器 ============
# 为 WebSocket 异步处理提供数据库会话（FastAPI 的 Depends 不适用）
from app.core.database import SessionLocal


class SessionLocal_ctx:
    def __enter__(self):
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.db.close()
        except Exception:
            pass
        return False
