"""用户认证业务逻辑层。

route 层只做参数校验和 Cookie 写入，业务逻辑（密码校验、Token 颁发、
登录失败锁定、审计日志）下沉到此处。

T2-5：logout 把 tokens.revoked = True，避免旧 refresh_token 继续可用（F21/D4）。
T2-6：新增 refresh_session 接口，access_token 过期后用 refresh_token 换新。
T7-8：登录失败锁定改用 SQLite 持久化（替代内存变量，进程重启不丢失）。
T7-9：登录/注册/发送验证码接口加 IP 限流（每分钟 10 次）。

邀请码系统（三状态）：
- guest（未登录）：只能看列表
- unverified（已注册未填邀请码）：能看帖子内容，不能发帖/评论/匹配/漂流瓶
- verified（已填邀请码）：解锁全部功能

每个 verified 用户自动获得一个 8 位邀请码，3 天冷却一次（让 1 个新人使用）。
被邀请人若违规核实为非学生 → 邀请人 invite_privilege_until += 30 天。
"""
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import (
    InviteCodeUsage,
    LoginLog,
    School,
    SeedInviteCode,
    Token,
    User,
)
from app.services.audit_log import log_user_action
from app.services.rate_limit_service import (
    check_login_locked,
    check_rate_limit,
    clear_login_failures,
    record_login_failure,
)


# ============ 邀请码工具函数 ============

INVITE_CODE_CHARS = string.ascii_uppercase + string.digits  # 不含易混淆字符 0/O/1/I
INVITE_CODE_COOLDOWN_DAYS = 3       # 自己的邀请码 3 天只能用 1 次
INVITE_PRIVILEGE_FREEZE_DAYS = 30   # 连坐冻结 30 天


def _generate_invite_code() -> str:
    """生成 8 位邀请码（大写字母+数字，去除易混淆字符）。"""
    safe_chars = "".join(c for c in INVITE_CODE_CHARS if c not in "0OI1")
    while True:
        code = "".join(secrets.choice(safe_chars) for _ in range(8))
        # 极小概率重复，由数据库 unique 约束兜底
        return code


def _assign_invite_code(db: Session, user: User) -> None:
    """为用户分配唯一的邀请码（重试最多 5 次避免碰撞）。"""
    for _ in range(5):
        code = _generate_invite_code()
        if not db.scalar(select(User).where(User.invite_code == code)):
            user.invite_code = code
            return
    # 兜底：用 user_id + 随机后缀
    user.invite_code = f"U{user.id}{secrets.token_hex(2)}".upper()[:8]


# ============ 鉴权相关 ============

def check_ip_rate_limit(db: Session, ip: str | None, action: str) -> None:
    """T7-9：IP 限流检查。超限抛 429。"""
    if not ip:
        return
    key = f"ip:{ip}:{action}"
    if not check_rate_limit(db, key):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


def _issue_tokens(response: Response, db: Session, user: User) -> dict[str, str]:
    """颁发 access_token + refresh_token 并写入 Cookie + 落库。"""
    settings = get_settings()
    access = create_token(str(user.id), minutes=settings.access_token_expire_minutes)
    refresh = create_token(str(user.id), days=settings.refresh_token_expire_days)
    db.add(Token(user_id=user.id, refresh_token=refresh))
    # 关键：设置 max_age 让 Cookie 跨浏览器会话持久化，否则浏览器关闭即丢失登录态
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie("access_token", access, httponly=True, samesite="strict", secure=settings.env != "dev", max_age=access_max_age, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, samesite="strict", secure=settings.env != "dev", max_age=refresh_max_age, path="/")
    return {"access_token": access, "refresh_token": refresh}


