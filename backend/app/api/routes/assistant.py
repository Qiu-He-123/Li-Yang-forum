"""同伴圈（全局浮窗）AI 助手日志接口。

全局 AI 助手（AiAssistant.vue）是纯前端规则引擎，不调用后端对话接口；
这里提供 best-effort 的对话埋点日志 + 后台日志查询/统计。
"""
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import admin_user, current_user
from app.core.database import get_db
from app.core.time_utils import to_iso_zh
from app.models import Admin, AiChatLog, User
from app.schemas.common import ok

router = APIRouter(prefix="/assistant", tags=["assistant"])
admin_router = APIRouter(prefix="/admin/assistant", tags=["assistant-admin"])


@router.post("/log")
def assistant_log(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """写入一条 AI 助手对话埋点日志（best-effort：任何异常静默，不影响对话体验）。"""
    try:
        db.add(
            AiChatLog(
                user_id=user.id,
                input=str(payload.get("input", ""))[:255],
                intent=str(payload.get("intent", ""))[:100],
                reply=str(payload.get("reply", "")) or "",
                action=str(payload.get("action", ""))[:50],
                hit=bool(payload.get("hit", False)),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    return ok()


@admin_router.get("/logs")
def admin_list_assistant_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    hit: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(AiChatLog)
    if keyword:
        kw = f"%{keyword}%"
        base = base.where(
            (AiChatLog.input.like(kw))
            | (AiChatLog.intent.like(kw))
            | (AiChatLog.reply.like(kw))
            | (AiChatLog.user_id.in_(select(User.id).where((User.nickname.like(kw)) | (User.username.like(kw))))
            )
        )
    if hit is not None:
        base = base.where(AiChatLog.hit == hit)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(AiChatLog.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for row in rows:
        u = db.get(User, row.user_id)
        items.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "user_name": (u.nickname if u else "") or (u.username if u else ""),
                "input": row.input,
                "intent": row.intent,
                "reply": row.reply,
                "action": row.action,
                "hit": bool(row.hit),
                "created_at": to_iso_zh(row.created_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@admin_router.get("/stats")
def admin_assistant_stats(db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    total = db.scalar(select(func.count()).select_from(AiChatLog)) or 0
    hits = db.scalar(
        select(func.count()).select_from(AiChatLog).where(AiChatLog.hit == True)  # noqa: E712
    ) or 0
    hit_rate = round(hits / total, 4) if total else 0
    per_day_rows = db.execute(
        select(func.date(AiChatLog.created_at).label("day"), func.count())
        .group_by("day")
        .order_by(func.date(AiChatLog.created_at).desc())
        .limit(30)
    ).all()
    per_day = [{"date": str(d), "count": c} for d, c in reversed(per_day_rows)]
    return ok({"total": total, "hits": hits, "hit_rate": hit_rate, "per_day": per_day})


@admin_router.delete("/logs/{log_id}")
def admin_delete_assistant_log(log_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    row = db.get(AiChatLog, log_id)
    if not row:
        raise HTTPException(status_code=404, detail="日志不存在")
    db.delete(row)
    db.commit()
    return ok()