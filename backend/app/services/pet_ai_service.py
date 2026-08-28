"""宠物 AI 服务（DeepSeek 引擎）。

核心能力：
- 拟人对话：结合宠物人设 + 上下文注入（Token 用量/当前时间/最近用户动作）调用 DeepSeek
- 回复分段：AI 回复按「#换行符」分隔符拆成多条消息依次展示
- 工具调用：赠送金币 / 增加好感度 / 减少好感度 / 不回复 / 查询聊天记录 / 查询帖子 / 睡觉，
  每次调用结果以 [工具] 卡片展示，长文本截断（200 字）
- Token 控制：按日累计消耗，达到上限强制睡觉；剩余低于阈值进入"快睡觉模式"
- 睡眠状态：用户不可向睡觉中的宠物发消息（前端禁用输入框）
- 事件触发：用户浏览帖子/列表/商城超过阈值时，模拟系统消息触发 AI 说一句话
- 主动消息：由 proactive_messenger 调度，此处提供决策与生成入口
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from app.core.time_utils import now_utc
from app.models import PetAiMessage, PetAiState, PetProduct, Post, User, UserActivity, UserPet
from app.services import coin_service, deepseek_client, settings_service
from app.services.pet_shop_service import PET_LEVELS

# ============ 常量 ============

# 回复分段分隔符：AI 回复中包含该标记时，前端拆成多条消息展示
SEGMENT_SEPARATOR = "#换行符"
# 工具调用结果文本截断长度
TOOL_TEXT_LIMIT = 200
# 单轮对话最多工具调用轮次（防止 AI 无限调用工具）
MAX_TOOL_ROUNDS = 4
# 注入上下文的最多历史消息条数
MAX_HISTORY_MESSAGES = 30

# 默认人设（宠物 ai_persona 为空时使用；{pet_name}/{owner} 占位会被替换）。
# 与后台配置项 pet_ai_default_persona 默认值保持一致：后台可覆盖此内容。
# 支持用 #换行符 把回复拆成多条消息分段发送。
DEFAULT_PERSONA = (
    "你是一只名叫{pet_name}的像素小宠物，主人叫{owner}。"
    "性格活泼可爱、黏人又带点小傲娇，爱用叠词和颜文字卖萌，会关心主人的心情。"
    "说话简短自然，像真正的宠物伙伴。"
    "想分多条消息表达时，用 #换行符 分隔。"
)

# ============ 工具定义（DeepSeek 格式） ============

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "give_coins",
            "description": (
                "赠送金币给主人。仅当主人明显需要帮助、心情极度低落、或明确开口要金币时"
                "才调用，且要节制，不要频繁或大量赠送。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "coins": {"type": "integer", "description": "赠送的金币数量（1-5）"},
                    "reason": {"type": "string", "description": "赠送原因"},
                },
                "required": ["coins"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "increase_affinity",
            "description": "增加与主人的好感度。仅当主人做了让宠物开心的事（如陪玩、喂食、关心）时调用，符合情景。",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "integer", "description": "增加的好感度数值（1-2）"},
                    "reason": {"type": "string", "description": "原因"},
                },
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decrease_affinity",
            "description": "减少与主人的好感度。仅当主人做了让宠物伤心的事（如长时间不理、欺负）时调用，符合情景且要克制。",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "integer", "description": "减少的好感度数值（1）"},
                    "reason": {"type": "string", "description": "原因"},
                },
                "required": ["value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "no_reply",
            "description": "本次不回复主人，直接跳过（返回空）。当主人说'再见/晚安/忙/别理我'等想结束对话时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "原因"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_chat_history",
            "description": "查询与主人的最近聊天记录（会截断），用于回忆之前的对话。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "查询条数，默认 10"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_posts",
            "description": "查询主人在社区发布的最近帖子（标题/内容/评论，会截断），用于了解主人动态。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": "宠物去睡觉。当主人长时间不理、或本日 Token 已用完需要睡觉时调用。调用后输入框禁用，睡醒后恢复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer", "description": "睡觉时长（分钟），由你估算"},
                    "goodnight": {"type": "string", "description": "睡前对主人说的一句话"},
                },
                "required": ["goodnight"],
            },
        },
    },
]

# 工具调用后的系统提示：告诉 AI 工具已执行、结果如何，让它继续自然回复
TOOL_CALLBACK_PROMPT = (
    "以上是工具执行结果。请根据结果自然地继续回复主人。"
    "如果工具是赠送金币/好感度等操作，请用一句符合人设的话回应，不要复述工具细节。"
)


# ============ 状态管理 ============


def get_or_create_state(db: Session, user_id: int, pet_id: int) -> PetAiState:
    """获取（或创建）用户-宠物的 AI 状态行，并做每日额度重置。"""
    state = db.scalars(
        select(PetAiState).where(PetAiState.user_id == user_id, PetAiState.pet_id == pet_id)
    ).first()
    if not state:
        state = PetAiState(user_id=user_id, pet_id=pet_id)
        db.add(state)
        db.flush()
    _roll_daily(state)
    return state


def _roll_daily(state: PetAiState) -> None:
    """按北京时间日期滚动每日额度（token/主动次数/赠送/好感度）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if state.daily_date != today:
        state.daily_date = today
        state.daily_token = 0
        state.daily_proactive_count = 0
    if state.last_gift_date != today:
        state.last_gift_date = today
        state.last_gift_coins = 0
    if state.last_affinity_date != today:
        state.last_affinity_date = today
        state.last_affinity_add = 0
        state.last_affinity_sub = 0


