"""订单 AI（接单大厅 · 豆包式对话助手）服务。

能力：用户用自然语言让 AI 帮忙「找单 / 发单 / 看钱包」。
- 复用宠物 AI 的 DeepSeek 账号（pet_ai_* key/model/base_url）
- 工具调用：搜索任务 / 看钱包余额 / 整理发单 / 接单
- 敏感操作（发单、接单）不真正执行，而是返回「确认卡片」(action=confirm)，
  由前端二次确认后再走既有业务接口，避免 AI 误操作 / 误扣款
- 每次调用消耗 token 计入每日上限，达到上限后拒绝并提示
- 聊天记录跨会话保留（order_ai_messages 表）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import OrderAiMessage, OrderAiSession, OrderTask, User, Wallet
from app.services import deepseek_client, order_service, settings_service

# 单轮对话最多工具调用轮次（防止 AI 无限调工具）
MAX_TOOL_ROUNDS = 3
# 尚未执行写操作前，单次返回任务卡片的条数上限
SEARCH_LIMIT = 6

# 订单分类（与 orders.py CATEGORIES 保持一致）
ORDER_CATEGORIES = [
    "代取快递", "代买代送", "找人办事", "学习互助",
    "组队开黑", "情感求助", "跑腿代领", "其他",
]


# ==================== 会话 / 额度 ====================


def get_session(db: Session, user_id: int) -> OrderAiSession:
    row = db.scalar(select(OrderAiSession).where(OrderAiSession.user_id == user_id))
    if not row:
        row = OrderAiSession(user_id=user_id)
        db.add(row)
        db.flush()
    _roll_daily(row)
    return row


def _roll_daily(s: OrderAiSession) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    if s.daily_date != today:
        s.daily_date = today
        s.daily_token = 0


def state_to_dict(db: Session, user_id: int) -> dict[str, Any]:
    """订单 AI 状态：本日 token / 上限 / 剩余。"""
    s = get_session(db, user_id)
    limit = settings_service.get_int(db, "order_ai_daily_token_limit", 200000)
    remaining = max(0, limit - (s.daily_token or 0)) if limit > 0 else None
    return {
        "daily_token": s.daily_token or 0,
        "daily_token_limit": limit,
        "remaining_token": remaining,
        "enabled": settings_service.get_bool(db, "order_ai_enabled", False),
    }


# ==================== 历史 ====================


def load_history(db: Session, user_id: int, limit: int = 40) -> list[dict[str, Any]]:
    """会话历史（仅前端展示用，含工具卡片 meta）。"""
    s = get_session(db, user_id)
    rows = db.scalars(
        select(OrderAiMessage)
        .where(OrderAiMessage.session_id == s.id)
        .order_by(OrderAiMessage.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "meta": m.meta or None,
            "created_at": m.created_at,
        }
        for m in reversed(rows)
    ]


def _context_messages(db: Session, user_id: int) -> list[dict[str, str]]:
    """构造发给 DeepSeek 的最近上下文（user/assistant 原文，不含 tool 卡片）。"""
    n = settings_service.get_int(db, "order_ai_context_messages", 12)
    s = get_session(db, user_id)
    rows = db.scalars(
        select(OrderAiMessage)
        .where(OrderAiMessage.session_id == s.id, OrderAiMessage.role.in_(["user", "assistant"]))
        .order_by(OrderAiMessage.id.desc())
        .limit(max(1, n))
    ).all()
    msgs = []
    for m in reversed(rows):
        msgs.append({"role": m.role, "content": m.content})
    return msgs


def _save(db: Session, user_id: int, session_id: int, role: str, content: str, meta: dict | None = None) -> OrderAiMessage:
    m = OrderAiMessage(user_id=user_id, session_id=session_id, role=role, content=content, meta=meta)
    db.add(m)
    return m


# ==================== 工具定义 ====================

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "在接单大厅搜索当前可接的任务/求助。用户想找单、赚钱、看看有没有合适的任务时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "分类，可留空表示全部。可选值：" + "/".join(ORDER_CATEGORIES) + "。用户没提分类时留空。"},
                    "keyword": {"type": "string", "description": "关键词，匹配标题/描述，可留空"},
                    "limit": {"type": "integer", "description": "返回条数（1-6），默认 6"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_balance",
            "description": "查询用户当前交易币钱包余额（可用/冻结）。用户问余额、还剩多少币、够不够发单时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_task",
            "description": "整理一份「发单/找人办事/求助」的草稿（标题/描述/分类/悬赏交易币）。注意：此工具只生成草稿并返还给用户确认，不会真正发布扣款。用户想发单、发布任务、悬赏找人帮忙时调用。用户若只修改草稿的某几项（如改标题），只传被改的字段，其余保持原样，不要重写。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务标题（一句话，不超过 64 字）"},
                    "content": {"type": "string", "description": "详细描述（做什么、要求、时长等，不超过 2000 字）"},
                    "category": {"type": "string", "description": "分类。可选值：" + "/".join(ORDER_CATEGORIES) + "，根据内容选最贴切的。"},
                    "reward": {"type": "integer", "description": "悬赏交易币（正整数）。默认 10，用户未说时用 10。"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "accept_task",
            "description": "用户想接某个单。搜索到任务后，用这个工具把要接的任务 id 交给前端，前端弹确认后引导接单。此工具不真正接单。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "要接的任务 id"},
                },
                "required": ["task_id"],
            },
        },
    },
]

TOOL_CALLBACK_PROMPT = (
    "以上是工具执行结果。请根据结果用简短、自然的口语回复用户，"
    "引导用户点击上方的操作卡片（如有）完成确认。不要复述工具实现的细节。"
)


def _build_system_prompt(db: Session) -> str:
    limit = settings_service.get_int(db, "order_ai_daily_token_limit", 200000)
    return (
        "你是「接单大厅」的 AI 帮手，帮用户找单、发单、看钱包。\n"
        "规则：\n"
        "1. 用语简短直接，不寒暄、不啰嗦，一句话切中要害。\n"
        "2. 找单：先 search_tasks，再挑最合适的 1-3 个推荐，注明分类和赏金。没搜到就直说没有。\n"
        "3. 发单：少问、多补全。用户没说悬赏就用 10，没说分类就按内容选；整理成完整草稿用 publish_task 交给用户确认。\n"
        "4. 看钱包：get_wallet_balance 后一句话报余额。\n"
        "5. 要接单：先 search_tasks 定位，再 accept_task 交给前端确认。\n"
        "6. 不确定就别编，不造数据。\n"
        f"7. 每人每日最多消耗 {limit} token，用完就说明天再来。\n"
        "可用分类：" + "/".join(ORDER_CATEGORIES) + "。"
    )


# ==================== 工具执行 ====================


def _run_tool(db: Session, user: User, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行工具，返回前端可渲染的卡片 data 与回传给模型的文本。"""
    if name == "search_tasks":
        return _tool_search_tasks(db, args)
    if name == "get_wallet_balance":
        return _tool_wallet(db, user.id)
    if name == "publish_task":
        return _tool_publish(db, user.id, args)
    if name == "accept_task":
        return _tool_accept(db, args)
    return {"card": None, "text": f"未知工具 {name}"}


