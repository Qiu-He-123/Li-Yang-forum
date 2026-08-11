"""徽章（勋章）系统业务逻辑层。

功能：
- 徽章目录：所有启用徽章列表（含 is_owned / is_wearing 状态）
- 我的徽章：当前用户已拥有的徽章
- 激活码领取：管理员生成 BadgeCode，用户在「消息 → 系统」输入激活码领取徽章
- 佩戴/卸下：每人可拥有多个徽章，选择其中一个佩戴，佩戴徽章展示在名字前
- 管理员管理：徽章 CRUD、批量生成激活码、直接发放徽章
"""
import json
import secrets
import string
from datetime import datetime

from fastapi import HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import now_utc, to_iso_zh
from app.models import Admin, Badge, BadgeCode, BadgeRule, User, UserBadge
from app.services.audit_log import log_admin_action, log_user_action
from app.services.notification_service import create_notification


# ============ 种子徽章（启动时幂等初始化，至少 20 个） ============

DEFAULT_BADGES: list[dict] = [
    # 身份类（必须包含：管理员徽章、集团成员徽章）
    {"name": "管理员", "code": "admin", "icon": "🛡️", "description": "立洋社区管理员专属徽章，维护社区秩序。", "sort_order": 1, "is_system": True},
    {"name": "集团成员", "code": "group_member", "icon": "🏢", "description": "立洋教育集团成员专属徽章。", "sort_order": 2, "is_system": True},
    {"name": "认证学生", "code": "verified_student", "icon": "🎓", "description": "通过学生认证的立洋学子。", "sort_order": 3, "is_system": True},
    {"name": "新人报到", "code": "newcomer", "icon": "🌱", "description": "初来乍到，多多关照。", "sort_order": 4},
    # 活跃 / 贡献类
    {"name": "签到达人", "code": "checkin_master", "icon": "📅", "description": "坚持每日签到，风雨无阻。", "sort_order": 5},
    {"name": "社区之星", "code": "community_star", "icon": "⭐", "description": "积极互动，深受大家喜爱。", "sort_order": 6},
    {"name": "活跃达人", "code": "active_member", "icon": "🔥", "description": "社区活跃分子，充满热情。", "sort_order": 7},
    {"name": "热心肠", "code": "helpful", "icon": "🤝", "description": "乐于助人，温暖校园。", "sort_order": 8},
    {"name": "创作大师", "code": "creator", "icon": "✍️", "description": "优质内容创作者，笔耕不辍。", "sort_order": 9},
    {"name": "分享狂魔", "code": "sharer", "icon": "📤", "description": "乐于分享校园新鲜事。", "sort_order": 10},
    # 圈子 / 内容类
    {"name": "圈子达人", "code": "circle_expert", "icon": "🏷️", "description": "创建或管理圈子的达人。", "sort_order": 11},
    {"name": "提问能手", "code": "question_master", "icon": "❓", "description": "善于提出有价值的问题。", "sort_order": 12},
    {"name": "答题学霸", "code": "answer_expert", "icon": "💡", "description": "学习互助中的答题高手。", "sort_order": 13},
    {"name": "表白达人", "code": "confess_master", "icon": "💘", "description": "表白墙常客，勇气可嘉。", "sort_order": 14},
    {"name": "美食家", "code": "foodie", "icon": "🍜", "description": "校园美食探店先锋。", "sort_order": 15},
    {"name": "摄影大师", "code": "photographer", "icon": "📷", "description": "用镜头记录校园美好。", "sort_order": 16},
    {"name": "游戏高手", "code": "gamer", "icon": "🎮", "description": "开黑上分，样样在行。", "sort_order": 17},
    # 生活 / 趣味类
    {"name": "早起鸟", "code": "early_bird", "icon": "🐦", "description": "每天迎着朝阳出发。", "sort_order": 18},
    {"name": "夜猫子", "code": "night_owl", "icon": "🦉", "description": "深夜出没的校园守护者。", "sort_order": 19},
    {"name": "运动健将", "code": "athlete", "icon": "⚽", "description": "热爱运动，活力四射。", "sort_order": 20},
    {"name": "自律达人", "code": "self_discipline", "icon": "⏰", "description": "时间管理大师，自律即自由。", "sort_order": 21},
    {"name": "元老用户", "code": "veteran", "icon": "👑", "description": "陪伴社区一路走来的元老。", "sort_order": 22},
]


