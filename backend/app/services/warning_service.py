"""警告值系统业务逻辑层。

警告值机制（替代旧的违规次数累计封号）：
- 每次违规：warning_score += violation_base_score（默认 20，可根据 AI severity 调整）
- 签到/发帖审核通过/评论审核通过：warning_score 减少（积极行为奖励）
- 阈值判定：
  - warning_score < warn_threshold（默认 30）：正常
  - warning_score >= warn_threshold：发警告通知
  - warning_score >= temp_ban_threshold（默认 60）：封号 temp_ban_hours 小时
  - warning_score >= perm_ban_threshold（默认 100）：永久封号

所有警告值变化都写入 warning_logs 表，用户可在个人主页查看变动记录。
"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.time_utils import now_utc, to_iso_zh
from app.models import BanRecord, Notification, User, WarningConfig, WarningLog


# ============ 配置管理 ============

def get_warning_config(db: Session) -> WarningConfig:
    """获取警告值配置（单行配置，id=1）。不存在则创建默认配置。"""
    cfg = db.get(WarningConfig, 1)
    if not cfg:
        cfg = WarningConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def update_warning_config(db: Session, payload: dict) -> dict:
    """更新警告值配置（管理员接口）。

    payload 可选字段（仅传需要更新的字段）：
    - warn_threshold: 警告阈值
    - temp_ban_threshold: 临时封号阈值
    - temp_ban_hours: 临时封号时长（小时）
    - perm_ban_threshold: 永久封号阈值
    - violation_base_score: 每次违规基础增加值
    - checkin_reduce: 签到减少值
    - post_reduce: 发帖审核通过减少值
    - comment_reduce: 评论审核通过减少值
    """
    cfg = get_warning_config(db)

    # 校验阈值合理性
    warn_threshold = payload.get("warn_threshold", cfg.warn_threshold)
    temp_ban_threshold = payload.get("temp_ban_threshold", cfg.temp_ban_threshold)
    perm_ban_threshold = payload.get("perm_ban_threshold", cfg.perm_ban_threshold)

    if not (0 <= warn_threshold <= temp_ban_threshold <= perm_ban_threshold):
        raise HTTPException(
            status_code=400,
            detail="阈值关系不合法，需满足 0 ≤ 警告阈值 ≤ 临时封号阈值 ≤ 永久封号阈值",
        )

    # 更新字段
    field_map = {
        "warn_threshold": "warn_threshold",
        "temp_ban_threshold": "temp_ban_threshold",
        "temp_ban_hours": "temp_ban_hours",
        "perm_ban_threshold": "perm_ban_threshold",
        "violation_base_score": "violation_base_score",
        "checkin_reduce": "checkin_reduce",
        "post_reduce": "post_reduce",
        "comment_reduce": "comment_reduce",
    }
    for key, attr in field_map.items():
        if key in payload:
            value = int(payload[key])
            if value < 0:
                raise HTTPException(status_code=400, detail=f"{key} 不能为负数")
            setattr(cfg, attr, value)

    db.commit()
    db.refresh(cfg)
    return _config_dict(cfg)


def _config_dict(cfg: WarningConfig) -> dict:
    """序列化警告值配置。"""
    return {
        "warn_threshold": cfg.warn_threshold,
        "temp_ban_threshold": cfg.temp_ban_threshold,
        "temp_ban_hours": cfg.temp_ban_hours,
        "perm_ban_threshold": cfg.perm_ban_threshold,
        "violation_base_score": cfg.violation_base_score,
        "checkin_reduce": cfg.checkin_reduce,
        "post_reduce": cfg.post_reduce,
        "comment_reduce": cfg.comment_reduce,
        "updated_at": to_iso_zh(cfg.updated_at),
    }


# ============ 警告值增减核心 ============

def add_warning_score(
    db: Session,
    user: User,
    delta: int,
    reason: str,
    source: str = "system",
    related_type: str | None = None,
    related_id: int | None = None,
    operator_id: int | None = None,
) -> int:
    """增减用户警告值，写变动记录，返回变动后的警告值。

    注意：本函数不 commit，由调用方统一提交。
    delta > 0 表示增加（违规），delta < 0 表示减少（积极行为/管理员调整）。
    警告值下限为 0（不会变成负数）。
    """
    old_score = user.warning_score or 0
    new_score = max(0, old_score + delta)
    user.warning_score = new_score

    log = WarningLog(
        user_id=user.id,
        delta=delta,
        score_after=new_score,
        reason=reason[:200],
        source=source,
        related_type=related_type,
        related_id=related_id,
        operator_id=operator_id,
    )
    db.add(log)
    return new_score


# ============ 违规处理 ============

def handle_violation(
    db: Session,
    user: User,
    reason: str,
    content_preview: str = "",
    target_type: str | None = None,
    target_id: int | None = None,
    severity: str = "medium",
) -> dict:
    """处理违规：增加警告值 + 阈值判定 + 发通知/封号。

    返回: {"action": "warn"/"temp_ban"/"perm_ban", "score_after": int, "duration_hours": int}

    通知文案采用警告值机制：
    - 警告：通知内容告知"警告值变为 X，达到 Y 将封号 Z"
    - 封号：通知内容告知"警告值达到 X，账号被封禁 Z"
    """
    cfg = get_warning_config(db)

    # 根据 severity 调整违规增加值
    severity_multiplier = {"low": 0.5, "medium": 1.0, "high": 1.5}.get(severity, 1.0)
    base_score = int(cfg.violation_base_score * severity_multiplier)
    if base_score <= 0:
        base_score = cfg.violation_base_score

    # 累加警告值
    score_after = add_warning_score(
        db, user, base_score, reason=f"内容违规：{reason[:150]}",
        source="violation", related_type=target_type, related_id=target_id,
    )

    # 保留 violation_count 向后兼容（旧字段，仅作统计参考）
    user.violation_count = (user.violation_count or 0) + 1

    # 内容预览片段
    target_label = "帖子" if target_type == "post" else "评论"
    preview_part = f"您发布的{target_label}「{content_preview}」未通过 AI 审核。" if content_preview else f"您的{target_label}未通过 AI 审核。"
    reason_part = f"原因：{reason}。"

    # 通知 1：内容审核未通过（关联到具体帖子/评论）
    notif_content = Notification(
        user_id=user.id,
        title=f"{target_label}审核未通过",
        content=f"{preview_part}{reason_part}请修改后重新发布。",
        type="system",
        reference_type=target_type,
        reference_id=target_id,
    )
    db.add(notif_content)

    # 阈值判定
    if score_after >= cfg.perm_ban_threshold:
        # 永久封号
        action = "perm_ban"
        duration_hours = -1
        user.is_active = False
        user.ban_until = None
        user.ban_reason = f"警告值达到 {score_after}（永久封号阈值 {cfg.perm_ban_threshold}）：{reason[:100]}"

        ban_record = BanRecord(
            user_id=user.id,
            reason=f"警告值达到 {score_after}，触发永久封号：{reason[:150]}",
            duration_hours=0,
            ban_until=None,
            status="active",
            appealable=True,
        )
        db.add(ban_record)

        notif_ban = Notification(
            user_id=user.id,
            title="账号已被永久封禁",
            content=(
                f"您的警告值已达到 {score_after}（永久封号阈值 {cfg.perm_ban_threshold}），"
                f"账号已被永久封禁。如认为有误，可通过申诉功能申请解封。"
                f"\n\n保持良好社区行为（签到、发帖等）可减少警告值。"
            ),
            type="system",
            reference_type=target_type,
            reference_id=target_id,
        )
        db.add(notif_ban)

    elif score_after >= cfg.temp_ban_threshold:
        # 临时封号
        action = "temp_ban"
        duration_hours = cfg.temp_ban_hours
        ban_until = now_utc() + timedelta(hours=duration_hours)
        user.is_active = False
        user.ban_until = ban_until
        user.ban_reason = f"警告值达到 {score_after}（临时封号阈值 {cfg.temp_ban_threshold}）：{reason[:100]}"

        ban_record = BanRecord(
            user_id=user.id,
            reason=f"警告值达到 {score_after}，封号 {duration_hours} 小时：{reason[:150]}",
            duration_hours=duration_hours,
            ban_until=ban_until,
            status="active",
            appealable=True,
        )
        db.add(ban_record)

        if duration_hours < 24:
            duration_display = f"{duration_hours} 小时"
        else:
            duration_display = f"{duration_hours // 24} 天"

        notif_ban = Notification(
            user_id=user.id,
            title=f"账号已被封禁 {duration_display}",
            content=(
                f"您的警告值已达到 {score_after}（临时封号阈值 {cfg.temp_ban_threshold}），"
                f"账号已被封禁 {duration_display}，解封时间：{to_iso_zh(ban_until)}。\n"
                f"达到 {cfg.perm_ban_threshold} 将永久封号。\n\n"
                f"保持良好社区行为（签到、发帖等）可减少警告值。"
            ),
            type="system",
            reference_type=target_type,
            reference_id=target_id,
        )
        db.add(notif_ban)

    elif score_after >= cfg.warn_threshold:
        # 仅警告
        action = "warn"
        duration_hours = 0
        user.ban_until = None
        user.ban_reason = None

        notif_ban = Notification(
            user_id=user.id,
            title="内容违规警告",
            content=(
                f"您的警告值已达到 {score_after}。\n"
                f"达到 {cfg.temp_ban_threshold} 将被封号 {cfg.temp_ban_hours} 小时，"
                f"达到 {cfg.perm_ban_threshold} 将被永久封号。\n\n"
                f"保持良好社区行为（签到、发帖等）可减少警告值，请遵守社区规范。"
            ),
            type="system",
            reference_type=target_type,
            reference_id=target_id,
        )
        db.add(notif_ban)

    else:
        # 未达警告阈值，仅记录（不再发额外通知，审核未通过通知已发）
        action = "record"
        duration_hours = 0

    return {
        "action": action,
        "score_after": score_after,
        "duration_hours": duration_hours,
    }


# ============ 积极行为减少警告值 ============

def reduce_on_checkin(db: Session, user: User) -> None:
    """签到成功后减少警告值（不 commit，由调用方提交）。"""
    if (user.warning_score or 0) <= 0:
        return  # 警告值为 0，不减
    cfg = get_warning_config(db)
    if cfg.checkin_reduce <= 0:
        return
    add_warning_score(
        db, user, -cfg.checkin_reduce,
        reason="每日签到奖励，警告值减少",
        source="checkin",
    )


def reduce_on_post_approved(db: Session, user: User, post_id: int) -> None:
    """帖子审核通过后减少警告值（不 commit，由调用方提交）。"""
    if (user.warning_score or 0) <= 0:
        return
    cfg = get_warning_config(db)
    if cfg.post_reduce <= 0:
        return
    add_warning_score(
        db, user, -cfg.post_reduce,
        reason="帖子审核通过奖励，警告值减少",
        source="post",
        related_type="post",
        related_id=post_id,
    )


def reduce_on_comment_approved(db: Session, user: User, comment_id: int) -> None:
    """评论审核通过后减少警告值（不 commit，由调用方提交）。"""
    if (user.warning_score or 0) <= 0:
        return
    cfg = get_warning_config(db)
    if cfg.comment_reduce <= 0:
        return
    add_warning_score(
        db, user, -cfg.comment_reduce,
        reason="评论审核通过奖励，警告值减少",
        source="comment",
        related_type="comment",
        related_id=comment_id,
    )


# ============ 管理员手动调整 ============

def admin_adjust_warning(
    db: Session,
    user_id: int,
    delta: int,
    reason: str,
    operator_id: int,
) -> dict:
    """管理员手动调整用户警告值。

    Args:
        delta: 正数增加，负数减少
        reason: 调整原因
        operator_id: 管理员 ID
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if delta == 0:
        raise HTTPException(status_code=400, detail="调整值不能为 0")

    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="请填写调整原因")

    old_score = user.warning_score or 0
    new_score = add_warning_score(
        db, user, delta,
        reason=f"管理员调整：{reason[:150]}",
        source="admin_adjust",
        operator_id=operator_id,
    )

    # 检查是否触发封号
    cfg = get_warning_config(db)
    triggered_ban = False
    if delta > 0 and new_score >= cfg.perm_ban_threshold and user.is_active:
        # 触发永久封号
        user.is_active = False
        user.ban_until = None
        user.ban_reason = f"管理员调整警告值至 {new_score}，触发永久封号"
        ban_record = BanRecord(
            user_id=user_id,
            reason=f"管理员调整警告值至 {new_score}，触发永久封号",
            duration_hours=0,
            ban_until=None,
            status="active",
            appealable=True,
        )
        db.add(ban_record)
        triggered_ban = True
    elif delta > 0 and new_score >= cfg.temp_ban_threshold and user.is_active:
        # 触发临时封号
        ban_until = now_utc() + timedelta(hours=cfg.temp_ban_hours)
        user.is_active = False
        user.ban_until = ban_until
        user.ban_reason = f"管理员调整警告值至 {new_score}，触发临时封号"
        ban_record = BanRecord(
            user_id=user_id,
            reason=f"管理员调整警告值至 {new_score}，封号 {cfg.temp_ban_hours} 小时",
            duration_hours=cfg.temp_ban_hours,
            ban_until=ban_until,
            status="active",
            appealable=True,
        )
        db.add(ban_record)
        triggered_ban = True

    db.commit()
    db.refresh(user)
    return {
        "user_id": user_id,
        "old_score": old_score,
        "new_score": new_score,
        "triggered_ban": triggered_ban,
    }