def register(payload, request, response: Response, db: Session) -> dict[str, Any]:
    """注册：IP 限流 + 校验 + 创建用户 + 邀请码处理 + 颁发 token + 审计日志。

    新方案：用户名 + 密码 + 校区；QQ 与邀请码均选填。
    - 注册时填邀请码 → 直接 verified
    - 注册时填种子码 → 直接 verified（消耗一个种子码）
    - 都不填 → unverified，可后续通过 /auth/apply-invite-code 补填
    """
    ip = _extract_ip(request)
    check_ip_rate_limit(db, ip, "register")

    if not payload.agreed:
        raise HTTPException(status_code=400, detail=ErrorCode.NOT_AGREED)
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail=ErrorCode.PASSWORD_MISMATCH)
    if not db.get(School, payload.school_id):
        raise HTTPException(status_code=400, detail=ErrorCode.SCHOOL_NOT_FOUND)
    # 用户名唯一性校验
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=400, detail=ErrorCode.USERNAME_EXISTS)

    # 邀请码处理：尝试匹配用户邀请码或种子码
    inviter_id: int | None = None
    seed_code_record: SeedInviteCode | None = None
    verification_status = "unverified"
    if payload.invite_code:
        code = payload.invite_code.strip().upper()
        # 1. 先查用户邀请码
        inviter = db.scalar(select(User).where(User.invite_code == code))
        if inviter:
            # 校验邀请人资格：3 天冷却 + 连坐冻结
            _check_inviter_privilege(db, inviter)
            inviter_id = inviter.id
            verification_status = "verified"
        else:
            # 2. 再查种子码
            seed = db.scalar(select(SeedInviteCode).where(SeedInviteCode.code == code, SeedInviteCode.used_by.is_(None)))
            if not seed:
                raise HTTPException(status_code=400, detail=ErrorCode.INVITE_CODE_INVALID)
            seed_code_record = seed
            verification_status = "verified"

    user = User(
        nickname=payload.nickname,
        username=payload.username,
        password_hash=hash_password(payload.password),
        school_id=payload.school_id,
        qq=payload.qq,
        verification_status=verification_status,
        verified_at=datetime.now() if verification_status == "verified" else None,
        invited_by=inviter_id,
    )
    db.add(user)
    db.flush()
    # 为每个用户分配自己的邀请码（包括 unverified 用户，但他们不能分享）
    _assign_invite_code(db, user)

    # 邀请码使用记录（使用 inviter 的邀请码，非 user 自己的码）
    if inviter_id:
        db.add(InviteCodeUsage(
            inviter_id=inviter_id,
            invitee_id=user.id,
            code=code,
            status="active",
        ))
        # 更新邀请人的 invite_code_shared_at（开始 3 天冷却）
        inviter = db.get(User, inviter_id)
        if inviter:
            inviter.invite_code_shared_at = datetime.now()

    # 种子码消耗
    if seed_code_record:
        seed_code_record.used_by = user.id
        seed_code_record.used_at = datetime.now()

    tokens = _issue_tokens(response, db, user)
    db.add(LoginLog(user_id=user.id, phone=user.username, success=True))
    log_user_action(
        db,
        user.id,
        "register",
        json.dumps(
            {"username": payload.username, "school_id": payload.school_id, "verification_status": verification_status},
            ensure_ascii=False,
        ),
        ip,
    )
    db.commit()
    return {
        "user_id": user.id,
        "verification_status": verification_status,
        **tokens,
    }


def login(payload, request, response: Response, db: Session) -> dict[str, Any]:
    """登录：IP 限流 + 失败锁定 + 密码校验 + 颁发 token + 审计日志。

    新方案：用户名 + 密码（不再支持验证码登录）。
    """
    ip = _extract_ip(request)
    check_ip_rate_limit(db, ip, "login")

    # T7-8：检查用户名是否被锁定（持久化），用 phone 字段兼容旧逻辑
    lock_key = payload.username
    if check_login_locked(db, lock_key):
        raise HTTPException(status_code=429, detail=ErrorCode.LOGIN_LOCKED)

    user = db.scalar(select(User).where(User.username == payload.username))
    if not user:
        db.add(LoginLog(phone=payload.username, success=False))
        log_user_action(
            db,
            None,
            "login_failed",
            json.dumps({"username": payload.username, "reason": "user_not_found"}, ensure_ascii=False),
            ip,
        )
        db.commit()
        record_login_failure(db, lock_key)
        raise HTTPException(status_code=401, detail=ErrorCode.LOGIN_FAILED)

    if not verify_password(payload.password, user.password_hash):
        db.add(LoginLog(user_id=user.id, phone=user.username, success=False))
        log_user_action(
            db,
            user.id,
            "login_failed",
            json.dumps({"username": payload.username, "reason": "wrong_password"}, ensure_ascii=False),
            ip,
        )
        db.commit()
        record_login_failure(db, lock_key)
        raise HTTPException(status_code=401, detail=ErrorCode.LOGIN_FAILED)

    clear_login_failures(db, lock_key)

    # 封号检查：允许登录但返回封号信息，由前端弹出封号提示页
    ban_info: dict | None = None
    if not user.is_active or (user.ban_until and user.ban_until > datetime.now()):
        is_still_banned = user.ban_until is None or user.ban_until > datetime.now()
        if not user.is_active or is_still_banned:
            ban_info = {
                "is_banned": True,
                "ban_until": user.ban_until.isoformat() if user.ban_until else None,
                "ban_reason": user.ban_reason,
                "violation_count": user.violation_count or 0,
            }

    tokens = _issue_tokens(response, db, user)
    db.add(LoginLog(user_id=user.id, phone=user.username, success=True))
    log_user_action(db, user.id, "login", json.dumps({"username": payload.username}, ensure_ascii=False), ip)
    db.commit()
    return {
        "user_id": user.id,
        "verification_status": user.verification_status,
        "ban_info": ban_info,
        **tokens,
    }