# ============ 徽章自动发放：支持的动作（后台可配置规则） ============

SUPPORTED_ACTIONS: dict[str, str] = {
    "checkin_consecutive": "连续签到天数",
    "approved_posts": "审核通过的帖子数",
    "approved_comments": "审核通过的评论数",
    "followers_count": "粉丝数",
    "likes_received": "获赞总数",
}


# ============ 序列化 ============

def badge_dict(badge: Badge | None) -> dict | None:
    """序列化徽章。badge 为 None 时返回 None（未佩戴）。"""
    if badge is None:
        return None
    return {
        "id": badge.id,
        "name": badge.name,
        "code": badge.code,
        "icon": badge.icon,
        "description": badge.description,
        "is_active": badge.is_active,
        "sort_order": badge.sort_order,
        "created_at": to_iso_zh(badge.created_at),
    }


def get_badge_by_id(db: Session, badge_id: int) -> Badge | None:
    return db.get(Badge, badge_id)


def get_wearing_badge(db: Session, user: User) -> Badge | None:
    """获取用户当前佩戴的徽章对象（无则 None）。"""
    if not user.wearing_badge_id:
        return None
    return db.get(Badge, user.wearing_badge_id)


def _owned_badge_ids(db: Session, user_id: int) -> set[int]:
    rows = db.scalars(
        select(UserBadge.badge_id).where(UserBadge.user_id == user_id)
    ).all()
    return set(rows)


def _badge_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(UserBadge.id)).where(UserBadge.user_id == user_id)
    ) or 0


# ============ 用户侧接口 ============

def list_badges(db: Session, user: User | None = None) -> list[dict]:
    """徽章目录（仅启用徽章，按 sort_order 排序）。"""
    rows = db.scalars(
        select(Badge)
        .where(Badge.is_active.is_(True))
        .order_by(Badge.sort_order.asc(), Badge.id.asc())
    ).all()
    owned = _owned_badge_ids(db, user.id) if user else set()
    result = []
    for b in rows:
        d = badge_dict(b)
        d["is_owned"] = b.id in owned
        d["is_wearing"] = bool(user and user.wearing_badge_id == b.id)
        result.append(d)
    return result


def my_badges(db: Session, user: User) -> dict:
    """我的徽章：已拥有列表 + 当前佩戴 + 全部目录。"""
    owned = _owned_badges_with_time(db, user)
    return {
        "owned": owned,
        "wearing_badge": badge_dict(get_wearing_badge(db, user)),
        "wearing_badge_id": user.wearing_badge_id,
        "total": len(owned),
        "all_badges": list_badges(db, user),
    }


def user_badges(db: Session, target: User) -> dict:
    """某用户的勋章列表（登录用户均可查看），含获取时间与佩戴状态。"""
    owned = _owned_badges_with_time(db, target)
    return {
        "owned": owned,
        "wearing_badge": badge_dict(get_wearing_badge(db, target)),
        "wearing_badge_id": target.wearing_badge_id,
        "total": len(owned),
    }


def _owned_badges_with_time(db: Session, user: User) -> list[dict]:
    """已拥有徽章列表：含获取时间（user_badges.created_at）与佩戴状态。"""
    owned_ids = _owned_badge_ids(db, user.id)
    owned_rows = (
        db.scalars(
            select(Badge)
            .where(Badge.id.in_(owned_ids))
            .order_by(Badge.sort_order.asc(), Badge.id.asc())
        ).all()
        if owned_ids
        else []
    )
    acquired: dict[int, str | None] = {}
    if owned_ids:
        for ub in db.scalars(select(UserBadge).where(UserBadge.user_id == user.id)):
            acquired[ub.badge_id] = to_iso_zh(ub.created_at)
    owned = []
    for b in owned_rows:
        d = badge_dict(b)
        d["is_wearing"] = user.wearing_badge_id == b.id
        d["acquired_at"] = acquired.get(b.id)
        owned.append(d)
    return owned