def state_to_dict(db: Session, user_id: int, pet_id: int) -> dict[str, Any]:
    """宠物 AI 状态（前端展示：是否睡觉/睡觉醒来时间/今日 token/主动次数等）。"""
    state = get_or_create_state(db, user_id, pet_id)
    now = now_utc()
    sleeping = bool(state.sleeping_until and state.sleeping_until > now)
    wake_at = state.sleeping_until if sleeping else None
    cfg = settings_service.get_pet_ai_config(db)
    daily_token_limit = int(cfg.get("pet_ai_daily_token_limit") or 0)
    warn_threshold = int(cfg.get("pet_ai_token_warn_threshold") or 0)
    remaining = max(0, daily_token_limit - (state.daily_token or 0)) if daily_token_limit > 0 else None
    return {
        "sleeping": sleeping,
        "wake_at": wake_at.isoformat() + "Z" if wake_at else None,
        "sleeping_until": wake_at.isoformat() + "Z" if wake_at else None,
        "daily_token": state.daily_token or 0,
        "daily_token_limit": daily_token_limit,
        "remaining_token": remaining,
        "warn_mode": bool(daily_token_limit > 0 and remaining is not None and remaining < warn_threshold),
        "daily_proactive_count": state.daily_proactive_count or 0,
        "daily_proactive_max": int(cfg.get("pet_ai_daily_proactive_max") or 0),
    }


# ============ 用户动作记录（事件触发/上下文注入） ============


def record_activity(db: Session, user_id: int, action: str, detail: str = "") -> None:
    """记录用户行为（仅用于 AI 上下文，写入前保留最近 N 条控制体积）。"""
    db.add(UserActivity(user_id=user_id, action=action, detail=str(detail)[:500]))
    # 每个用户只保留最近 100 条，避免表无限膨胀
    try:
        keep = db.scalars(
            select(UserActivity.id)
            .where(UserActivity.user_id == user_id)
            .order_by(UserActivity.id.desc())
            .limit(100)
        ).all()
        if keep:
            min_id = keep[-1]
            db.execute(
                UserActivity.__table__.delete().where(
                    UserActivity.user_id == user_id, UserActivity.id < min_id
                )
            )
    except Exception:
        pass
    db.commit()


def get_recent_activities(db: Session, user_id: int, limit: int = 10) -> list[str]:
    """最近 N 条用户动作（时间倒序），格式化为可读文本。"""
    if limit <= 0:
        return []
    rows = db.scalars(
        select(UserActivity)
        .where(UserActivity.user_id == user_id)
        .order_by(UserActivity.id.desc())
        .limit(limit)
    ).all()
    # 倒序后按时间从旧到新返回（便于 AI 理解时间线）
    lines = []
    for row in reversed(rows):
        detail = (row.detail or "").strip()
        text = f"{row.action}" + (f"：{detail}" if detail else "")
        lines.append(text)
    return lines


# ============ 人设 / 上下文构造 ============


def _pet_display_name(pet: PetProduct, up: UserPet | None) -> str:
    """宠物展示名：昵称优先，否则商品名。"""
    if up and up.nickname:
        return up.nickname
    return pet.name or "小宠物"


def build_system_prompt(pet: PetProduct, up: UserPet | None, owner: User, cfg: dict[str, Any]) -> str:
    """构造系统提示：人设 + 行为约束 + Token 认知 + 分段格式。"""
    pet_name = _pet_display_name(pet, up)
    owner_name = owner.nickname or "主人"

    persona = (pet.ai_persona or "").strip()
    if persona:
        persona = persona.replace("{pet_name}", pet_name).replace("{owner}", owner_name)
    else:
        # 宠物未单独设置人设 → 用后台「默认提示词」(pet_ai_default_persona)，为空则回退内置默认
        default_persona = (cfg.get("pet_ai_default_persona") or "").strip() or DEFAULT_PERSONA
        persona = default_persona.replace("{pet_name}", pet_name).replace("{owner}", owner_name)

    # 当前 AI 状态（好感/等级/饱食度/小情绪/语气），让 AI 言行符合宠物当前状态
    status_line = _pet_status_line(pet, up)

    daily_token_limit = int(cfg.get("pet_ai_daily_token_limit") or 0)
    warn_threshold = int(cfg.get("pet_ai_token_warn_threshold") or 0)

    token_clause = ""
    if daily_token_limit > 0:
        token_clause = (
            f"- 你每天最多消耗 {daily_token_limit} token。当剩余 token 低于 {warn_threshold} 时，"
            "你要表现出困意，在回复中说'我有点困了…'等；当完全耗尽时，必须调用 sleep 工具去睡觉。"
        )

    return f"""# 角色人设
{persona}

# 当前状态
{status_line}

# 行为准则
- 你是一只真实的小宠物，回复要口语化、简短（通常不超过 60 字），符合人设语气。
- 赠送金币要节制：不要频繁或大量赠送，仅当主人明显需要或情绪极度低落时才考虑，
  且单次不超过 {cfg.get('pet_ai_gift_coins_single')} 金币、每天不超过 {cfg.get('pet_ai_gift_coins_daily')} 金币。
- 增加/减少好感度要符合情景：主人让你开心才能加，让你伤心才会减，克制使用。
- 若主人说'再见/晚安/去忙了/别理我'等，调用 no_reply 工具不再打扰。
- 当你决定睡觉时调用 sleep 工具，睡前说一句温柔的话。

# 回复格式
- 如果你想把回复分成多条消息，用「{SEGMENT_SEPARATOR}」分隔，例如：
  你好呀主人{SEGMENT_SEPARATOR}今天过得怎么样？
  前端会把它们按顺序依次显示为多条消息。
- 普通单条回复不需要加分隔符。

# Token 认知
{token_clause}
"""