# ============ 警告值记录查询 ============

def _warning_log_dict(log: WarningLog) -> dict:
    """序列化警告值变动记录。"""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "delta": log.delta,
        "score_after": log.score_after,
        "reason": log.reason,
        "source": log.source,
        "related_type": log.related_type,
        "related_id": log.related_id,
        "operator_id": log.operator_id,
        "created_at": to_iso_zh(log.created_at),
    }


def list_user_warning_logs(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询用户警告值变动记录（分页）。"""
    query = select(WarningLog).where(WarningLog.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    rows = db.scalars(
        query.order_by(desc(WarningLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": [_warning_log_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_user_warning_status(user: User, db: Session) -> dict:
    """获取用户警告值状态（用于个人主页展示）。"""
    cfg = get_warning_config(db)
    score = user.warning_score or 0

    # 判定当前等级
    if score >= cfg.perm_ban_threshold:
        level = "danger"  # 危险（即将永久封号）
    elif score >= cfg.temp_ban_threshold:
        level = "ban"  # 封号级
    elif score >= cfg.warn_threshold:
        level = "warn"  # 警告级
    else:
        level = "normal"  # 正常

    return {
        "score": score,
        "level": level,
        "warn_threshold": cfg.warn_threshold,
        "temp_ban_threshold": cfg.temp_ban_threshold,
        "temp_ban_hours": cfg.temp_ban_hours,
        "perm_ban_threshold": cfg.perm_ban_threshold,
        "next_threshold": (
            cfg.perm_ban_threshold if score >= cfg.temp_ban_threshold
            else cfg.temp_ban_threshold if score >= cfg.warn_threshold
            else cfg.warn_threshold
        ),
        "next_action": (
            "永久封号" if score >= cfg.temp_ban_threshold
            else f"封号 {cfg.temp_ban_hours} 小时" if score >= cfg.warn_threshold
            else "警告通知"
        ),
        "reduce_hint": (
            f"签到减少 {cfg.checkin_reduce}，发帖审核通过减少 {cfg.post_reduce}，评论审核通过减少 {cfg.comment_reduce}"
        ),
    }
