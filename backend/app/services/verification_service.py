"""学生认证 + 管理员邀请码生成业务逻辑层。

两类功能：
1. 学生认证（用户上传学生证/校园卡照片 → 管理员审核 → 自动发放邀请码）
2. 管理员生成种子邀请码（批量生成，便于线下发放给可靠的班长/学生会主席）

防护机制：
- 每个用户只能有一个 pending 状态的认证申请
- 每天最多提交 3 次认证申请（防刷）
- 图片必须通过 magic bytes 校验（在 routes 层完成）
- 管理员审核记录 reviewer_id
- 已 verified 用户不能再提交认证申请
- 种子邀请码生成时校验唯一性（重试机制）
"""
from __future__ import annotations

import json
import secrets
import string
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import to_iso_zh
from app.models import (
    Admin,
    Image,
    SeedInviteCode,
    StudentVerification,
    User,
)
from app.services.audit_log import log_admin_action, log_user_action
from app.services.auth_service import _assign_invite_code


# 防刷：每天最多提交 3 次认证申请
DAILY_SUBMIT_LIMIT = 3
# 种子码字符集（去除易混淆字符）
SEED_CODE_CHARS = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "0OI1")


# ============ 用户端：学生认证申请 ============

def _extract_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    try:
        from app.api.deps import extract_ip
        return extract_ip(request)
    except Exception:
        return None


def get_my_verification_status(db: Session, user: User) -> dict[str, Any]:
    """查询当前用户的认证申请状态。

    返回：
    - verification_status: 用户当前的认证状态（unverified/verified）
    - latest_application: 最近一次申请（含 status / reject_reason / created_at）
    - pending_count: 当前 pending 申请数（0 或 1）
    """
    latest = db.scalar(
        select(StudentVerification)
        .where(StudentVerification.user_id == user.id)
        .order_by(StudentVerification.created_at.desc())
    )
    pending_count = db.scalar(
        select(func.count())
        .select_from(StudentVerification)
        .where(StudentVerification.user_id == user.id, StudentVerification.status == "pending")
    ) or 0
    return {
        "verification_status": user.verification_status,
        "latest_application": _verification_dict(latest) if latest else None,
        "pending_count": int(pending_count),
    }


def submit_verification(
    db: Session,
    user: User,
    image_id: int,
    note: str | None,
    request: Request | None = None,
) -> dict[str, Any]:
    """提交学生认证申请。

    防护：
    - 已 verified 用户不能再提交
    - 每个用户只能有一个 pending 申请
    - 每天最多 3 次（防刷）
    """
    # 已 verified 用户不允许再申请
    if user.verification_status == "verified":
        raise HTTPException(status_code=400, detail="你已通过认证，无需再次申请")

    # P0-1/P1-3：必须引用本人私密上传的图片，拒绝任意 URL 与引用他人图片
    image = db.get(Image, image_id)
    if not image or image.user_id != user.id:
        raise HTTPException(status_code=400, detail="请使用本人上传的学生证照片")
    if not image.is_private:
        raise HTTPException(status_code=400, detail="请通过私密上传通道提交学生证照片")
    image_url = image.url
    note = (note or "").strip()
    if len(note) > 200:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)

    # 防重复：每个用户只能有一个 pending 申请
    existing_pending = db.scalar(
        select(StudentVerification).where(
            StudentVerification.user_id == user.id,
            StudentVerification.status == "pending",
        )
    )
    if existing_pending:
        raise HTTPException(status_code=400, detail="你已有一个待审核的申请，请等待管理员审核")

    # 防刷：每天最多 3 次（含已 rejected 的）
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.scalar(
        select(func.count())
        .select_from(StudentVerification)
        .where(StudentVerification.user_id == user.id, StudentVerification.created_at >= today_start)
    ) or 0
    if int(today_count) >= DAILY_SUBMIT_LIMIT:
        raise HTTPException(status_code=429, detail="今日提交次数已达上限，明天再试")

    verification = StudentVerification(
        user_id=user.id,
        image_url=image_url,
        note=note or None,
        status="pending",
    )
    db.add(verification)
    log_user_action(
        db,
        user.id,
        "submit_student_verification",
        json.dumps({"verification_id": verification.id}, ensure_ascii=False),
        _extract_ip(request),
    )
    db.commit()
    db.refresh(verification)
    return _verification_dict(verification, user=user)