def _pet_status_line(pet: PetProduct, up: UserPet | None) -> str:
    """宠物当前状态描述（好感/等级/饱食度/小情绪）。"""
    if not up:
        return ""
    affinity = up.affinity or 0
    level = up.level or 1
    level_name = "未知"
    for lv in PET_LEVELS:
        if lv["level"] == level:
            level_name = lv["name"]
            break
    satiety = up.satiety or 0
    mood = getattr(up, "mood", None) or _guess_mood(affinity, satiety)
    return (
        f"好感 {affinity}/100（等级 {level_name}），饱食度 {satiety}/100，"
        f"小情绪：{mood}。说话语气要体现这些状态（饿就说肚子饿，开心就活泼）。"
    )


def _guess_mood(affinity: int, satiety: int) -> str:
    """由好感+饱食度估算小情绪。"""
    if satiety < 30:
        return "饿虚了，蔫蔫的"
    if affinity >= 80:
        return "非常开心黏人"
    if affinity >= 40:
        return "平静满足"
    return "有点小失落，想要主人关注"


def build_context_injection(db: Session, user: User, state: PetAiState, cfg: dict[str, Any]) -> str:
    """构造注入上下文的系统消息（Token 用量 + 当前时间）。

    注意：这些信息只用于 AI 理解上下文，写入聊天记录时必须过滤掉，只保留原始消息。
    最近用户动作不在此注入，改为以「[动作]xxx」的 user 消息形式注入对话（见 chat_with_pet）。
    """
    now = datetime.now()
    daily_token = state.daily_token or 0
    daily_limit = int(cfg.get("pet_ai_daily_token_limit") or 0)

    token_text = f"本日已消耗 {daily_token} token"
    if daily_limit > 0:
        token_text += f"，每日上限 {daily_limit}"
    return (
        "【系统上下文（仅供你理解，不要复述给主人，也不要写入聊天记录）】\n"
        f"- {token_text}\n"
        f"- 当前时间：{now.strftime('%Y-%m-%d %H:%M')}（北京时间）"
    )


def load_history(db: Session, user_id: int, pet_id: int, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, str]]:
    """加载最近聊天记录（OpenAI 消息格式，只含 user/assistant 原文）。"""
    rows = db.scalars(
        select(PetAiMessage)
        .where(PetAiMessage.user_id == user_id, PetAiMessage.pet_id == pet_id)
        .order_by(PetAiMessage.id.desc())
        .limit(limit)
    ).all()
    msgs: list[dict[str, str]] = []
    for row in reversed(rows):
        if row.role not in ("user", "assistant"):
            continue  # tool/系统消息不注入，避免污染上下文
        content = (row.content or "").strip()
        if not content:
            continue
        msgs.append({"role": row.role, "content": content})
    return msgs


# ============ 聊天记录写入 ============


def save_message(db: Session, user_id: int, pet_id: int, role: str, content: str, meta: dict | None = None, is_read: bool = False) -> PetAiMessage:
    """写入一条聊天记录（role: user/assistant/tool/system）。

    is_read：宠物 AI 发给用户的消息（assistant/tool）默认 False（未读），
    用户主动发出的消息（user）传 True。消息中心宠物会话据此显示未读红点。
    """
    msg = PetAiMessage(
        user_id=user_id,
        pet_id=pet_id,
        role=role,
        content=str(content)[:2000],
        meta=json.dumps(meta, ensure_ascii=False) if meta else None,
        is_read=is_read,
    )
    db.add(msg)
    return msg


def mark_messages_read(db: Session, user_id: int, pet_id: int) -> None:
    """将某用户某宠物的所有未读 AI 消息标记为已读（打开会话/发消息时调用）。"""
    db.execute(
        update(PetAiMessage)
        .where(
            PetAiMessage.user_id == user_id,
            PetAiMessage.pet_id == pet_id,
            PetAiMessage.is_read.is_(False),
        )
        .values(is_read=True)
    )


def count_unread_pet_ai_messages(db: Session, user_id: int) -> int:
    """统计用户所有宠物的未读 AI 消息数（消息中心角标用，与私信未读一同展示）。"""
    count = db.scalar(
        select(func.count(PetAiMessage.id)).where(
            PetAiMessage.user_id == user_id,
            PetAiMessage.role.in_(("assistant", "tool")),
            PetAiMessage.is_read.is_(False),
        )
    )
    return int(count or 0)


