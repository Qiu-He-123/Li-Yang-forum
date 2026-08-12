"""好友与私信业务逻辑层（抖音/快手风格重构）。

支持：
- 好友请求管理（保留，但消息不再依赖好友关系）
- 私信发送（基于互关关系 + 权限设置）
  - 互关用户：自由发送
  - 非互关用户：受接收方 message_permission 控制
    - everyone       所有人可发
    - mutual_only    仅互关可发
    - stranger_once  陌生人每天可发 1 条（默认）
    - no_stranger    不接受陌生人消息
- 会话列表（仅包含有消息记录的会话）
- 消息历史
- 私信权限管理
"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ErrorCode
from app.core.time_utils import beijing_today_start, now_utc, to_iso_zh
from app.models import Follow, FriendRequest, Message, User
from app.services.follow_service import _default_friend_ids, is_mutual_follow
from app.services.avatar import avatar_url_or_default


def _default_friend_users(db: Session, user: User) -> list[User]:
    """管理端配置的默认好友列表（有序，本人除外）；未配置或用户不存在返回空列表。"""
    ids = _default_friend_ids(db)
    if not ids:
        return []
    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_(ids))
        ).all()
    }
    return [
        users[uid] for uid in ids
        if uid != user.id and uid in users and users[uid].is_active
    ]


# 私信权限枚举
VALID_PERMISSIONS = {"everyone", "mutual_only", "stranger_once", "no_stranger"}


def _user_dict(u: User) -> dict:
    from app.services.badge_service import badge_dict as _badge_dict
    return {
        "id": u.id,
        "nickname": u.nickname,
        "avatar_url": avatar_url_or_default(u.avatar_url),
        "badge": _badge_dict(getattr(u, "wearing_badge", None)),
        "bio": u.bio,
        "school": u.school.name if u.school else None,
        "grade": u.grade,
    }


def _conv_id(uid1: int, uid2: int) -> str:
    """生成稳定的会话 ID（两人 id 排序后拼接）。"""
    a, b = sorted([uid1, uid2])
    return f"conv_{a}_{b}"


# ============ 私信权限管理 ============

def get_message_permission(user: User) -> dict:
    """获取当前用户的私信权限设置。"""
    return {"message_permission": user.message_permission or "stranger_once"}


def update_message_permission(db: Session, user: User, permission: str) -> dict:
    """更新当前用户的私信权限设置。"""
    if permission not in VALID_PERMISSIONS:
        raise HTTPException(status_code=400, detail="无效的权限值")
    user.message_permission = permission
    db.commit()
    db.refresh(user)
    return {"message_permission": user.message_permission}


def check_can_send(db: Session, sender: User, receiver_id: int) -> dict:
    """预检：当前用户能否给 receiver_id 发消息。

    返回：
    - can_send: bool
    - reason: str（不能发的原因）
    - is_mutual: bool（是否互关）
    - remaining_today: int（今日剩余可发条数，互关/双向对话后为 -1 表示无限制）
    """
    if sender.id == receiver_id:
        return {"can_send": False, "reason": "不能给自己发消息", "is_mutual": False, "remaining_today": 0}

    receiver = db.get(User, receiver_id)
    if not receiver or not receiver.is_active:
        return {"can_send": False, "reason": "用户不存在", "is_mutual": False, "remaining_today": 0}

    mutual = is_mutual_follow(db, sender.id, receiver_id)

    # 互关：自由发送
    if mutual:
        return {"can_send": True, "reason": "", "is_mutual": True, "remaining_today": -1}

    # 今日双向对话放行：今日双方都已发过消息，破冰后当天可继续自由沟通
    if _has_bidirectional_conversation_today(db, sender.id, receiver_id):
        return {"can_send": True, "reason": "", "is_mutual": False, "remaining_today": -1}

    # 非互关：检查接收方权限设置
    perm = receiver.message_permission or "stranger_once"

    if perm == "everyone":
        return {"can_send": True, "reason": "", "is_mutual": False, "remaining_today": -1}

    if perm in ("mutual_only", "no_stranger"):
        reason = "对方仅接受互关用户的消息" if perm == "mutual_only" else "对方不接受陌生人消息"
        return {"can_send": False, "reason": reason, "is_mutual": False, "remaining_today": 0}

    # stranger_once：每天 1 条
    remaining = _remaining_stranger_messages(db, sender.id, receiver_id)
    if remaining <= 0:
        return {"can_send": False, "reason": "今日已向对方发送过消息，明天再试", "is_mutual": False, "remaining_today": 0}
    return {"can_send": True, "reason": "", "is_mutual": False, "remaining_today": remaining}


def _remaining_stranger_messages(db: Session, sender_id: int, receiver_id: int) -> int:
    """陌生人每日剩余可发条数（stranger_once 模式下固定 1 条/天）。"""
    today_start = beijing_today_start()
    sent_today = db.scalar(
        select(func.count(Message.id)).where(
            Message.sender_id == sender_id,
            Message.receiver_id == receiver_id,
            Message.created_at >= today_start,
        )
    ) or 0
    return max(0, 1 - sent_today)


def _has_bidirectional_conversation_today(db: Session, user_a_id: int, user_b_id: int) -> bool:
    """今日双方是否已经形成双向对话（即今日 A 发给过 B 且 B 也发给过 A）。

    一旦形成双向对话，今天剩余时间内双方都可以自由发送消息，不再受
    stranger_once 的每日 1 条限制。这样匹配实际社交直觉：陌生人破冰后
    应当允许继续沟通，而不是被强制等到第二天。
    """
    today_start = beijing_today_start()
    # A -> B 今日已发
    a_to_b = db.scalar(
        select(func.count(Message.id)).where(
            Message.sender_id == user_a_id,
            Message.receiver_id == user_b_id,
            Message.created_at >= today_start,
        )
    ) or 0
    if a_to_b == 0:
        return False
    # B -> A 今日已发
    b_to_a = db.scalar(
        select(func.count(Message.id)).where(
            Message.sender_id == user_b_id,
            Message.receiver_id == user_a_id,
            Message.created_at >= today_start,
        )
    ) or 0
    return b_to_a > 0


# ============ 好友请求（保留，个人主页也可申请） ============

def send_friend_request(db: Session, from_user: User, to_id: int, message: str | None = None) -> dict:
    """发送好友请求（幂等，已存在则返回已有状态）。"""
    if from_user.id == to_id:
        raise HTTPException(status_code=400, detail="不能添加自己为好友")

    to_user = db.get(User, to_id)
    if not to_user or not to_user.is_active:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)

    # 检查是否已经是好友（双向都有请求记录且 accepted）
    existing_accepted = db.scalar(
        select(FriendRequest).where(
            or_(
                (FriendRequest.from_id == from_user.id) & (FriendRequest.to_id == to_id),
                (FriendRequest.from_id == to_id) & (FriendRequest.to_id == from_user.id),
            ),
            FriendRequest.status == "accepted",
        )
    )
    if existing_accepted:
        return {"status": "already_friend", "user": _user_dict(to_user)}

    # 检查是否已有 pending 请求
    existing = db.scalar(
        select(FriendRequest).where(
            FriendRequest.from_id == from_user.id,
            FriendRequest.to_id == to_id,
            FriendRequest.status == "pending",
        )
    )
    if existing:
        return {"status": "pending", "request_id": existing.id}

    # 如果对方已向我发送请求，自动接受
    reverse = db.scalar(
        select(FriendRequest).where(
            FriendRequest.from_id == to_id,
            FriendRequest.to_id == from_user.id,
            FriendRequest.status == "pending",
        )
    )
    if reverse:
        reverse.status = "accepted"
        db.commit()
        # 给自己的请求也创建 accepted 记录
        db.add(FriendRequest(from_id=from_user.id, to_id=to_id, status="accepted", message=message))
        db.commit()
        return {"status": "accepted", "user": _user_dict(to_user)}

    req = FriendRequest(from_id=from_user.id, to_id=to_id, message=message)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"status": "pending", "request_id": req.id}


def accept_friend_request(db: Session, user: User, request_id: int) -> dict:
    """接受好友请求。"""
    req = db.get(FriendRequest, request_id)
    if not req or req.to_id != user.id:
        raise HTTPException(status_code=404, detail="请求不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="请求已处理")
    req.status = "accepted"
    # 创建反向记录
    db.add(FriendRequest(from_id=user.id, to_id=req.from_id, status="accepted"))
    db.commit()
    from_user = db.get(User, req.from_id)
    return {"status": "accepted", "user": _user_dict(from_user) if from_user else None}


def reject_friend_request(db: Session, user: User, request_id: int) -> dict:
    """拒绝好友请求。"""
    req = db.get(FriendRequest, request_id)
    if not req or req.to_id != user.id:
        raise HTTPException(status_code=404, detail="请求不存在")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="请求已处理")
    req.status = "rejected"
    db.commit()
    return {"status": "rejected"}


def list_friends(db: Session, user: User) -> list[dict]:
    """获取好友列表（按最新消息时间排序）。

    好友来源：
    1. FriendRequest 中 status=accepted 的记录（传统好友请求）
    2. Follow 表中互相关注的用户（通过随机匹配"同意互关"成为好友的用户）
    """
    friend_ids = set()

    # 1. 传统好友请求
    accepted = db.scalars(
        select(FriendRequest).where(
            or_(
                (FriendRequest.from_id == user.id),
                (FriendRequest.to_id == user.id),
            ),
            FriendRequest.status == "accepted",
        )
    ).all()
    for r in accepted:
        friend_ids.add(r.from_id if r.from_id != user.id else r.to_id)

    # 2. 互相关注的用户（随机匹配"同意互关"产生的好友关系）
    # 查找我关注的人
    following_ids = set(
        db.scalars(
            select(Follow.followee_id).where(Follow.follower_id == user.id)
        ).all()
    )
    # 查找关注我的人
    follower_ids = set(
        db.scalars(
            select(Follow.follower_id).where(Follow.followee_id == user.id)
        ).all()
    )
    # 交集 = 互相关注
    mutual_ids = following_ids & follower_ids
    friend_ids.update(mutual_ids)

    # 默认好友们视作好友（即使没有真实好友关系），以便读取真实最后一条消息/未读数
    friend_ids.update(u.id for u in _default_friend_users(db, user))

    users = {
        u.id: u
        for u in db.scalars(
            select(User).options(selectinload(User.school)).where(User.id.in_(friend_ids))
        ).all()
    }

    result = []
    for fid in friend_ids:
        u = users.get(fid)
        if not u:
            continue
        conv = _conv_id(user.id, fid)
        last_msg = db.scalar(
            select(Message)
            .where(Message.conversation_id == conv)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        unread = (
            db.scalar(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conv,
                    Message.receiver_id == user.id,
                    Message.is_read.is_(False),
                )
            )
            or 0
        )
        result.append({
            "user": _user_dict(u),
            "last_message": last_msg.content[:50] if last_msg else None,
            "last_msg_type": last_msg.msg_type if last_msg else None,
            "last_time": to_iso_zh(last_msg.created_at) if last_msg else None,
            "unread_count": unread,
        })

    result.sort(key=lambda x: x["last_time"] or "", reverse=True)
    # 默认好友置顶：有真实记录则保留最后一条消息/未读数，仅在没有记录时插入占位项
    default_friends = _default_friend_users(db, user)
    if default_friends:
        pinned_entries = []
        default_ids = {df.id for df in default_friends}
        for df in default_friends:
            entry = next((r for r in result if r["user"]["id"] == df.id), None)
            if entry is None:
                entry = {
                    "user": _user_dict(df),
                    "last_message": "默认好友（官方账号）",
                    "last_time": None,
                    "unread_count": 0,
                }
            elif not entry["last_message"]:
                # 有真实好友关系但没有消息时，避免前端显示「开始聊天吧」
                entry["last_message"] = "默认好友（官方账号）"
            pinned_entries.append(entry)
        result = pinned_entries + [
            r for r in result if r["user"]["id"] not in default_ids
        ]
    return result


def list_friend_requests(db: Session, user: User, direction: str = "incoming") -> list[dict]:
    """获取好友请求列表。"""
    if direction == "incoming":
        rows = db.scalars(
            select(FriendRequest)
            .where(FriendRequest.to_id == user.id, FriendRequest.status == "pending")
            .order_by(FriendRequest.created_at.desc())
        ).all()
        result = []
        for r in rows:
            from_user = db.get(User, r.from_id)
            if from_user:
                result.append({
                    "id": r.id,
                    "user": _user_dict(from_user),
                    "message": r.message,
                    "created_at": to_iso_zh(r.created_at),
                })
        return result
    else:
        rows = db.scalars(
            select(FriendRequest)
            .where(FriendRequest.from_id == user.id, FriendRequest.status == "pending")
            .order_by(FriendRequest.created_at.desc())
        ).all()
        result = []
        for r in rows:
            to_user = db.get(User, r.to_id)
            if to_user:
                result.append({
                    "id": r.id,
                    "user": _user_dict(to_user),
                    "message": r.message,
                    "created_at": to_iso_zh(r.created_at),
                })
        return result


# ============ 私信 ============

def send_message(db: Session, sender: User, receiver_id: int, content: str, msg_type: str = "text") -> dict:
    """发送私信（抖音/快手风格：互关自由发，陌生人受权限控制）。

    新规则：今日双方已形成双向对话后，当天剩余时间双方均可自由发送，
    不再受 stranger_once 的每日 1 条限制。
    """
    if sender.id == receiver_id:
        raise HTTPException(status_code=400, detail="不能给自己发消息")

    receiver = db.get(User, receiver_id)
    if not receiver or not receiver.is_active:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)

    conv = _conv_id(sender.id, receiver_id)
    mutual = is_mutual_follow(db, sender.id, receiver_id)

    # 权限检查
    if not mutual:
        # 今日双向对话放行：双方今天都已发过消息，允许继续自由沟通
        if _has_bidirectional_conversation_today(db, sender.id, receiver_id):
            pass  # 放行
        else:
            perm = receiver.message_permission or "stranger_once"
            if perm in ("mutual_only", "no_stranger"):
                reason = "对方仅接受互关用户的消息" if perm == "mutual_only" else "对方不接受陌生人消息"
                raise HTTPException(status_code=403, detail=reason)
            # stranger_once：检查今日已发条数
            if perm == "stranger_once":
                remaining = _remaining_stranger_messages(db, sender.id, receiver_id)
                if remaining <= 0:
                    raise HTTPException(status_code=403, detail="今日已向对方发送过消息，明天再试")
            # everyone：直接放行

    msg = Message(
        sender_id=sender.id,
        receiver_id=receiver_id,
        content=content,
        msg_type=msg_type,
        conversation_id=conv,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "receiver_id": msg.receiver_id,
        "content": msg.content,
        "msg_type": msg.msg_type,
        "is_read": msg.is_read,
        "read_at": None,
        "is_mutual": mutual,
        "is_default_friend": receiver_id in _default_friend_ids(db),
        "created_at": to_iso_zh(msg.created_at),
    }


def get_messages(db: Session, user: User, friend_id: int, page: int = 1, page_size: int = 30) -> dict:
    """获取与某用户的聊天记录（分页），同时返回关系状态。"""
    conv = _conv_id(user.id, friend_id)
    total = (
        db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == conv)
        )
        or 0
    )
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conv)
        .order_by(Message.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # 标记对方发给我的消息为已读
    unread = [
        m for m in rows
        if m.receiver_id == user.id and not m.is_read
    ]
    if unread:
        now = now_utc()
        for m in unread:
            m.is_read = True
            m.read_at = now
        db.commit()

    items = [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "content": m.content,
            "msg_type": m.msg_type,
            "is_read": m.is_read,
            "read_at": to_iso_zh(m.read_at) if m.read_at else None,
            "created_at": to_iso_zh(m.created_at),
        }
        for m in reversed(rows)
    ]

    # 返回关系状态，供前端决定输入框行为
    mutual = is_mutual_follow(db, user.id, friend_id)
    other = db.get(User, friend_id)
    other_perm = other.message_permission if other else "stranger_once"
    can_send_info = check_can_send(db, user, friend_id)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "is_mutual": mutual,
        "is_default_friend": friend_id in _default_friend_ids(db),
        "other_message_permission": other_perm,
        "can_send": can_send_info["can_send"],
        "can_send_reason": can_send_info["reason"],
        "remaining_today": can_send_info["remaining_today"],
    }


def list_conversations(db: Session, user: User) -> list[dict]:
    """获取会话列表（仅包含有消息记录的会话，按最新消息排序）。

    重构：不再依赖 list_friends，直接从 messages 表聚合。
    """
    # 找出当前用户参与的所有会话 ID
    conv_rows = db.execute(
        select(
            Message.conversation_id,
            func.max(Message.created_at).label("last_time"),
        )
        .where(
            or_(
                Message.sender_id == user.id,
                Message.receiver_id == user.id,
            ),
            Message.conversation_id.is_not(None),
        )
        .group_by(Message.conversation_id)
        .order_by(func.max(Message.created_at).desc())
    ).all()

    # 从 conversation_id 解析对方用户 ID
    result = []
    for conv_id_str, last_time in conv_rows:
        # conv_id 格式: conv_{min}_{max}
        parts = conv_id_str.split("_")
        if len(parts) != 3:
            continue
        uid_a, uid_b = int(parts[1]), int(parts[2])
        other_id = uid_b if uid_a == user.id else uid_a

        other = db.get(User, other_id)
        if not other:
            continue

        # 最后一条消息
        last_msg = db.scalar(
            select(Message)
            .where(Message.conversation_id == conv_id_str)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        # 未读数
        unread = (
            db.scalar(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conv_id_str,
                    Message.receiver_id == user.id,
                    Message.is_read.is_(False),
                )
            )
            or 0
        )
        # 互关状态
        mutual = is_mutual_follow(db, user.id, other_id)

        result.append({
            "user": _user_dict(other),
            "last_message": last_msg.content[:50] if last_msg else None,
            "last_msg_type": last_msg.msg_type if last_msg else None,
            "last_time": to_iso_zh(last_time),
            "unread_count": unread,
            "is_mutual": mutual,
        })

    # 默认好友置顶：有真实会话则保留最后一条消息/未读数（红点正常），仅在没有会话时插入占位项
    default_friends = _default_friend_users(db, user)
    if default_friends:
        pinned_entries = []
        default_ids = {df.id for df in default_friends}
        for df in default_friends:
            entry = next((r for r in result if r["user"]["id"] == df.id), None)
            if entry is None:
                entry = {
                    "user": _user_dict(df),
                    "last_message": "默认好友（官方账号）",
                    "last_time": None,
                    "unread_count": 0,
                    "is_mutual": True,
                }
            pinned_entries.append(entry)
        result = pinned_entries + [
            r for r in result if r["user"]["id"] not in default_ids
        ]
    return result


def count_unread_messages(user_id: int, db: Session) -> int:
    """统计当前用户所有私信未读数（用于底部导航栏消息红点）。"""
    count = db.scalar(
        select(func.count(Message.id)).where(
            Message.receiver_id == user_id,
            Message.is_read.is_(False),
        )
    )
    return int(count or 0)


def search_users(db: Session, user: User, keyword: str) -> list[dict]:
    """搜索用户（用于添加好友 / 全站搜索）：同时匹配昵称与账号（username）。"""
    if not keyword or len(keyword.strip()) < 1:
        return []
    rows = db.scalars(
        select(User)
        .options(selectinload(User.school))
        .where(
            or_(
                User.nickname.like(f"%{keyword}%"),
                User.username.like(f"%{keyword}%"),
            ),
            User.id != user.id,
            User.is_active.is_(True),
        )
        .limit(20)
    ).all()

    result = []
    for u in rows:
        conv = _conv_id(user.id, u.id)
        rel = db.scalar(
            select(FriendRequest).where(
                or_(
                    (FriendRequest.from_id == user.id) & (FriendRequest.to_id == u.id),
                    (FriendRequest.from_id == u.id) & (FriendRequest.to_id == user.id),
                ),
                FriendRequest.status == "accepted",
            )
        )
        is_friend = bool(rel)
        pending_sent = db.scalar(
            select(FriendRequest).where(
                FriendRequest.from_id == user.id,
                FriendRequest.to_id == u.id,
                FriendRequest.status == "pending",
            )
        )
        pending_received = db.scalar(
            select(FriendRequest).where(
                FriendRequest.from_id == u.id,
                FriendRequest.to_id == user.id,
                FriendRequest.status == "pending",
            )
        )
        rel_status = "friend" if is_friend else (
            "pending_sent" if pending_sent else (
                "pending_received" if pending_received else "none"
            )
        )
        result.append(
            {
                "user": {**_user_dict(u), "username": u.username},
                "relation": rel_status,
                "request_id": pending_received.id
                if pending_received
                else (pending_sent.id if pending_sent else None),
            }
        )
    return result
