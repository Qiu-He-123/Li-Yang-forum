"""用户操作审计日志服务。

每次调用既写文件日志（loguru，方便排查错误），也持久化到 operation_logs 表
（方便后台查询和统计）。日志失败绝不阻断主业务流程。
"""

from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models import OperationLog


def log_user_action(
    db: Session,
    user_id: int | None,
    action: str,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """记录用户操作。

    Args:
        db: SQLAlchemy Session，与业务同事务提交。
        user_id: 用户 id，未登录场景为 None。
        action: 动作名，如 login / create_post / like_post。
        detail: 详情文本，建议 JSON 字符串。
        ip: 客户端 IP，可选。

    注意：本函数只 add 不 commit，由调用方在业务提交时一并提交。
    T7-14：ip 为 None 时记录 "unknown"，避免 operation_logs.ip 列出现 NULL。
    """
    # T7-14：ip 为 None 时记录 unknown，保证 ip 列非 NULL
    safe_ip = ip or "unknown"
    try:
        db.add(OperationLog(user_id=user_id, action=action, detail=detail, ip=safe_ip))
    except Exception as exc:  # 日志失败不影响业务
        logger.warning("log_user_action add failed: action={} err={}", action, exc)

    # 文件日志独立写一份，立即落盘，方便排查
    logger.info(
        "[USER_OP] user={} action={} detail={} ip={}",
        user_id,
        action,
        detail[:200] if detail else "",
        safe_ip,
    )


def log_admin_action(
    db: Session,
    admin_id: int | None,
    action: str,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """记录管理员操作。

    与 log_user_action 区分：写入 admin_id 字段（L7 修复），方便后台追溯。
    本函数只 add 不 commit，由调用方在业务提交时一并提交。
    T7-14：ip 为 None 时记录 "unknown"。
    """
    safe_ip = ip or "unknown"
    try:
        db.add(OperationLog(admin_id=admin_id, action=action, detail=detail, ip=safe_ip))
    except Exception as exc:  # 日志失败不影响业务
        logger.warning("log_admin_action add failed: action={} err={}", action, exc)

    logger.info(
        "[ADMIN_OP] admin={} action={} detail={} ip={}",
        admin_id,
        action,
        detail[:200] if detail else "",
        safe_ip,
    )


def log_error(action: str, error: Exception | str, context: dict[str, Any] | None = None) -> None:
    """记录错误日志，仅写文件，不入库。"""
    logger.error("[ERROR] action={} err={} ctx={}", action, error, context or {})