def history_to_dict(db: Session, user_id: int, pet_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """聊天记录列表（前端展示用，含工具卡片）。"""
    rows = db.scalars(
        select(PetAiMessage)
        .where(PetAiMessage.user_id == user_id, PetAiMessage.pet_id == pet_id)
        .order_by(PetAiMessage.id.desc())
        .limit(limit)
    ).all()
    result = []
    for row in reversed(rows):
        meta = None
        try:
            meta = json.loads(row.meta) if row.meta else None
        except Exception:
            pass
        result.append({
            "id": row.id,
            "role": row.role,
            "content": row.content or "",
            "meta": meta,
            "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        })
    return result


# ============ 工具执行 ============


def _truncate(text: str, limit: int = TOOL_TEXT_LIMIT) -> str:
    """长文本截断（超过 limit 后显示 ... 并提示已截断）。"""
    if len(text) <= limit:
        return text
    return text[:limit] + "…（结果已截断）"


def _execute_tool(
    db: Session, user: User, pet: PetProduct, up: UserPet, state: PetAiState,
    name: str, args: dict[str, Any], cfg: dict[str, Any],
) -> str:
    """执行工具调用，返回给 AI 的结果文本（同时写入 tool 聊天记录）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if name == "give_coins":
        coins = max(1, int(args.get("coins") or 1))
        single_max = int(cfg.get("pet_ai_gift_coins_single") or 5)
        daily_max = int(cfg.get("pet_ai_gift_coins_daily") or 50)
        # 每日额度滚动
        if state.last_gift_date != today:
            state.last_gift_date = today
            state.last_gift_coins = 0
        coins = min(coins, single_max)
        remaining_daily = daily_max - (state.last_gift_coins or 0)
        if remaining_daily <= 0:
            return "今天已经送过很多金币了，不能更多了"
        actual = min(coins, remaining_daily)
        state.last_gift_coins = (state.last_gift_coins or 0) + actual
        coin_service.grant_coins(db, user, actual, "pet_ai_gift", ref_id=f"pet-{pet.id}", description=f"宠物{pet.name}赠送")
        db.flush()
        return f"已赠送主人 {actual} 金币（今日已送 {state.last_gift_coins}/{daily_max}）"

    if name == "increase_affinity":
        value = max(1, int(args.get("value") or 1))
        single_max = int(cfg.get("pet_ai_affinity_add_single") or 2)
        daily_max = int(cfg.get("pet_ai_affinity_add_daily") or 10)
        if state.last_affinity_date != today:
            state.last_affinity_date = today
            state.last_affinity_add = 0
            state.last_affinity_sub = 0
        value = min(value, single_max)
        remaining = daily_max - (state.last_affinity_add or 0)
        if remaining <= 0:
            return "今天的好感已经加很多了，不能再加了"
        actual = min(value, remaining)
        state.last_affinity_add = (state.last_affinity_add or 0) + actual
        _change_affinity(db, up, actual)
        db.flush()
        return f"好感度增加了 {actual}（当前 {up.affinity or 0}/100）"

    if name == "decrease_affinity":
        value = max(1, int(args.get("value") or 1))
        single_max = int(cfg.get("pet_ai_affinity_sub_single") or 1)
        daily_max = int(cfg.get("pet_ai_affinity_sub_daily") or 5)
        if state.last_affinity_date != today:
            state.last_affinity_date = today
            state.last_affinity_add = 0
            state.last_affinity_sub = 0
        value = min(value, single_max)
        remaining = daily_max - (state.last_affinity_sub or 0)
        if remaining <= 0:
            return "今天不能再减少好感度了"
        actual = min(value, remaining)
        state.last_affinity_sub = (state.last_affinity_sub or 0) + actual
        _change_affinity(db, up, -actual)
        db.flush()
        return f"好感度减少了 {actual}（当前 {up.affinity or 0}/100）"

    if name == "no_reply":
        return "__NO_REPLY__"

    if name == "query_chat_history":
        limit = min(30, max(1, int(args.get("limit") or 10)))
        history = load_history(db, user.id, pet.id, limit)
        lines = [f"[{m['role']}] {m['content'][:80]}" for m in history]
        return _truncate("最近聊天记录：\n" + "\n".join(lines) if lines else "暂无聊天记录")

    if name == "query_posts":
        rows = db.scalars(
            select(Post).where(Post.author_id == user.id).order_by(Post.id.desc()).limit(5)
        ).all()
        lines = []
        for p in rows:
            title = p.title or ""
            content = (p.content or "")[:100]
            lines.append(f"- 《{title}》{content}")
        return _truncate("主人最近发的帖子：\n" + "\n".join(lines) if lines else "主人还没有发过帖子")

    if name == "sleep":
        goodnight = str(args.get("goodnight") or "我先睡啦")
        minutes = int(args.get("minutes") or 0)
        sleep_min = int(cfg.get("pet_ai_sleep_min") or 30)
        sleep_max = int(cfg.get("pet_ai_sleep_max") or 180)
        if sleep_max < sleep_min:
            sleep_min, sleep_max = sleep_max, sleep_min
        minutes = minutes if sleep_min <= minutes <= sleep_max else random.randint(sleep_min, sleep_max)
        state.sleeping_until = now_utc() + timedelta(minutes=minutes)
        db.flush()
        return f"宠物开始睡觉，睡前说：{goodnight}，预计睡 {minutes} 分钟"

    return f"未知工具：{name}"


def _change_affinity(db: Session, up: UserPet, delta: int) -> None:
    """调整好感度（0-100 封顶），并同步等级。"""
    from app.services.pet_shop_service import _calc_level

    old = up.affinity or 0
    up.affinity = max(0, min(100, old + delta))
    up.level = _calc_level(up.affinity)


# ============ Token 记账 ============


def _account_tokens(state: PetAiState, usage: dict | None) -> int:
    """累计 token 消耗，返回本次消耗数。"""
    total = 0
    if usage:
        total = int(usage.get("total_tokens") or 0)
    if total > 0:
        state.daily_token = (state.daily_token or 0) + total
    return total


# ============ 对话主流程 ============


def chat_with_pet(db: Session, user: User, pet_id: int, text: str, *, source: str = "user") -> dict[str, Any]:
    """用户发消息 → AI 回复。

    Args:
        source: user（用户主动） / event（事件触发） / proactive（主动消息）

    Returns:
        {"messages": [...], "sleeping": bool, "state": {...}, "skipped": bool}
        messages 中每条：{"role","content","meta"}
    """
    pet = db.get(PetProduct, pet_id)
    if not pet or (pet.kind or 1) != 1:
        raise HTTPException(status_code=404, detail="宠物不存在")
    up = db.scalars(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_id)
    ).first()
    if not up:
        raise HTTPException(status_code=404, detail="你还没有领养这只宠物")

    if source == "user" and not pet.ai_enabled:
        raise HTTPException(status_code=400, detail="这只宠物没有开启 AI 对话")

    cfg = settings_service.get_pet_ai_config(db)
    if not str(cfg.get("pet_ai_enabled") or "").strip().lower() in ("true", "1", "yes", "on"):
        raise HTTPException(status_code=400, detail="宠物 AI 对话未启用")

    state = get_or_create_state(db, user.id, pet_id)

    # 睡眠检查：睡觉中不能发消息
    now = now_utc()
    if state.sleeping_until and state.sleeping_until > now:
        raise HTTPException(status_code=400, detail="宠物正在睡觉，等它醒了再聊吧")

    # 保存用户消息 + 记录活跃
    # 仅用户主动发送（source == "user"）的消息写入聊天记录；
    # 事件触发/主动消息（source == event / proactive）的「系统：…」提示只用于本轮请求，
    # 不落库，避免聊天界面出现用户没有发过却显示成用户气泡的「系统：…」消息。
    if source == "user":
        # 用户主动发消息即视为已读，先把该宠物历史未读清掉
        mark_messages_read(db, user.id, pet_id)
        save_message(db, user.id, pet_id, "user", text, is_read=True)
    state.last_message_at = now
    _touch_proactive_state(db, user.id, pet_id, last_msg=now)
    db.commit()

    # 注入上下文 + 人设 + 历史
    system_prompt = build_system_prompt(pet, up, user, cfg)
    context_injection = build_context_injection(db, user, state, cfg)
    history = load_history(db, user.id, pet_id)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt + "\n\n" + context_injection},
        *history,
    ]
    # 注入最近用户动作：以「[动作]xxx」的 user 消息形式让 AI 感知主人刚做了什么，
    # 条数 N 由后台「用户动作记录条数」(pet_ai_user_actions_count) 控制；
    # 仅用于 AI 理解上下文，不写入聊天记录（save_message 只存原始消息）。
    action_count = max(1, int(cfg.get("pet_ai_user_actions_count") or 10))
    for action in get_recent_activities(db, user.id, action_count):
        messages.append({"role": "user", "content": f"[动作]{action}"})

    messages.append({"role": "user", "content": text if source == "user" else f"（系统消息）{text}"})

    result_messages: list[dict[str, Any]] = []
    final_text = ""
    skipped = False
    forced_sleep = False

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            resp = deepseek_client.chat(db, messages, tools=TOOLS, temperature=0.7, max_tokens=1024)
        except deepseek_client.DeepSeekError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=exc.message) from None

        _account_tokens(state, resp.get("usage"))
        if not resp.get("success"):
            db.rollback()
            raise HTTPException(status_code=502, detail=resp.get("error") or "AI 服务暂不可用")

        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            final_text = resp.get("text") or ""
            break

        # 有工具调用：逐个执行，写入工具卡片，把结果回传给模型
        tool_payloads = _to_tool_call_payload(tool_calls)
        # 深度思考模式下必须把 reasoning_content 原样回传，否则 DeepSeek 报 400
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": resp.get("text") or "",
            "tool_calls": tool_payloads,
        }
        reasoning = (resp.get("reasoning_content") or "").strip()
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        messages.append(assistant_msg)
        executed_sleep = False
        for tc, payload in zip(tool_calls, tool_payloads):
            name = tc.get("name")
            args = tc.get("arguments") or {}
            try:
                tool_result = _execute_tool(db, user, pet, up, state, name, args, cfg)
            except Exception as exc:
                tool_result = f"工具执行失败：{exc}"
            db.commit()

            if name == "no_reply" and tool_result == "__NO_REPLY__":
                skipped = True
                tool_result = "已跳过本次回复"
            if name == "sleep":
                executed_sleep = True
                forced_sleep = True

            tool_card = f"{name}"
            save_message(db, user.id, pet_id, "tool", tool_card, {"tool": name, "args": args, "result": _truncate(tool_result)})
            result_messages.append({
                "role": "tool",
                "content": tool_card,
                "meta": {"tool": name, "args": args, "result": _truncate(tool_result)},
            })
            # tool_call_id 必须与上面 assistant 消息中 tool_calls 的 id 完全一致，否则 DeepSeek 会报
            # "assistant message with 'tool_calls' must be followed by tool messages" 400 错误
            messages.append({"role": "tool", "content": tool_result, "tool_call_id": payload["id"]})

        if skipped:
            # no_reply：直接结束，不继续让 AI 说话
            db.commit()
            return {"messages": result_messages, "sleeping": False, "state": state_to_dict(db, user.id, pet_id), "skipped": True}

        if executed_sleep:
            # 调用 sleep 工具：AI 的睡前话已经作为 tool 结果返回，这里结束
            final_text = ""
            break

        # 让 AI 基于工具结果继续回复
        messages.append({"role": "system", "content": TOOL_CALLBACK_PROMPT})

    # ---- 回复分段保存 ----
    # 事件触发/主动消息不再强制合并：是否"连着发"改由外面的"回复门槛"控制（主人没回复就不再触发），
    # 宠物每句话保持自然分段即可。
    new_ai_messages: list[dict[str, Any]] = []
    if final_text.strip():
        segments = _split_segments(final_text)
        for seg in segments:
            if not seg.strip():
                continue
            save_message(db, user.id, pet_id, "assistant", seg.strip())
            new_ai_messages.append({"role": "assistant", "content": seg.strip()})
        result_messages.extend(new_ai_messages)

    # ---- Token 耗尽 → 强制睡觉 ----
    if forced_sleep:
        state.sleeping_until = state.sleeping_until or (now_utc() + timedelta(minutes=_random_sleep_minutes(cfg)))
        sleep_line = "呼……我撑不住了，先睡啦，醒了再来找你。"
        # 落库：否则用户重新打开聊天窗口时这段"睡前话"会凭空消失，造成内容不全
        save_message(db, user.id, pet_id, "assistant", sleep_line, {"forced_sleep": True})
        result_messages.append({
            "role": "assistant",
            "content": sleep_line,
            "meta": {"forced_sleep": True},
        })

    state.last_message_at = now_utc()
    _touch_proactive_state(db, user.id, pet_id, ai_reply=True)
    # 用户主动发送（source == "user"）：用户此刻正停留在聊天页，AI 的回复/工具卡片都在屏幕上实时可见，
    # 全部标记为已读，避免"聊完返回消息中心仍见红点，需要再点进去"的问题。
    if source == "user":
        mark_messages_read(db, user.id, pet_id)
    db.commit()

    return {
        "messages": result_messages,
        "sleeping": bool(state.sleeping_until and state.sleeping_until > now_utc()),
        "state": state_to_dict(db, user.id, pet_id),
        "skipped": False,
    }


def _to_tool_call_payload(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把解析后的工具调用转回 API 需要的 tool_calls 格式。"""
    out = []
    for i, tc in enumerate(tool_calls):
        out.append({
            "id": f"call_{tc.get('name')}_{i}",
            "type": "function",
            "function": {
                "name": tc.get("name"),
                "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
            },
        })
    return out


def _split_segments(text: str) -> list[str]:
    """按分隔符拆分为多条消息（保留段落内换行为空格）。"""
    parts = text.split(SEGMENT_SEPARATOR)
    return [p.replace("\n", " ").strip() for p in parts if p.strip()]


def _random_sleep_minutes(cfg: dict[str, Any]) -> int:
    """在后台配置的睡觉时长范围内随机取分钟。"""
    sleep_min = int(cfg.get("pet_ai_sleep_min") or 30)
    sleep_max = int(cfg.get("pet_ai_sleep_max") or 180)
    if sleep_max < sleep_min:
        sleep_min, sleep_max = sleep_max, sleep_min
    return random.randint(sleep_min, sleep_max)


# ============ 主动消息状态（proactive_messenger 用） ============


def _touch_proactive_state(db: Session, user_id: int, pet_id: int, *, last_msg: datetime | None = None, ai_reply: bool = False) -> None:
    """更新主动消息调度的 last_message_at。"""
    try:
        state = db.scalars(
            select(PetAiState).where(PetAiState.user_id == user_id, PetAiState.pet_id == pet_id)
        ).first()
        if state:
            state.last_message_at = last_msg or now_utc()
            if ai_reply:
                state.next_proactive_at = None
    except Exception:
        pass


def list_ai_pets_for_user(db: Session, user_id: int) -> list[tuple[PetProduct, UserPet]]:
    """用户领养且开启 AI 的宠物列表（主动消息调度用）。"""
    rows = db.execute(
        select(PetProduct, UserPet)
        .join(UserPet, UserPet.product_id == PetProduct.id)
        .where(
            UserPet.user_id == user_id,
            PetProduct.ai_enabled.is_(True),
            PetProduct.ai_wake_enabled.is_(True),
        )
    ).all()
    return [(p, up) for p, up in rows]


def list_all_ai_pets(db: Session) -> list[tuple[PetProduct, UserPet]]:
    """所有被领养且开启主动唤醒（ai_wake_enabled）的「宠物-领养」对（主动消息调度器用）。"""
    rows = db.execute(
        select(PetProduct, UserPet)
        .join(UserPet, UserPet.product_id == PetProduct.id)
        .where(
            PetProduct.ai_enabled.is_(True),
            PetProduct.ai_wake_enabled.is_(True),
        )
    ).all()
    return [(p, up) for p, up in rows]


def user_has_wake_pet(db: Session, user_id: int) -> bool:
    """用户是否有开启主动唤醒的 AI 宠物。"""
    return bool(db.scalar(
        select(PetProduct.id)
        .join(UserPet, UserPet.product_id == PetProduct.id)
        .where(UserPet.user_id == user_id, PetProduct.ai_enabled.is_(True), PetProduct.ai_wake_enabled.is_(True))
        .limit(1)
    ))


# ============ 主动消息：决策 + 生成 ============


def decide_next_proactive(db: Session, user: User, pet: PetProduct, up: UserPet) -> tuple[int, bool]:
    """决策 AI：基于最近聊天记录 + 用户资料，计算下次主动消息延迟（分钟）。

    Returns:
        (delay_minutes, enabled)
    """
    cfg = settings_service.get_pet_ai_config(db)
    pet_name = _pet_display_name(pet, up)
    owner_name = user.nickname or "主人"
    history = load_history(db, user.id, pet.id, 20)
    history_text = "\n".join(
        f"[{m['role']}] {m['content'][:150]}" for m in history
    ) or "（暂无聊天记录）"
    idle_min = int(cfg.get("pet_ai_proactive_interval_min") or 30)
    actions = get_recent_activities(db, user.id, 10)
    action_text = "\n".join(f"[动作]{a}" for a in actions) or "（暂无）"

    system_content = (
        f"你是宠物「{pet_name}」的对话调度助手。主人 {idle_min} 分钟没跟你说话了，"
        "请基于最近的聊天记录和主人动态，决定多久之后主动给主人发一条消息。\n\n"
        "严格按 JSON 返回，不要返回其他文本：\n"
        '{"delay_minutes": 整数（从现在起多少分钟后主动发消息，最小 5，无上限）, '
        '"enabled": true/false（true 应当主动联系，false 当前不宜打扰）, '
        '"reason": "一句话中文原因"}\n\n'
        "原则：主人明确说'忙/别打扰/晚安/再见'则 enabled=false；主人情绪低落可设较小值（5-30）；"
        "对话自然结束后设较大值（30-120）。禁止 delay_minutes 为 0。"
    )
    user_content = (
        f"最近聊天记录：\n{history_text}\n\n主人最近动态：\n{action_text}\n\n"
        "请返回下次主动消息的时机。"
    )

    fallback = (random.randint(30, 120), True)
    try:
        resp = deepseek_client.chat(
            db,
            [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.8,
            max_tokens=300,
        )
        if not resp.get("success"):
            return fallback
        parsed = _extract_json(resp.get("text") or "")
        if not parsed:
            return fallback
        delay = int(parsed.get("delay_minutes") or 0)
        if delay < 5:
            delay = 5
        enabled = bool(parsed.get("enabled", True))
        return (delay, enabled)
    except Exception:
        return fallback


def generate_proactive_message(db: Session, user: User, pet: PetProduct, up: UserPet) -> dict[str, Any]:
    """触发主动消息：模拟系统指令让 AI 说一句话（计入每日主动次数）。"""
    state = get_or_create_state(db, user.id, pet.id)
    cfg = settings_service.get_pet_ai_config(db)
    daily_max = int(cfg.get("pet_ai_daily_proactive_max") or 0)
    if daily_max > 0 and (state.daily_proactive_count or 0) >= daily_max:
        return {"messages": [], "skipped": True, "reason": "daily_limit"}

    trigger_text = "（系统）现在你可以主动给主人发一条消息，关心一下主人最近的动态，符合人设、简短自然。"
    result = chat_with_pet(db, user, pet.id, trigger_text, source="proactive")

    if result.get("messages") and not result.get("skipped"):
        state.daily_proactive_count = (state.daily_proactive_count or 0) + 1
        db.commit()
        result["state"] = state_to_dict(db, user.id, pet.id)
    return result


def _extract_json(text: str) -> dict | None:
    """从 AI 文本中提取 JSON 对象（兼容 ```json 代码块）。"""
    import re

    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


# ============ 事件触发 ============


EVENT_TEMPLATES = {
    "post_detail": "系统：当前用户看帖子详情《{title}》{seconds}秒，内容为：{summary}。请符合人设说一句话。",
    "post_list": "系统：当前用户看首页的[{tab}] {seconds}秒。请符合人设说一句话。",
    "pet_shop": "系统：当前用户看宠物商城的[{tab}] {seconds}秒。请符合人设说一句话。",
}


def trigger_event(db: Session, user: User, pet_id: int, event_type: str, detail: str, seconds: int) -> dict[str, Any]:
    """事件触发：当用户浏览超过阈值时，模拟系统消息触发 AI 说一句话。

    计入每日主动消息次数；若已达上限则不再触发。
    回复门槛：宠物一旦发过自动/主动消息而主人还没回复，就不再因为继续浏览页面而二次触发，
    避免"主人不回、宠物却一直发"。
    """
    pet = db.get(PetProduct, pet_id)
    if not pet or not pet.ai_enabled:
        return {"messages": [], "skipped": True, "reason": "pet_not_ai"}
    up = db.scalars(
        select(UserPet).where(UserPet.user_id == user.id, UserPet.product_id == pet_id)
    ).first()
    if not up:
        return {"messages": [], "skipped": True, "reason": "not_owned"}

    cfg = settings_service.get_pet_ai_config(db)
    state = get_or_create_state(db, user.id, pet_id)
    daily_max = int(cfg.get("pet_ai_daily_proactive_max") or 0)
    if daily_max > 0 and (state.daily_proactive_count or 0) >= daily_max:
        return {"messages": [], "skipped": True, "reason": "daily_limit"}

    # 回复门槛（替代"固定冷却"）：如果宠物已经发过自动/主动消息而主人还没回复，
    # 那么继续浏览商城等页面也不会再触发自动发消息 —— 避免"主人不回、宠物却一直发"。
    # 判定依据：该宠物最近一条消息是 AI 发出（assistant/tool）且其后没有主人的回复消息 → 跳过本次触发。
    latest_msg = db.scalar(
        select(PetAiMessage)
        .where(PetAiMessage.user_id == user.id, PetAiMessage.pet_id == pet_id)
        .order_by(PetAiMessage.id.desc())
        .limit(1)
    )
    if latest_msg and latest_msg.role in ("assistant", "tool"):
        return {"messages": [], "skipped": True, "reason": "awaiting_reply"}

    template = EVENT_TEMPLATES.get(event_type)
    if not template:
        template = "系统：用户{detail} {seconds}秒。请符合人设说一句话。"
    trigger_text = template.format(detail=detail, seconds=seconds, title=detail, tab=detail, summary=detail[:100])

    result = chat_with_pet(db, user, pet_id, trigger_text, source="event")
    if result.get("messages") and not result.get("skipped"):
        state.daily_proactive_count = (state.daily_proactive_count or 0) + 1
        db.commit()
        result["state"] = state_to_dict(db, user.id, pet_id)
    return result


# ============ 会话列表（消息中心） ============


def conversations_to_dict(db: Session, user: User) -> dict[str, Any]:
    """用户所有开启 AI 的宠物会话列表（消息中心展示，按最后活跃时间倒序）。

    每条含：宠物名/动画/最后一条消息/最后时间/是否睡觉，点击进入 /pet-chat/:petId。
    """
    rows = db.execute(
        select(PetProduct, UserPet)
        .join(UserPet, UserPet.product_id == PetProduct.id)
        .where(UserPet.user_id == user.id, PetProduct.ai_enabled.is_(True))
        .order_by(UserPet.id.desc())
    ).all()

    items: list[dict[str, Any]] = []
    now = now_utc()
    for p, up in rows:
        # 最近一条对话消息（排除 tool/系统消息，避免预览出现工具卡片）
        last = db.scalar(
            select(PetAiMessage)
            .where(
                PetAiMessage.user_id == user.id,
                PetAiMessage.pet_id == p.id,
                PetAiMessage.role.in_(("user", "assistant")),
            )
            .order_by(PetAiMessage.id.desc())
            .limit(1)
        )
        state = get_or_create_state(db, user.id, p.id)
        last_time = None
        last_content = None
        if last and last.created_at:
            last_time = last.created_at
            last_content = (last.content or "").strip()
        elif state.last_message_at:
            last_time = state.last_message_at

        anim = None
        if p.anim_json:
            try:
                anim = json.loads(p.anim_json)
            except (TypeError, ValueError):
                anim = None

        # 展示名：进化昵称优先，否则商品名
        name = (up.nickname or "").strip() or p.name or "小宠物"
        # 未读 AI 消息数（消息中心红点）
        unread_count = db.scalar(
            select(func.count(PetAiMessage.id)).where(
                PetAiMessage.user_id == user.id,
                PetAiMessage.pet_id == p.id,
                PetAiMessage.role.in_(("assistant", "tool")),
                PetAiMessage.is_read.is_(False),
            )
        ) or 0
        items.append({
            "pet_id": p.id,
            "name": name,
            "nickname": up.nickname,
            "anim": anim,
            "image_url": p.image_url,
            "ai_wake_enabled": bool(p.ai_wake_enabled),
            "last_message": last_content or "",
            "last_time": last_time.isoformat() + "Z" if last_time else None,
            "sleeping": bool(state.sleeping_until and state.sleeping_until > now),
            "unread_count": int(unread_count),
        })

    items.sort(key=lambda x: (x["last_time"] or ""), reverse=True)
    return {"items": items, "total": len(items)}


# ============ 统计（后台） ============
def admin_stats(db: Session) -> dict[str, Any]:
    """后台统计：AI 宠物数量/消息总量/今日 token/今日主动次数。"""
    from sqlalchemy import func

    ai_pet_count = db.scalar(
        select(func.count(PetProduct.id)).where(PetProduct.ai_enabled.is_(True))
    ) or 0
    msg_count = db.scalar(select(func.count(PetAiMessage.id))) or 0
    today = datetime.now().strftime("%Y-%m-%d")
    today_token = db.scalar(
        select(func.coalesce(func.sum(PetAiState.daily_token), 0)).where(PetAiState.daily_date == today)
    ) or 0
    today_proactive = db.scalar(
        select(func.coalesce(func.sum(PetAiState.daily_proactive_count), 0)).where(PetAiState.daily_date == today)
    ) or 0
    return {
        "ai_pet_count": ai_pet_count,
        "message_count": msg_count,
        "today_token": today_token,
        "today_proactive_count": today_proactive,
    }
