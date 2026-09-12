"""接单大厅（项目 2）接口。

用户端：
- 接单大厅列表 / 我的任务
- 发布任务（悬赏交易币，发布即托管）
- 接单 / 交付 / 验收（抽成）/ 取消 / 曝光
- 交易币钱包 / 充值申请 / 提现申请

后台：
- 任务管理（查看 / 下架）
- 充值审核 / 提现审核
- 兑换汇率 / 抽成 / 最低提现 / 曝光价配置
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user, current_user_optional
from app.core.database import get_db
from app.core.time_utils import now_utc, to_iso_zh
from app.models import (
    Admin,
    LotteryAccount,
    OrderAiMessage,
    OrderAiSession,
    OrderReview,
    OrderTask,
    User,
    Wallet,
    WalletTransaction,
    WithdrawRequest,
)
from app.schemas.common import ok
from app.services import order_ai_service, order_service as os, settings_service

router = APIRouter(prefix="/orders", tags=["orders"])
admin_router = APIRouter(prefix="/admin/orders", tags=["orders-admin"])

CATEGORIES = [
    "代取快递",
    "代买代送",
    "找人办事",
    "学习互助",
    "组队开黑",
    "情感求助",
    "跑腿代领",
    "其他",
]


# ==================== 订单 AI（豆包式对话助手） ====================
class AiChatPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, description="用户消息")


@router.post("/ai/chat")
def order_ai_chat(
    payload: AiChatPayload,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """订单 AI 对话：帮用户找单/发单/看钱包。返回本次新增消息（含工具卡片）。"""
    try:
        return ok(order_ai_service.chat(db, user, payload.text))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务异常：{exc}") from None


@router.get("/ai/history")
def order_ai_history(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok({"history": order_ai_service.load_history(db, user.id),
               "state": order_ai_service.state_to_dict(db, user.id)})


@router.get("/ai/state")
def order_ai_state(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(order_ai_service.state_to_dict(db, user.id))


# ==================== 用户端：任务 ====================
@router.get("")
def list_tasks(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User | None = Depends(current_user_optional),
) -> dict:
    """接单大厅：曝光度高的在前，再看最新。（公开浏览，未登录也可看）"""
    base = select(OrderTask)
    if status:
        base = base.where(OrderTask.status == status)
    if category:
        base = base.where(OrderTask.category == category)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(desc(OrderTask.boost), desc(OrderTask.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    uid = user.id if user else None
    return ok(
        {
            "categories": CATEGORIES,
            "items": [os.task_dict(db, t, uid) for t in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("")
def create_task(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    category = str(payload.get("category", "其他"))
    reward = int(payload.get("reward", 0))

    if not title or not content:
        raise HTTPException(status_code=400, detail="标题和描述不能为空")
    if len(title) > 64 or len(content) > 2000:
        raise HTTPException(status_code=400, detail="标题最长 64 字，描述最长 2000 字")
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="分类不合法")
    if reward <= 0:
        raise HTTPException(status_code=400, detail="请设置悬赏交易币（正整数）")

    # 发布即托管：从钱包划出悬赏到 escrow
    try:
        os.debit(db, user, reward, "task_publish", ref_id="order-publish", description=f"发布求助「{title}」托管悬赏")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    task = OrderTask(
        user_id=user.id,
        title=title,
        content=content,
        category=category,
        reward=reward,
        escrow=reward,
        status="open",
    )
    db.add(task)
    db.flush()
    db.commit()
    db.refresh(task)
    return ok(os.task_dict(db, task, user.id))


@router.get("/my")
def my_tasks(
    role: str = Query(default="all", pattern="^(all|posted|taken)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    base = select(OrderTask)
    if role == "posted":
        base = base.where(OrderTask.user_id == user.id)
    elif role == "taken":
        base = base.where(OrderTask.assignee_id == user.id)
    else:
        base = base.where((OrderTask.user_id == user.id) | (OrderTask.assignee_id == user.id))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(OrderTask.id)).offset((page - 1) * page_size).limit(page_size)).all()
    return ok(
        {
            "items": [os.task_dict(db, t, user.id) for t in rows],
            "total": total,
        }
    )


@router.get("/{task_id}")
def task_detail(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ok(os.task_dict(db, t, user.id))


@router.post("/{task_id}/accept")
def accept_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id == user.id:
        raise HTTPException(status_code=400, detail="不能接自己的单")
    if t.status != "open":
        raise HTTPException(status_code=400, detail="任务已被接走或已结束")
    t.status = "in_progress"
    t.assignee_id = user.id
    db.commit()
    db.refresh(t)
    return ok(os.task_dict(db, t, user.id))


@router.post("/{task_id}/deliver")
def deliver_task(task_id: int, payload: dict = {}, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.assignee_id != user.id:
        raise HTTPException(status_code=403, detail="只有接单人可交付")
    if t.status != "in_progress":
        raise HTTPException(status_code=400, detail="当前状态不可交付")
    t.status = "done"
    t.deliver_note = str(payload.get("note", ""))[:500]
    db.commit()
    db.refresh(t)
    return ok(os.task_dict(db, t, user.id))


@router.post("/{task_id}/confirm")
def confirm_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """发布者验收：把托管悬赏（扣除抽成）发放给接单人，并记录抽成。"""
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id:
        raise HTTPException(status_code=403, detail="只有发布者可验收")
    if t.status != "done":
        raise HTTPException(status_code=400, detail="请先让接单人交付")
    if not t.assignee_id:
        raise HTTPException(status_code=400, detail="缺少接单人")

    comm = os._commission(db)
    payout = t.escrow * (100 - comm) // 100 if comm < 100 else 0
    platform_cut = t.escrow - payout
    assignee = db.get(User, t.assignee_id)

    os.credit(
        db,
        assignee,
        payout,
        "task_reward",
        ref_id=f"order-{t.id}",
        description=f"完成求助「{t.title}」，获得悬赏 {payout} 交易币",
    )
    t.status = "completed"
    t.completed_at = now_utc()
    t.escrow = 0
    if platform_cut > 0:
        os._ledger(
            db,
            user.id,
            -0,
            "task_commission",
            ref_id=f"order-{t.id}",
            description=f"平台抽成 {platform_cut} 交易币",
            status="completed",
            balance_after=db.get(Wallet, user.id).balance if db.get(Wallet, user.id) else 0,
        )
    db.commit()
    db.refresh(t)
    # 回传抽成信息，便于前端提示
    data = os.task_dict(db, t, user.id)
    data["platform_cut"] = platform_cut
    return ok(data)


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id:
        raise HTTPException(status_code=403, detail="只有发布者可取消")
    if t.status != "open":
        raise HTTPException(status_code=400, detail="任务进行中不可取消")
    # 退回托管悬赏
    if t.escrow > 0:
        os.credit(db, user, t.escrow, "refund", ref_id=f"order-{t.id}", description=f"取消求助「{t.title}」，退回悬赏 {t.escrow} 交易币")
    t.status = "cancelled"
    t.escrow = 0
    db.commit()
    db.refresh(t)
    return ok(os.task_dict(db, t, user.id))


@router.post("/{task_id}/boost")
def boost_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """花钱买曝光：提升任务在接单大厅的排序权重。"""
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.user_id != user.id:
        raise HTTPException(status_code=403, detail="只有发布者可购买曝光")
    price = os._boost_price(db)
    try:
        os.debit(db, user, price, "boost", ref_id=f"order-{t.id}", description=f"购买「{t.title}」曝光 ×1")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    t.boost += 1
    db.commit()
    db.refresh(t)
    return ok(os.task_dict(db, t, user.id))


# ==================== 用户端：钱包 ====================
@router.get("/wallet/me")
def wallet_me(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    from sqlalchemy import select as _select

    w = os.get_wallet(db, user.id)
    acc = db.scalar(_select(LotteryAccount).where(LotteryAccount.user_id == user.id))
    txs = db.scalars(
        select(WalletTransaction).where(WalletTransaction.user_id == user.id).order_by(desc(WalletTransaction.id)).limit(100)
    ).all()
    return ok(
        {
            "balance": w.balance,
            "frozen": w.frozen,
            "rate": os._rate(db),
            "commission_rate": os._commission(db),
            "withdraw_min_cents": os._withdraw_min_cents(db),
            "boost_price": os._boost_price(db),
            "ticket_qty": acc.ticket_qty if acc else 0,
            "transactions": [
                {
                    "id": x.id,
                    "amount": x.amount,
                    "balance_after": x.balance_after,
                    "type": x.type,
                    "status": x.status,
                    "description": x.description,
                    "created_at": to_iso_zh(x.created_at),
                }
                for x in txs
            ],
        }
    )


@router.post("/wallet/recharge")
def recharge_apply(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """充值申请：金额（元）按后台汇率换交易币，生成待审核充值单。

    说明：生产接入真实支付网关后由回调确认到账；当前版本为后台人工审核后到账。
    """
    raw = payload.get("fuel_amount")
    try:
        yuan = round(float(raw), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="充值金额不合法") from None
    if yuan <= 0:
        raise HTTPException(status_code=400, detail="充值金额需大于 0")
    if yuan > 5000:
        raise HTTPException(status_code=400, detail="单笔充值不超过 5000 元")
    cents = int(round(yuan * 100))
    bin_ = cents // 100 * os._rate(db)
    os._ledger(
        db,
        user.id,
        bin_,
        "recharge",
        ref_id=f"recharge-{cents}",
        description=f"充值 ¥{yuan:g}（等待审核到账 {bin_} 交易币）",
        status="pending",
        balance_after=os.get_wallet(db, user.id).balance,
    )
    db.commit()
    return ok({"cents": cents, "bin": bin_, "rate": os._rate(db), "status": "pending"})


@router.post("/wallet/withdraw")
def withdraw_apply(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """提现申请：交易币按汇率转元，最低后台配置金额（默认 6 元）。"""
    raw = payload.get("fuel_amount")
    try:
        bin_ = int(float(raw))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="提现交易币数量不合法") from None
    rate = os._rate(db)
    if bin_ <= 0:
        raise HTTPException(status_code=400, detail="提现数量需大于 0")
    cents = bin_ * 100 // rate  # 交易币 → 分（向下取整）
    if cents < os._withdraw_min_cents(db):
        raise HTTPException(status_code=400, detail=f"最低可提现 {os._withdraw_min_cents(db) / 100:g} 元")
    payee = str(payload.get("payee", "")).strip()[:120]
    if not payee:
        raise HTTPException(status_code=400, detail="请填写收款账号（支付宝/微信）")

    w = os.get_wallet(db, user.id)
    if w.balance < bin_:
        raise HTTPException(status_code=400, detail="交易币不足")
    w.balance -= bin_
    w.frozen += bin_
    os._ledger(
        db,
        user.id,
        -bin_,
        "withdraw",
        ref_id=f"wd-{bin_}",
        description=f"提现申请 {bin_} 交易币（冻结中）",
        status="pending",
        balance_after=w.balance,
    )
    req = WithdrawRequest(
        user_id=user.id,
        amount_bin=bin_,
        amount_cents=cents,
        payee=payee,
        status="pending",
    )
    db.add(req)
    db.commit()
    return ok(
        {
            "id": req.id,
            "amount_bin": bin_,
            "amount_cents": cents,
            "status": "pending",
        }
    )


# ==================== 后台：任务管理 ====================
@admin_router.get("")
def admin_list_tasks(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(OrderTask)
    if status:
        base = base.where(OrderTask.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(OrderTask.id)).offset((page - 1) * page_size).limit(page_size)).all()
    return ok({"items": [os.task_dict(db, t, None) for t in rows], "total": total})


@admin_router.post("/{task_id}/cancel")
def admin_cancel_task(task_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    t = db.get(OrderTask, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status not in ("open", "in_progress"):
        raise HTTPException(status_code=400, detail="该状态不可下架")
    if t.escrow > 0:
        owner = db.get(User, t.user_id)
        os.credit(db, owner, t.escrow, "refund", ref_id=f"order-{t.id}", description=f"后台下架求助「{t.title}」，退回悬赏 {t.escrow} 交易币")
    t.status = "cancelled"
    t.escrow = 0
    db.commit()
    return ok(os.task_dict(db, t, None))


# ==================== 后台：交易审核 ====================
@admin_router.post("/recharge/{tx_id}/approve")
def admin_approve_recharge(tx_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    tx = db.get(WalletTransaction, tx_id)
    if not tx or tx.type != "recharge" or tx.status != "pending":
        raise HTTPException(status_code=400, detail="充值单不存在或不可审核")
    w = os.get_wallet(db, tx.user_id)
    w.balance += tx.amount
    tx.status = "completed"
    tx.balance_after = w.balance
    tx.description = tx.description.replace("等待审核到账", "已到账")
    db.commit()
    return ok({"balance": w.balance})


@admin_router.post("/recharge/{tx_id}/reject")
def admin_reject_recharge(tx_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    tx = db.get(WalletTransaction, tx_id)
    if not tx or tx.type != "recharge" or tx.status != "pending":
        raise HTTPException(status_code=400, detail="充值单不存在或不可审核")
    tx.status = "rejected"
    db.commit()
    return ok({"status": "rejected"})


@admin_router.get("/recharges")
def admin_list_recharges(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(WalletTransaction).where(WalletTransaction.type == "recharge")
    if status:
        base = base.where(WalletTransaction.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(WalletTransaction.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for tx in rows:
        u = db.get(User, tx.user_id)
        items.append(
            {
                "id": tx.id,
                "user_id": tx.user_id,
                "user_name": u.nickname if u else "",
                "amount": tx.amount,
                "status": tx.status,
                "description": tx.description,
                "created_at": to_iso_zh(tx.created_at),
            }
        )
    return ok({"items": items, "total": total})


@admin_router.post("/withdraw/{req_id}/approve")
def admin_approve_withdraw(req_id: int, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    req = db.get(WithdrawRequest, req_id)
    if not req or req.status != "pending":
        raise HTTPException(status_code=400, detail="提现单不存在或不可审核")
    w = os.get_wallet(db, req.user_id)
    if w.frozen < req.amount_bin:
        raise HTTPException(status_code=400, detail="冻结余额不足，无法打款")
    w.frozen -= req.amount_bin
    os._ledger(db, req.user_id, -0, "withdraw_paid", ref_id=f"wd-{req.id}", description=f"提现 ¥{req.amount_cents / 100:g} 已打款", status="completed", balance_after=w.balance)
    req.status = "completed"
    req.completed_at = now_utc()
    db.commit()
    return ok({"status": "completed"})


@admin_router.post("/withdraw/{req_id}/reject")
def admin_reject_withdraw(req_id: int, payload: dict = {}, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    req = db.get(WithdrawRequest, req_id)
    if not req or req.status != "pending":
        raise HTTPException(status_code=400, detail="提现单不存在或不可审核")
    w = os.get_wallet(db, req.user_id)
    # 退回冻结到余额
    w.frozen -= req.amount_bin
    w.balance += req.amount_bin
    os._ledger(db, req.user_id, req.amount_bin, "withdraw_refund", ref_id=f"wd-{req.id}", description=f"提现被驳回，退回 {req.amount_bin} 交易币", status="completed", balance_after=w.balance)
    req.status = "rejected"
    req.reject_reason = str(payload.get("reason", ""))[:255]
    db.commit()
    return ok({"status": "rejected"})


@admin_router.get("/withdraws")
def admin_list_withdraws(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    base = select(WithdrawRequest)
    if status:
        base = base.where(WithdrawRequest.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(WithdrawRequest.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for r in rows:
        u = db.get(User, r.user_id)
        items.append(
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": u.nickname if u else "",
                "amount_bin": r.amount_bin,
                "amount_cents": r.amount_cents,
                "payee": r.payee,
                "status": r.status,
                "reject_reason": r.reject_reason,
                "created_at": to_iso_zh(r.created_at),
            }
        )
    return ok({"items": items, "total": total})


# ==================== 后台：配置 ====================
@admin_router.post("/settings")
def admin_set_settings(payload: dict, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    from app.services import settings_service

    mapping = {
        "task_exchange_rate": "task_exchange_rate",
        "task_commission_rate": "task_commission_rate",
        "task_withdraw_min_cents": "task_withdraw_min_cents",
        "task_boost_price": "task_boost_price",
    }
    updates = {}
    for key, db_key in mapping.items():
        if key in payload and payload[key] is not None:
            updates[db_key] = str(int(payload[key]))
    if updates:
        settings_service.set_many(db, updates)
    return ok(
        {
            "rate": os._rate(db),
            "commission_rate": os._commission(db),
            "withdraw_min_cents": os._withdraw_min_cents(db),
            "boost_price": os._boost_price(db),
        }
    )


@admin_router.get("/settings")
def admin_get_settings(db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    return ok(
        {
            "rate": os._rate(db),
            "commission_rate": os._commission(db),
            "withdraw_min_cents": os._withdraw_min_cents(db),
            "boost_price": os._boost_price(db),
        }
    )


# ==================== 后台：订单 AI 管理 ====================
@admin_router.get("/ai/sessions")
def admin_list_order_ai_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    """订单 AI 会话列表（每用户一行 + 消息数 + 额度）。"""
    base = select(OrderAiSession)
    if keyword:
        kw = f"%{keyword}%"
        base = base.where(
            (OrderAiSession.user_id.in_(
                select(User.id).where((User.nickname.like(kw)) | (User.username.like(kw)))
            ))
        )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(OrderAiSession.id)).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for s in rows:
        user = db.get(User, s.user_id)
        msg_count = db.scalar(
            select(func.count()).select_from(OrderAiMessage.__table__).where(OrderAiMessage.session_id == s.id)
        ) or 0
        items.append(
            {
                "user_id": s.user_id,
                "user_name": (user.nickname if user else "") or (user.username if user else ""),
                "daily_token": s.daily_token or 0,
                "daily_token_limit": settings_service.get_int(db, "order_ai_daily_token_limit", 200000),
                "message_count": msg_count,
                "daily_date": s.daily_date,
                "created_at": to_iso_zh(s.created_at),
                "updated_at": to_iso_zh(s.updated_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@admin_router.get("/ai/sessions/{user_id}/messages")
def admin_order_ai_messages(
    user_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _admin: Admin = Depends(admin_user),
) -> dict:
    from app.core.time_utils import to_iso_zh

    s = db.scalar(select(OrderAiSession).where(OrderAiSession.user_id == user_id))
    user = db.get(User, user_id)
    if not s:
        return ok({"role": (user.nickname if user else str(user_id)), "messages": []})
    rows = db.scalars(
        select(OrderAiMessage).where(OrderAiMessage.session_id == s.id).order_by(desc(OrderAiMessage.id)).limit(limit)
    ).all()
    messages = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "meta": m.meta or None,
            "created_at": to_iso_zh(m.created_at),
        }
        for m in reversed(rows)
    ]
    return ok({"role": (user.nickname if user else str(user_id)), "messages": messages})


@admin_router.get("/ai/settings")
def admin_get_order_ai_settings(db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    return ok(
        {
            "enabled": settings_service.get_bool(db, "order_ai_enabled", False),
            "daily_token_limit": settings_service.get_int(db, "order_ai_daily_token_limit", 200000),
            "context_messages": settings_service.get_int(db, "order_ai_context_messages", 12),
        }
    )


@admin_router.post("/ai/settings")
def admin_set_order_ai_settings(payload: dict, db: Session = Depends(get_db), _admin: Admin = Depends(admin_user)) -> dict:
    updates = {}
    if payload.get("enabled") is not None:
        updates["order_ai_enabled"] = "1" if bool(payload["enabled"]) else "0"
    if payload.get("daily_token_limit") is not None:
        v = int(payload.get("daily_token_limit"))
        updates["order_ai_daily_token_limit"] = str(max(0, v))
    if payload.get("context_messages") is not None:
        v = int(payload.get("context_messages"))
        updates["order_ai_context_messages"] = str(max(1, v))
    if updates:
        settings_service.set_many(db, updates)
    return ok(
        {
            "enabled": settings_service.get_bool(db, "order_ai_enabled", False),
            "daily_token_limit": settings_service.get_int(db, "order_ai_daily_token_limit", 200000),
            "context_messages": settings_service.get_int(db, "order_ai_context_messages", 12),
        }
    )