def _tool_search_tasks(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    category = str(args.get("category") or "").strip() or None
    keyword = str(args.get("keyword") or "").strip() or None
    limit = min(int(args.get("limit") or SEARCH_LIMIT), SEARCH_LIMIT)
    base = select(OrderTask).where(OrderTask.status == "open")
    if category:
        base = base.where(OrderTask.category == category)
    if keyword:
        kw = f"%{keyword}%"
        base = base.where((OrderTask.title.like(kw)) | (OrderTask.content.like(kw)))
    rows = db.scalars(base.order_by(desc(OrderTask.boost), desc(OrderTask.id)).limit(limit)).all()
    tasks = [order_service.task_dict(db, t, None) for t in rows]
    if not tasks:
        return {
            "card": {"type": "tasks", "tasks": [], "empty": True},
            "text": "没有找到符合条件的任务。",
        }
    return {"card": {"type": "tasks", "tasks": tasks, "empty": False}, "text": f"找到 {len(tasks)} 个任务。"}


def _tool_wallet(db: Session, user_id: int) -> dict[str, Any]:
    w = order_service.get_wallet(db, user_id)
    return {
        "card": {"type": "wallet", "balance": w.balance, "frozen": w.frozen},
        "text": f"可用余额 {w.balance} 交易币，冻结 {w.frozen} 交易币。",
    }


def _current_draft(db: Session, user_id: int) -> dict[str, Any] | None:
    """取本会话最近一份发单草稿（供「只改标题、其余保留」的续改场景）。"""
    s = get_session(db, user_id)
    row = db.scalar(
        select(OrderAiMessage)
        .where(OrderAiMessage.session_id == s.id, OrderAiMessage.role == "tool", OrderAiMessage.meta.isnot(None))
        .order_by(desc(OrderAiMessage.id))
        .limit(1)
    )
    if not row:
        return None
    m = row.meta or {}
    if m.get("type") == "confirm" and m.get("action") == "publish" and m.get("data"):
        return m["data"]
    return None


def _tool_publish(db: Session, user_id: int, args: dict[str, Any]) -> dict[str, Any]:
    # 续改场景：只改被提到的字段，其余沿用上一版草稿，避免把未修改的内容一起覆盖掉
    draft = _current_draft(db, user_id) or {}
    title = str(args.get("title") or draft.get("title") or "").strip()
    content = str(args.get("content") or draft.get("content") or "").strip()
    category = str(args.get("category") or draft.get("category") or "其他").strip()
    try:
        reward = int(args.get("reward") if args.get("reward") not in (None, "") else draft.get("reward"))
    except (TypeError, ValueError):
        reward = 10
    if not reward:
        reward = 10
    if category not in ORDER_CATEGORIES:
        category = "其他"
    # 敏感操作：仅返回确认卡片，由前端二次确认后走 createOrder
    return {
        "card": {
            "type": "confirm",
            "action": "publish",
            "data": {"title": title, "content": content, "category": category, "reward": reward},
        },
        "text": "这是一份发单草稿，等你确认。",
    }


def _tool_accept(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    try:
        task_id = int(args.get("task_id"))
    except (TypeError, ValueError):
        return {"card": None, "text": "缺少任务 id。"}
    t = db.get(OrderTask, task_id)
    if not t:
        return {"card": None, "text": "该任务不存在。"}
    return {
        "card": {"type": "confirm", "action": "accept", "task": order_service.task_dict(db, t, None), "data": {"task_id": task_id}},
        "text": f"你确认接单「{t.title}」吗？",
    }


# ==================== 对话主入口 ====================


def chat(db: Session, user: User, text: str) -> dict[str, Any]:
    """处理一轮对话，返回要追加到前端的新消息（含工具卡片）。"""
    enabled = settings_service.get_bool(db, "order_ai_enabled", False)
    if not enabled:
        raise RuntimeError("订单 AI 尚未开启，请在后台开启后使用")

    s = get_session(db, user.id)
    limit = settings_service.get_int(db, "order_ai_daily_token_limit", 200000)
    state = state_to_dict(db, user.id)
    if limit > 0 and (s.daily_token or 0) >= limit:
        raise RuntimeError("今天的 AI 次数（Token）已用完，明天再来找我吧")

    # 保存用户消息
    _save(db, user.id, s.id, "user", text)
    db.flush()

    msgs: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt(db)}]
    msgs += _context_messages(db, user.id)
    msgs.append({"role": "user", "content": text})

    new_messages: list[dict[str, Any]] = []   # [user, ...assistant/tool] 返回前端
    spent = 0
    reasoning_extra: dict[str, Any] = {}

    for _ in range(MAX_TOOL_ROUNDS):
        resp = deepseek_client.chat(db, msgs, tools=TOOLS, max_tokens=1500, **reasoning_extra)
        if not resp.get("success"):
            raise RuntimeError(resp.get("error") or "AI 暂时无法响应，请稍后再试")

        if resp.get("usage"):
            spent += int((resp["usage"] or {}).get("total_tokens") or 0)

        text_part = resp.get("text") or ""
        tool_calls = resp.get("tool_calls") or []
        if resp.get("reasoning_content"):
            # 思考型模型：回传 assistant 消息时需原样带 reasoning_content
            reasoning_extra["reasoning_content"] = resp.get("reasoning_content")

        # 先追加 assistant 文本，再追加工具卡片
        if text_part:
            _save(db, user.id, s.id, "assistant", text_part)
            new_messages.append({"role": "assistant", "content": text_part})

        if not tool_calls:
            break

        # 逐个执行工具
        for tc in tool_calls:
            name = tc.get("name")
            args = tc.get("arguments") or {}
            try:
                result = _run_tool(db, user, name, args)
            except Exception:
                result = {"card": None, "text": f"工具 {name} 执行出错"}
            card = result.get("card")
            if card:
                _save(db, user.id, s.id, "tool", "", meta=card)
                new_messages.append({"role": "tool", "content": "", "meta": card})
            # 加入模型回话上下文
            msgs.append({"role": "assistant", "content": text_part or "", **reasoning_extra,
                         "tool_calls": [{"id": f"call_{name}", "type": "function", "function": {"name": name, "arguments": json_dumps(args)}}]})
            msgs.append({"role": "tool", "tool_call_id": f"call_{name}",
                         "content": result.get("text") or str(card or "")})
            # 每个工具后追加一句引导文本（assistant 说话）
            msgs.append({"role": "user", "content": "请根据工具结果，用简短自然的话引导我继续。"})

    s.daily_token = (s.daily_token or 0) + spent
    db.commit()
    try:
        db.refresh(s)
    except Exception:
        pass

    return {
        "new_messages": new_messages,
        "state": state_to_dict(db, user.id),
        "spent_tokens": spent,
    }


def json_dumps(args: dict[str, Any]) -> str:
    import json
    return json.dumps(args, ensure_ascii=False)