def logout(response: Response, db: Session, user: User) -> None:
    """登出：清 Cookie + 撤销 refresh_token + 审计日志。"""
    db.execute(
        update(Token)
        .where(Token.user_id == user.id, Token.revoked.is_(False))
        .values(revoked=True)
    )
    log_user_action(db, user.id, "logout", None, None)
    db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


def refresh_session(refresh_token: str | None, request: Request, response: Response, db: Session) -> dict[str, Any]:
    """用 refresh_token 换取新的 access_token。"""
    if not refresh_token:
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID)

    record = db.scalar(select(Token).where(Token.refresh_token == refresh_token))
    if not record or record.revoked:
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID)

    try:
        user_id = int(decode_token(refresh_token))
    except Exception:
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID) from None

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail=ErrorCode.USER_NOT_FOUND)

    settings = get_settings()
    new_access = create_token(str(user.id), minutes=settings.access_token_expire_minutes)
    new_refresh = create_token(str(user.id), days=settings.refresh_token_expire_days)
    record.revoked = True
    db.add(Token(user_id=user.id, refresh_token=new_refresh))

    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie("access_token", new_access, httponly=True, samesite="strict", secure=settings.env != "dev", max_age=access_max_age, path="/")
    response.set_cookie("refresh_token", new_refresh, httponly=True, samesite="strict", secure=settings.env != "dev", max_age=refresh_max_age, path="/")

    log_user_action(
        db,
        user.id,
        "refresh_token",
        json.dumps({"old_token_id": record.id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return {"user_id": user.id, "access_token": new_access, "refresh_token": new_refresh}


def _extract_ip(request) -> str | None:
    """从 Request 提取 IP（service 层避免循环依赖）。"""
    try:
        from app.api.deps import extract_ip

        return extract_ip(request)
    except Exception:
        return None


def change_password(payload, request, response: Response, db: Session, user: User) -> dict[str, Any]:
    """修改密码：校验旧密码 → 更新密码哈希 → 重发 token。"""
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail=ErrorCode.PASSWORD_MISMATCH)
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail=ErrorCode.LOGIN_FAILED)
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail=ErrorCode.PASSWORD_TOO_SHORT)

    user.password_hash = hash_password(payload.new_password)
    db.execute(
        update(Token)
        .where(Token.user_id == user.id, Token.revoked.is_(False))
        .values(revoked=True)
    )
    tokens = _issue_tokens(response, db, user)
    log_user_action(
        db,
        user.id,
        "change_password",
        json.dumps({"username": user.username}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return {"user_id": user.id, **tokens}


# ============ 邀请码业务 ============

def _check_inviter_privilege(db: Session, inviter: User) -> None:
    """校验邀请人是否有资格分享邀请码：3 天冷却 + 连坐冻结。"""
    now = datetime.now()
    # 连坐冻结期
    if inviter.invite_privilege_until and inviter.invite_privilege_until > now:
        raise HTTPException(status_code=403, detail=ErrorCode.INVITE_PRIVILEGE_FROZEN)
    # 3 天冷却
    if inviter.invite_code_shared_at and inviter.invite_code_shared_at > now - timedelta(days=INVITE_CODE_COOLDOWN_DAYS):
        raise HTTPException(status_code=403, detail=ErrorCode.INVITE_CODE_COOLDOWN)


def apply_invite_code(payload, request: Request, db: Session, user: User) -> dict[str, Any]:
    """填写邀请码解锁全部功能（已注册用户补填邀请码）。

    - 已 verified 用户不能再填（避免重复解锁）
    - 邀请码可以是其他用户的邀请码或种子码
    - 用户邀请码：校验邀请人资格（3 天冷却 + 连坐冻结），并记录使用关系
    - 种子码：直接消耗
    """
    if user.verification_status == "verified":
        return {"verification_status": "verified", "message": "已认证，无需再次填写邀请码"}

    # 防止同一用户重复填码（数据库唯一约束兜底）
    existing = db.scalar(select(InviteCodeUsage).where(InviteCodeUsage.invitee_id == user.id))
    if existing:
        raise HTTPException(status_code=400, detail=ErrorCode.INVITE_CODE_INVALID)

    code = payload.code.strip().upper()
    inviter_id: int | None = None
    seed_record: SeedInviteCode | None = None

    # 1. 先查用户邀请码
    inviter = db.scalar(select(User).where(User.invite_code == code))
    if inviter:
        if inviter.id == user.id:
            raise HTTPException(status_code=400, detail=ErrorCode.INVITE_CODE_INVALID)
        _check_inviter_privilege(db, inviter)
        inviter_id = inviter.id
    else:
        # 2. 再查种子码
        seed_record = db.scalar(
            select(SeedInviteCode)
            .where(SeedInviteCode.code == code, SeedInviteCode.used_by.is_(None))
        )
        if not seed_record:
            raise HTTPException(status_code=400, detail=ErrorCode.INVITE_CODE_INVALID)

    # 更新当前用户为 verified
    user.verification_status = "verified"
    user.verified_at = datetime.now()
    if inviter_id:
        user.invited_by = inviter_id
        # 记录邀请码使用关系
        db.add(InviteCodeUsage(
            inviter_id=inviter_id,
            invitee_id=user.id,
            code=code,
            status="active",
        ))
        # 更新邀请人冷却时间
        inviter.invite_code_shared_at = datetime.now()
    if seed_record:
        seed_record.used_by = user.id
        seed_record.used_at = datetime.now()

    log_user_action(
        db,
        user.id,
        "apply_invite_code",
        json.dumps({"code": code, "inviter_id": inviter_id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return {
        "verification_status": "verified",
        "verified_at": user.verified_at.isoformat(),
        "inviter_id": inviter_id,
    }


def get_my_invite_code(db: Session, user: User) -> dict[str, Any]:
    """获取自己的邀请码 + 分享状态（3 天冷却 + 连坐冻结）。"""
    # 如果用户还没有邀请码（理论上 register 时已分配），兜底生成
    if not user.invite_code:
        _assign_invite_code(db, user)
        db.commit()

    now = datetime.now()
    # 计算冷却剩余时间
    cooldown_remaining = 0
    if user.invite_code_shared_at:
        elapsed = now - user.invite_code_shared_at
        remaining = timedelta(days=INVITE_CODE_COOLDOWN_DAYS) - elapsed
        if remaining.total_seconds() > 0:
            cooldown_remaining = int(remaining.total_seconds())

    # 计算连坐冻结剩余时间
    frozen_remaining = 0
    is_frozen = False
    if user.invite_privilege_until and user.invite_privilege_until > now:
        is_frozen = True
        frozen_remaining = int((user.invite_privilege_until - now).total_seconds())

    can_share = (
        user.verification_status == "verified"
        and not is_frozen
        and cooldown_remaining == 0
    )

    return {
        "code": user.invite_code,
        "can_share": can_share,
        "cooldown_remaining": cooldown_remaining,  # 秒
        "is_frozen": is_frozen,
        "frozen_remaining": frozen_remaining,  # 秒
        "verification_status": user.verification_status,
    }


def get_verification_status(user: User) -> dict[str, Any]:
    """查询当前用户的认证状态。"""
    return {
        "verification_status": user.verification_status,
        "verified_at": user.verified_at.isoformat() if user.verified_at else None,
        "invited_by": user.invited_by,
        "qq": user.qq,
    }


def update_qq(payload, request: Request, db: Session, user: User) -> dict[str, Any]:
    """修改 QQ 号（设置页）。"""
    user.qq = payload.qq
    log_user_action(
        db,
        user.id,
        "update_qq",
        json.dumps({"qq": payload.qq}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    return {"qq": user.qq}


def freeze_inviter(db: Session, invitee_id: int, reason: str) -> None:
    """连坐机制：被邀请人违规核实后，冻结邀请人的分享资格 30 天。

    供管理员后台调用（如举报核实、人工审核发现非学生）。
    """
    usage = db.scalar(select(InviteCodeUsage).where(InviteCodeUsage.invitee_id == invitee_id))
    if not usage or not usage.inviter_id:
        return
    inviter = db.get(User, usage.inviter_id)
    if not inviter:
        return
    now = datetime.now()
    # 如果已有冻结期且未过期，从原冻结期延长 30 天；否则从现在延长 30 天
    base = inviter.invite_privilege_until if inviter.invite_privilege_until and inviter.invite_privilege_until > now else now
    inviter.invite_privilege_until = base + timedelta(days=INVITE_PRIVILEGE_FREEZE_DAYS)
    usage.status = "frozen"
    log_user_action(
        db,
        inviter.id,
        "invite_privilege_frozen",
        json.dumps({"invitee_id": invitee_id, "reason": reason}, ensure_ascii=False),
        None,
    )
    db.commit()