def claim_badge_by_code(db: Session, user: User, code: str, request: Request) -> dict:
    """用户使用激活码领取徽章。"""
    code = (code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_CODE_INVALID)

    row = db.scalar(select(BadgeCode).where(BadgeCode.code == code))
    if not row or row.used_by is not None:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_CODE_INVALID)
    badge = db.get(Badge, row.badge_id)
    if not badge or not badge.is_active:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_NOT_FOUND)

    # 已拥有则直接返回（幂等），但激活码仍然消耗？不消耗更好：已拥有时返回提示
    existing = db.scalar(
        select(UserBadge).where(
            UserBadge.user_id == user.id, UserBadge.badge_id == badge.id
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_ALREADY_OWNED)

    db.add(UserBadge(user_id=user.id, badge_id=badge.id))
    row.used_by = user.id
    row.used_at = now_utc()
    # 领取后默认自动佩戴（如果当前没佩戴任何徽章）
    if not user.wearing_badge_id:
        user.wearing_badge_id = badge.id
    log_user_action(
        db,
        user.id,
        "claim_badge",
        json.dumps({"badge_id": badge.id, "badge_name": badge.name, "code": code}, ensure_ascii=False),
        _extract_ip(request),
    )
    # 系统通知：告知领取成功（消息 → 系统 可查看）
    create_notification(
        db,
        user.id,
        "徽章领取成功",
        f"恭喜你获得了「{badge.icon} {badge.name}」徽章！"
        f"可前往「我的 → 徽章中心」选择佩戴，展示在名字前。",
        ntype="system",
        reference_type="badge",
        reference_id=badge.id,
    )
    db.commit()
    db.refresh(user)
    return badge_dict(badge)


def wear_badge(db: Session, user: User, badge_id: int, request: Request) -> dict:
    """佩戴徽章（必须已拥有）。"""
    badge = db.get(Badge, badge_id)
    if not badge or not badge.is_active:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_NOT_FOUND)
    owned = db.scalar(
        select(UserBadge).where(
            UserBadge.user_id == user.id, UserBadge.badge_id == badge_id
        )
    )
    if not owned:
        raise HTTPException(status_code=403, detail=ErrorCode.BADGE_CANNOT_WEAR)
    user.wearing_badge_id = badge_id
    log_user_action(
        db,
        user.id,
        "wear_badge",
        json.dumps({"badge_id": badge_id, "badge_name": badge.name}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(user)
    return badge_dict(badge)


def unwear_badge(db: Session, user: User, request: Request) -> dict:
    """卸下当前佩戴的徽章。"""
    if user.wearing_badge_id:
        log_user_action(
            db,
            user.id,
            "unwear_badge",
            json.dumps({"badge_id": user.wearing_badge_id}, ensure_ascii=False),
            _extract_ip(request),
        )
    user.wearing_badge_id = None
    db.commit()
    db.refresh(user)
    return {"wearing_badge": None}


# ============ 管理员接口 ============

def admin_list_badges(db: Session, keyword: str | None = None) -> list[dict]:
    """后台徽章列表（含已停用徽章 + 激活码数量）。"""
    query = select(Badge).order_by(Badge.sort_order.asc(), Badge.id.asc())
    if keyword:
        query = query.where(
            Badge.name.contains(keyword) | Badge.code.contains(keyword)
        )
    rows = db.scalars(query).all()
    result = []
    for b in rows:
        d = badge_dict(b)
        d["is_system"] = b.is_system
        d["code_count"] = (
            db.scalar(select(func.count(BadgeCode.id)).where(BadgeCode.badge_id == b.id))
            or 0
        )
        d["used_code_count"] = (
            db.scalar(
                select(func.count(BadgeCode.id)).where(
                    BadgeCode.badge_id == b.id, BadgeCode.used_by.is_not(None)
                )
            )
            or 0
        )
        d["owner_count"] = (
            db.scalar(select(func.count(UserBadge.id)).where(UserBadge.badge_id == b.id))
            or 0
        )
        result.append(d)
    return result


def admin_create_badge(payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """创建徽章。payload: name/code/icon/description/is_active/sort_order/is_system。"""
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip().lower()
    if not name or not code:
        raise HTTPException(status_code=400, detail="徽章名称和标识不能为空")
    if db.scalar(select(Badge).where(Badge.code == code)) or db.scalar(
        select(Badge).where(Badge.name == name)
    ):
        raise HTTPException(status_code=400, detail="徽章名称或标识已存在")
    badge = Badge(
        name=name[:32],
        code=code[:32],
        icon=(payload.get("icon") or "🏅").strip()[:500],
        description=(payload.get("description") or "").strip()[:200] or None,
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order", 0) or 0),
        is_system=bool(payload.get("is_system", False)),
    )
    db.add(badge)
    log_admin_action(
        db,
        admin.id,
        "create_badge",
        json.dumps({"badge_name": name, "code": code}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(badge)
    return badge_dict(badge)


def admin_update_badge(badge_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """更新徽章（名称/图标/描述/排序/启用状态）。"""
    badge = db.get(Badge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail=ErrorCode.BADGE_NOT_FOUND)
    changes = {}
    for key in ("name", "icon", "description", "is_active", "sort_order"):
        if key in payload and getattr(badge, key) != payload[key]:
            changes[key] = {"old": getattr(badge, key), "new": payload[key]}
            setattr(badge, key, payload[key])
    if changes:
        log_admin_action(
            db,
            admin.id,
            "update_badge",
            json.dumps({"badge_id": badge_id, "changes": changes}, ensure_ascii=False),
            _extract_ip(request),
        )
    db.commit()
    db.refresh(badge)
    return badge_dict(badge)


def admin_delete_badge(badge_id: int, request: Request, db: Session, admin: Admin) -> None:
    """删除徽章（系统徽章不可删除，只能停用）。"""
    badge = db.get(Badge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail=ErrorCode.BADGE_NOT_FOUND)
    if badge.is_system:
        raise HTTPException(status_code=400, detail="系统徽章不可删除，可停用")
    # 删除徽章的同时清理关联数据
    db.query(UserBadge).filter(UserBadge.badge_id == badge_id).delete()
    db.query(BadgeCode).filter(BadgeCode.badge_id == badge_id).delete()
    # 用户佩戴该徽章的，卸下佩戴
    db.query(User).filter(User.wearing_badge_id == badge_id).update(
        {User.wearing_badge_id: None}
    )
    db.delete(badge)
    log_admin_action(
        db,
        admin.id,
        "delete_badge",
        json.dumps({"badge_id": badge_id, "badge_name": badge.name}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()


def admin_generate_badge_codes(
    db: Session, admin: Admin, badge_id: int, count: int = 1,
    request: Request | None = None,
    note: str | None = None, batch_no: str | None = None,
) -> dict:
    """批量生成徽章激活码（格式 B + 8 位大写字母数字，避开易混淆字符）。"""
    badge = db.get(Badge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail=ErrorCode.BADGE_NOT_FOUND)
    count = max(1, min(100, int(count or 1)))
    batch_no = batch_no or f"B{datetime.now():%Y%m%d%H%M%S}"
    safe_chars = "".join(
        c for c in (string.ascii_uppercase + string.digits) if c not in "0OI1"
    )
    created: list[str] = []
    for _ in range(count):
        for _retry in range(20):
            code = "B" + "".join(secrets.choice(safe_chars) for _ in range(8))
            if not db.scalar(select(BadgeCode).where(BadgeCode.code == code)):
                db.add(
                    BadgeCode(
                        badge_id=badge_id,
                        code=code,
                        note=note,
                        batch_no=batch_no,
                        created_by=admin.id,
                    )
                )
                created.append(code)
                break
    log_admin_action(
        db,
        admin.id,
        "generate_badge_codes",
        json.dumps(
            {"badge_id": badge_id, "badge_name": badge.name, "count": len(created), "batch_no": batch_no},
            ensure_ascii=False,
        ),
        _extract_ip(request),
    )
    db.commit()
    return {"badge": badge_dict(badge), "codes": created, "batch_no": batch_no}


def admin_list_badge_codes(
    db: Session, badge_id: int | None = None, status: str | None = None,
    page: int = 1, page_size: int = 20,
) -> dict:
    """激活码列表（分页 + 徽章/状态过滤）。"""
    query = select(BadgeCode).order_by(desc(BadgeCode.created_at))
    if badge_id:
        query = query.where(BadgeCode.badge_id == badge_id)
    if status == "used":
        query = query.where(BadgeCode.used_by.is_not(None))
    elif status == "unused":
        query = query.where(BadgeCode.used_by.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    badge_ids = {r.badge_id for r in rows}
    badges = {
        b.id: b
        for b in db.scalars(select(Badge).where(Badge.id.in_(badge_ids))).all()
    } if badge_ids else {}
    users = {}
    user_ids = {r.used_by for r in rows if r.used_by}
    if user_ids:
        users = {
            u.id: u
            for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()
        }
    items = []
    for r in rows:
        b = badges.get(r.badge_id)
        u = users.get(r.used_by)
        items.append({
            "id": r.id,
            "code": r.code,
            "badge_id": r.badge_id,
            "badge_name": b.name if b else None,
            "badge_icon": b.icon if b else None,
            "note": r.note,
            "batch_no": r.batch_no,
            "created_at": to_iso_zh(r.created_at),
            "used_by": r.used_by,
            "used_nickname": u.nickname if u else None,
            "used_at": to_iso_zh(r.used_at) if r.used_at else None,
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


def admin_delete_badge_code(code_id: int, request: Request, db: Session, admin: Admin) -> None:
    """删除未使用的激活码（已使用的保留用于审计）。"""
    row = db.get(BadgeCode, code_id)
    if not row:
        raise HTTPException(status_code=404, detail="激活码不存在")
    if row.used_by is not None:
        raise HTTPException(status_code=400, detail="已使用的激活码不可删除")
    db.delete(row)
    log_admin_action(
        db,
        admin.id,
        "delete_badge_code",
        json.dumps({"code_id": code_id, "code": row.code}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()


def admin_grant_badge(user_id: int, badge_id: int, request: Request, db: Session, admin: Admin) -> dict:
    """管理员直接向用户发放徽章（线下渠道）。"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)
    badge = db.get(Badge, badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail=ErrorCode.BADGE_NOT_FOUND)
    existing = db.scalar(
        select(UserBadge).where(
            UserBadge.user_id == user_id, UserBadge.badge_id == badge_id
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_ALREADY_OWNED)
    db.add(UserBadge(user_id=user_id, badge_id=badge_id))
    if not user.wearing_badge_id:
        user.wearing_badge_id = badge_id
    log_admin_action(
        db,
        admin.id,
        "grant_badge",
        json.dumps({"user_id": user_id, "badge_id": badge_id, "badge_name": badge.name}, ensure_ascii=False),
        _extract_ip(request),
    )
    # 通知用户获得徽章
    create_notification(
        db,
        user_id,
        "获得新徽章",
        f"管理员为你发放了「{badge.icon} {badge.name}」徽章！",
        ntype="system",
        reference_type="badge",
        reference_id=badge_id,
    )
    db.commit()
    return {"user_id": user_id, "badge": badge_dict(badge)}


# ============ 自动发放 ============

def auto_grant_by_action(db: Session, user: User, action: str, value: int) -> list[dict]:
    """按动作触发值自动发放徽章（幂等：已拥有/未启用规则跳过）。

    在业务动作发生后调用（如签到、帖子审核通过、获赞、粉丝数变化等），
    达到任一启用规则的阈值即自动发放对应徽章并通知用户。
    """
    if action not in SUPPORTED_ACTIONS or value <= 0:
        return []
    rules = db.scalars(
        select(BadgeRule).where(
            BadgeRule.action == action,
            BadgeRule.is_enabled.is_(True),
        )
    ).all()
    granted: list[dict] = []
    for rule in rules:
        if value < rule.threshold:
            continue
        badge = db.get(Badge, rule.badge_id)
        if not badge or not badge.is_active:
            continue
        existing = db.scalar(
            select(UserBadge).where(
                UserBadge.user_id == user.id,
                UserBadge.badge_id == badge.id,
            )
        )
        if existing:
            continue
        db.add(UserBadge(user_id=user.id, badge_id=badge.id))
        if not user.wearing_badge_id:
            user.wearing_badge_id = badge.id
        create_notification(
            db,
            user.id,
            "自动获得新徽章",
            f"恭喜你在「{SUPPORTED_ACTIONS[action]}」上达到 {rule.threshold}，"
            f"系统自动发放了「{badge.icon} {badge.name}」徽章！",
            ntype="system",
            reference_type="badge",
            reference_id=badge.id,
        )
        granted.append(badge_dict(badge))
    if granted:
        db.commit()
    return granted


def admin_list_badge_rules(db: Session) -> list[dict]:
    """后台徽章自动发放规则列表。"""
    rows = db.scalars(
        select(BadgeRule).order_by(BadgeRule.action.asc(), BadgeRule.threshold.asc())
    ).all()
    badge_ids = {r.badge_id for r in rows}
    badges = {
        b.id: b
        for b in db.scalars(select(Badge).where(Badge.id.in_(badge_ids))).all()
    } if badge_ids else {}
    return [
        {
            "id": r.id,
            "action": r.action,
            "action_label": SUPPORTED_ACTIONS.get(r.action, r.action),
            "badge_id": r.badge_id,
            "badge_name": badges.get(r.badge_id).name if badges.get(r.badge_id) else None,
            "badge_icon": badges.get(r.badge_id).icon if badges.get(r.badge_id) else None,
            "threshold": r.threshold,
            "description": r.description,
            "is_enabled": r.is_enabled,
            "created_at": to_iso_zh(r.created_at),
        }
        for r in rows
    ]


def admin_create_badge_rule(payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """创建自动发放规则。payload: action/badge_id/threshold/description/is_enabled。"""
    action = (payload.get("action") or "").strip()
    badge_id = int(payload.get("badge_id", 0) or 0)
    threshold = int(payload.get("threshold", 1) or 1)
    if action not in SUPPORTED_ACTIONS:
        raise HTTPException(status_code=400, detail="不支持的动作类型")
    if not db.get(Badge, badge_id):
        raise HTTPException(status_code=400, detail=ErrorCode.BADGE_NOT_FOUND)
    if threshold < 1:
        raise HTTPException(status_code=400, detail="阈值必须 >= 1")
    existing = db.scalar(
        select(BadgeRule).where(
            BadgeRule.action == action,
            BadgeRule.threshold == threshold,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="同一动作 + 阈值的规则已存在")
    rule = BadgeRule(
        action=action,
        badge_id=badge_id,
        threshold=threshold,
        description=(payload.get("description") or "").strip()[:200] or None,
        is_enabled=bool(payload.get("is_enabled", True)),
    )
    db.add(rule)
    log_admin_action(
        db,
        admin.id,
        "create_badge_rule",
        json.dumps({"action": action, "badge_id": badge_id, "threshold": threshold}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(rule)
    return {
        "id": rule.id,
        "action": rule.action,
        "action_label": SUPPORTED_ACTIONS.get(rule.action, rule.action),
        "badge_id": rule.badge_id,
        "threshold": rule.threshold,
        "description": rule.description,
        "is_enabled": rule.is_enabled,
        "created_at": to_iso_zh(rule.created_at),
    }


def admin_update_badge_rule(rule_id: int, payload: dict, request: Request, db: Session, admin: Admin) -> dict:
    """更新自动发放规则。"""
    rule = db.get(BadgeRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    changes = {}
    for key in ("badge_id", "threshold", "description", "is_enabled"):
        if key in payload and getattr(rule, key) != payload[key]:
            changes[key] = {"old": getattr(rule, key), "new": payload[key]}
            setattr(rule, key, payload[key])
    if changes:
        log_admin_action(
            db,
            admin.id,
            "update_badge_rule",
            json.dumps({"rule_id": rule_id, "changes": changes}, ensure_ascii=False),
            _extract_ip(request),
        )
    db.commit()
    db.refresh(rule)
    return {
        "id": rule.id,
        "action": rule.action,
        "action_label": SUPPORTED_ACTIONS.get(rule.action, rule.action),
        "badge_id": rule.badge_id,
        "threshold": rule.threshold,
        "description": rule.description,
        "is_enabled": rule.is_enabled,
        "created_at": to_iso_zh(rule.created_at),
    }


def admin_delete_badge_rule(rule_id: int, request: Request, db: Session, admin: Admin) -> None:
    """删除自动发放规则。"""
    rule = db.get(BadgeRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    log_admin_action(
        db,
        admin.id,
        "delete_badge_rule",
        json.dumps({"rule_id": rule_id, "action": rule.action, "threshold": rule.threshold}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.delete(rule)
    db.commit()


def _extract_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    try:
        from app.api.deps import extract_ip
        return extract_ip(request)
    except Exception:
        return None