def _verification_dict(
    v: StudentVerification,
    user: User | None = None,
    reviewer: Admin | None = None,
) -> dict[str, Any]:
    return {
        "id": v.id,
        "user_id": v.user_id,
        "user_nickname": user.nickname if user else None,
        "user_username": user.username if user else None,
        "image_url": v.image_url,
        "note": v.note,
        "status": v.status,
        "reviewer_id": v.reviewer_id,
        "reviewer_username": reviewer.username if reviewer else None,
        "reviewed_at": to_iso_zh(v.reviewed_at) if v.reviewed_at else None,
        "reject_reason": v.reject_reason,
        "granted_invite_code": v.granted_invite_code,
        "created_at": to_iso_zh(v.created_at),
    }


# ============ 管理员端：学生认证审核 ============

def admin_list_verifications(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    """管理员查看学生认证申请列表。"""
    query = select(StudentVerification).order_by(StudentVerification.created_at.desc())
    if status in ("pending", "approved", "rejected"):
        query = query.where(StudentVerification.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    # 批量加载用户信息
    user_ids = list({v.user_id for v in rows})
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    reviewer_ids = list({v.reviewer_id for v in rows if v.reviewer_id})
    reviewers = {a.id: a for a in db.scalars(select(Admin).where(Admin.id.in_(reviewer_ids))).all()} if reviewer_ids else {}
    return {
        "items": [_verification_dict(v, user=users.get(v.user_id), reviewer=reviewers.get(v.reviewer_id)) for v in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def admin_review_verification(
    db: Session,
    verification_id: int,
    action: str,
    admin: Admin,
    reject_reason: str | None = None,
) -> dict[str, Any]:
    """管理员审核学生认证申请。

    action: approve / reject
    - approve: 自动生成种子邀请码并分配给用户 → 用户变为 verified
    - reject:  通知用户重新上传（reject_reason 必填）
    """
    v = db.get(StudentVerification, verification_id)
    if not v:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    if v.status != "pending":
        raise HTTPException(status_code=400, detail=f"该申请当前状态为 {v.status}，无法重复审核")

    user = db.get(User, v.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=ErrorCode.USER_NOT_FOUND)

    if action == "approve":
        # 生成种子邀请码并消耗（直接绑定给用户）
        seed_code = _generate_seed_code(db)
        seed_record = SeedInviteCode(
            code=seed_code,
            note=f"学生认证通过自动生成（user_id={user.id}, verification_id={v.id}）",
            batch_no=f"verify-{v.id}",
            status="used",
            used_by=user.id,
            used_at=datetime.now(),
        )
        db.add(seed_record)

        # 用户变为 verified
        v.status = "approved"
        v.reviewer_id = admin.id
        v.reviewed_at = datetime.now()
        v.granted_invite_code = seed_code
        user.verification_status = "verified"
        user.verified_at = datetime.now()
        # 若用户没有邀请码，分配一个
        if not user.invite_code:
            _assign_invite_code(db, user)

        log_admin_action(
            db,
            admin.id,
            "approve_student_verification",
            json.dumps({
                "verification_id": v.id,
                "user_id": user.id,
                "granted_code": seed_code,
            }, ensure_ascii=False),
            None,
        )
    elif action == "reject":
        reject_reason = (reject_reason or "").strip()
        if not reject_reason:
            raise HTTPException(status_code=400, detail="驳回必须填写原因")
        if len(reject_reason) > 200:
            raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)
        v.status = "rejected"
        v.reviewer_id = admin.id
        v.reviewed_at = datetime.now()
        v.reject_reason = reject_reason

        log_admin_action(
            db,
            admin.id,
            "reject_student_verification",
            json.dumps({
                "verification_id": v.id,
                "user_id": user.id,
                "reason": reject_reason,
            }, ensure_ascii=False),
            None,
        )
    else:
        raise HTTPException(status_code=400, detail=ErrorCode.PARAM_ERROR)

    db.commit()
    db.refresh(v)
    reviewer = db.get(Admin, v.reviewer_id) if v.reviewer_id else None
    return _verification_dict(v, user=user, reviewer=reviewer)


# ============ 管理员端：种子邀请码生成 ============

def _generate_seed_code(db: Session) -> str:
    """生成一个未被使用的种子邀请码（重试 10 次避免碰撞）。"""
    for _ in range(10):
        code = "".join(secrets.choice(SEED_CODE_CHARS) for _ in range(8))
        if not db.scalar(select(SeedInviteCode).where(SeedInviteCode.code == code)):
            return code
    # 兜底：用时间戳后缀
    code = f"S{int(datetime.now().timestamp()) % 1000000:06d}"
    while db.scalar(select(SeedInviteCode).where(SeedInviteCode.code == code)):
        code = f"S{secrets.token_hex(3).upper()}"
    return code


def admin_generate_seed_codes(
    db: Session,
    admin: Admin,
    count: int = 1,
    note: str | None = None,
    batch_no: str | None = None,
) -> dict[str, Any]:
    """管理员批量生成种子邀请码。

    Args:
        count: 生成数量（1-100）
        note: 备注
        batch_no: 批次号（不传则自动生成 batch-yyyymmdd-HHMMSS）
    """
    if count < 1 or count > 100:
        raise HTTPException(status_code=400, detail="生成数量必须在 1-100 之间")
    note = (note or "").strip()[:100] if note else None
    if not batch_no:
        batch_no = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    codes: list[str] = []
    for _ in range(count):
        code = _generate_seed_code(db)
        db.add(SeedInviteCode(
            code=code,
            note=note,
            batch_no=batch_no,
            status="unused",
            created_by=admin.id,
        ))
        codes.append(code)

    log_admin_action(
        db,
        admin.id,
        "generate_seed_invite_codes",
        json.dumps({"count": count, "batch_no": batch_no, "note": note}, ensure_ascii=False),
        None,
    )
    db.commit()
    return {
        "batch_no": batch_no,
        "count": len(codes),
        "codes": codes,
    }


def admin_list_seed_codes(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    batch_no: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """管理员查看种子邀请码列表。

    status:
    - unused: 未使用
    - reserved: 待使用（已被管理员复制带走）
    - used: 已使用
    - None: 全部
    """
    query = select(SeedInviteCode).order_by(SeedInviteCode.created_at.desc())
    if batch_no:
        query = query.where(SeedInviteCode.batch_no == batch_no)
    if status in ("unused", "reserved", "used"):
        query = query.where(SeedInviteCode.status == status)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    # 批量加载使用人
    user_ids = list({r.used_by for r in rows if r.used_by})
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    # 批量加载预留管理员
    admin_ids = list({r.reserved_by for r in rows if r.reserved_by})
    admins = {a.id: a for a in db.scalars(select(Admin).where(Admin.id.in_(admin_ids))).all()} if admin_ids else {}
    # 批量加载创建管理员（系统自动生成时为 None）
    creator_ids = list({r.created_by for r in rows if r.created_by})
    creators = {a.id: a for a in db.scalars(select(Admin).where(Admin.id.in_(creator_ids))).all()} if creator_ids else {}
    # 各状态统计（未使用 / 待使用 / 已使用）
    counts = {s: 0 for s in ("unused", "reserved", "used")}
    for row in db.execute(
        select(SeedInviteCode.status, func.count(SeedInviteCode.id)).group_by(SeedInviteCode.status)
    ).all():
        if row[0] in counts:
            counts[row[0]] = int(row[1])
    return {
        "items": [
            _seed_code_dict(
                r,
                used_by_user=users.get(r.used_by) if r.used_by else None,
                reserved_by_admin=admins.get(r.reserved_by) if r.reserved_by else None,
                created_by_admin=creators.get(r.created_by) if r.created_by else None,
            )
            for r in rows
        ],
        "total": int(total),
        "counts": counts,
        "page": page,
        "page_size": page_size,
    }


def _seed_code_dict(
    s: SeedInviteCode,
    used_by_user: User | None = None,
    reserved_by_admin: Admin | None = None,
    created_by_admin: Admin | None = None,
) -> dict[str, Any]:
    return {
        "id": s.id,
        "code": s.code,
        "note": s.note,
        "batch_no": s.batch_no,
        "status": s.status or ("used" if s.used_by else "unused"),
        "reserved_by": s.reserved_by,
        "reserved_by_username": reserved_by_admin.username if reserved_by_admin else None,
        "reserved_at": to_iso_zh(s.reserved_at) if s.reserved_at else None,
        "created_by": s.created_by,
        "created_by_username": created_by_admin.username if created_by_admin else None,
        "used_by": s.used_by,
        "used_by_username": used_by_user.username if used_by_user else None,
        "used_at": to_iso_zh(s.used_at) if s.used_at else None,
        "created_at": to_iso_zh(s.created_at),
    }


def admin_reserve_seed_codes(
    db: Session,
    admin: Admin,
    count: int = 1,
    note: str | None = None,
    batch_no: str | None = None,
) -> dict[str, Any]:
    """复制 N 个未使用种子并标记为「待使用」。

    用途：管理员线下分发前批量复制种子码，复制的同时打上「待使用」状态 +
    当前管理员信息，其他管理员看到后就不会再重复分发同一批种子。
    """
    if count < 1 or count > 200:
        raise HTTPException(status_code=400, detail="复制数量必须在 1-200 之间")
    note = (note or "").strip()[:100] if note else None
    if not batch_no:
        batch_no = f"reserve-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # FIFO 选取未使用种子（最早生成的先用），避免跳过旧码
    rows = db.scalars(
        select(SeedInviteCode)
        .where(SeedInviteCode.status == "unused")
        .order_by(SeedInviteCode.created_at.asc(), SeedInviteCode.id.asc())
        .limit(count)
    ).all()
    if not rows:
        raise HTTPException(status_code=400, detail="暂无可复制的未使用种子码，请先批量生成")
    if len(rows) < count:
        raise HTTPException(
            status_code=400,
            detail=f"未使用种子码不足，当前仅剩 {len(rows)} 个，请先批量生成",
        )

    codes: list[str] = []
    for s in rows:
        s.status = "reserved"
        s.reserved_by = admin.id
        s.reserved_at = datetime.now()
        if note:
            prefix = f"{s.note}｜" if s.note else ""
            s.note = f"{prefix}待使用：{note}"[:100]
        if not s.batch_no:
            s.batch_no = batch_no
        codes.append(s.code)

    log_admin_action(
        db,
        admin.id,
        "reserve_seed_invite_codes",
        json.dumps({"count": len(codes), "batch_no": batch_no, "note": note, "code_ids": [s.id for s in rows]}, ensure_ascii=False),
        None,
    )
    db.commit()
    return {
        "batch_no": batch_no,
        "count": len(codes),
        "codes": codes,
    }


def admin_release_seed_code(db: Session, admin: Admin, code_id: int) -> dict[str, Any]:
    """释放「待使用」种子码（回到未使用池，供其他管理员复制）。"""
    s = db.get(SeedInviteCode, code_id)
    if not s:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    if s.status != "reserved":
        raise HTTPException(status_code=400, detail="仅「待使用」状态的种子码可释放")
    old_note = s.note
    s.status = "unused"
    s.reserved_by = None
    s.reserved_at = None
    # 去掉追加的「待使用：xxx」备注（保留原始备注）
    if old_note and "｜待使用：" in old_note:
        s.note = old_note.split("｜待使用：", 1)[0]
    log_admin_action(
        db,
        admin.id,
        "release_seed_invite_code",
        json.dumps({"code_id": code_id, "code": s.code}, ensure_ascii=False),
        None,
    )
    db.commit()
    return {"ok": True, "code": s.code, "status": s.status}


def admin_delete_seed_code(db: Session, admin: Admin, code_id: int) -> dict[str, Any]:
    """管理员删除未使用的种子邀请码（已使用的不可删除）。"""
    s = db.get(SeedInviteCode, code_id)
    if not s:
        raise HTTPException(status_code=404, detail=ErrorCode.TARGET_NOT_FOUND)
    if s.status != "unused":
        raise HTTPException(status_code=400, detail="仅「未使用」状态的种子码可删除")
    db.delete(s)
    log_admin_action(
        db,
        admin.id,
        "delete_seed_invite_code",
        json.dumps({"code_id": code_id, "code": s.code}, ensure_ascii=False),
        None,
    )
    db.commit()
    return {"ok": True}
