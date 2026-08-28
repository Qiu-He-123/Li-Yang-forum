"""宠物 AI（DeepSeek 引擎）路由。

用户侧（/pet-ai）：
- POST /pet-ai/{pet_id}/chat      用户发消息 → AI 分段回复（含工具调用卡片/睡觉状态）
- GET  /pet-ai/{pet_id}/messages  聊天记录（前端回显，含工具卡片 meta）
- GET  /pet-ai/{pet_id}/state     AI 状态（是否睡觉/今日 token/主动次数等）
- POST /pet-ai/activity           上报用户动作（看帖子/列表/商城，注入 AI 上下文）
- POST /pet-ai/{pet_id}/event     事件触发（浏览超阈值时后端模拟系统消息让 AI 说话）

管理侧（/admin/pet-ai）：
- GET  /admin/pet-ai/config       宠物 AI 完整配置（后台编辑）
- PUT  /admin/pet-ai/config       更新配置（API Key/模型/限额/事件/睡眠等）
- GET  /admin/pet-ai/models       从 DeepSeek 官方 API 拉取模型列表（下拉框）
- POST /admin/pet-ai/test         测试 DeepSeek 连接
- GET  /admin/pet-ai/stats        统计（AI 宠物数/消息量/今日 token/主动次数）
- PATCH /admin/pet-ai/products/{id}/ai  更新单只宠物的 AI 设定（宠物商城弹窗复用）
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user
from app.core.database import get_db
from app.models import Admin, PetProduct, User
from app.schemas.common import ok
from app.services import deepseek_client, pet_ai_service, settings_service

router = APIRouter(prefix="/pet-ai", tags=["pet-ai"])
admin_router = APIRouter(prefix="/admin/pet-ai", tags=["admin-pet-ai"])


# ==================== 用户侧 ====================


class ChatPayload(BaseModel):
    """用户发送给宠物的消息。"""

    text: str = Field(..., min_length=1, max_length=1000, description="消息内容")


@router.post("/{pet_id}/chat")
def pet_ai_chat(
    pet_id: int,
    payload: ChatPayload,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """用户发消息 → AI 回复。

    返回 messages 列表（含 assistant 分段、tool 工具卡片），以及当前睡觉状态。
    若宠物正在睡觉，直接返回 400「宠物正在睡觉，等它醒了再聊吧」（前端禁用输入框）。
    """
    try:
        result = pet_ai_service.chat_with_pet(db, user, pet_id, payload.text, source="user")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务异常：{exc}") from None
    return ok(result)


@router.get("/conversations")
def pet_ai_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """宠物会话列表（消息中心展示所有开启 AI 的宠物，含最后一条消息/时间/睡觉状态）。"""
    return ok(pet_ai_service.conversations_to_dict(db, user))


@router.get("/{pet_id}/messages")
def pet_ai_messages(
    pet_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """聊天记录（前端回显用）。拉取即视为已读，同时清除该宠物的未读标记。"""
    pet_ai_service.mark_messages_read(db, user.id, pet_id)
    db.commit()
    return ok({"messages": pet_ai_service.history_to_dict(db, user.id, pet_id, limit)})


@router.post("/{pet_id}/read")
def pet_ai_mark_read(
    pet_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """将该宠物所有未读 AI 消息标记为已读（清除消息中心红点）。"""
    pet_ai_service.mark_messages_read(db, user.id, pet_id)
    db.commit()
    return ok({})


@router.get("/{pet_id}/state")
def pet_ai_state(
    pet_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """宠物 AI 状态：是否睡觉/睡醒时间/今日 token/剩余/主动次数等。"""
    return ok(pet_ai_service.state_to_dict(db, user.id, pet_id))


class ActivityPayload(BaseModel):
    """用户动作上报（用于 AI 上下文注入 / 事件触发决策）。"""

    action: str = Field(..., description="动作类型，如 post_detail/post_list/pet_shop/send_message/join_gathering")
    detail: str = Field(default="", max_length=500, description="动作详情（标题/标签名等）")


@router.post("/activity")
def pet_ai_record_activity(
    payload: ActivityPayload,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """上报用户动作。仅登录用户上报，写入 user_activities 供 AI 理解上下文。"""
    pet_ai_service.record_activity(db, user.id, payload.action, payload.detail)
    return ok({})


@router.get("/event-config")
def pet_ai_event_config(
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
) -> dict:
    """返回事件触发阈值（用户侧，供前端决定何时上报浏览时长触发 AI 说话）。"""
    cfg = settings_service.get_pet_ai_config(db)
    enabled = str(cfg.get("pet_ai_enabled") or "").strip().lower() in ("true", "1", "yes", "on")
    return ok({
        "enabled": enabled,
        "post_detail": [
            int(cfg.get("pet_ai_event_post_detail_min") or 30),
            int(cfg.get("pet_ai_event_post_detail_max") or 90),
        ],
        "post_list": [
            int(cfg.get("pet_ai_event_post_list_min") or 60),
            int(cfg.get("pet_ai_event_post_list_max") or 180),
        ],
        "pet_shop": [
            int(cfg.get("pet_ai_event_pet_shop_min") or 60),
            int(cfg.get("pet_ai_event_pet_shop_max") or 180),
        ],
    })


class EventPayload(BaseModel):
    """事件触发载荷。"""

    pet_id: int = Field(..., description="宠物 id")
    event_type: str = Field(..., description="事件类型：post_detail/post_list/pet_shop/自定义")
    detail: str = Field(default="", max_length=500, description="场景描述（标题/标签名）")
    seconds: int = Field(default=0, ge=0, description="持续时长（秒）")


@router.post("/event")
def pet_ai_trigger_event(
    payload: EventPayload,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """事件触发：用户浏览帖子详情/列表/商城超过阈值时，模拟系统消息让 AI 说一句话。

    前端在浏览时长达到后台配置范围内时调用；由后端判断是否计入每日主动次数上限。
    """
    result = pet_ai_service.trigger_event(db, user, payload.pet_id, payload.event_type, payload.detail, payload.seconds)
    return ok(result)


# ==================== 管理侧 ====================


class PetAiConfigPayload(BaseModel):
    """后台可编辑的全部宠物 AI 配置项（只传需要修改的键）。"""

    pet_ai_enabled: bool | None = None
    pet_ai_api_key: str | None = None
    pet_ai_base_url: str | None = None
    pet_ai_model: str | None = None
    pet_ai_proactive_interval_min: int | None = None
    pet_ai_daily_token_limit: int | None = None
    pet_ai_token_warn_threshold: int | None = None
    pet_ai_gift_coins_single: int | None = None
    pet_ai_gift_coins_daily: int | None = None
    pet_ai_affinity_add_single: int | None = None
    pet_ai_affinity_add_daily: int | None = None
    pet_ai_affinity_sub_single: int | None = None
    pet_ai_affinity_sub_daily: int | None = None
    pet_ai_sleep_min: int | None = None
    pet_ai_sleep_max: int | None = None
    pet_ai_event_post_detail_min: int | None = None
    pet_ai_event_post_detail_max: int | None = None
    pet_ai_event_post_list_min: int | None = None
    pet_ai_event_post_list_max: int | None = None
    pet_ai_event_pet_shop_min: int | None = None
    pet_ai_event_pet_shop_max: int | None = None
    pet_ai_event_cooldown_min: int | None = None
    pet_ai_daily_proactive_max: int | None = None
    pet_ai_user_actions_count: int | None = None
    pet_ai_default_persona: str | None = None


@admin_router.get("/config")
def admin_pet_ai_config_get(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """读取宠物 AI 完整配置（含描述与默认值）。API Key 返回脱敏掩码。"""
    cfg = settings_service.get_pet_ai_config(db)
    api_key = str(cfg.get("pet_ai_api_key") or "")
    cfg["pet_ai_api_key"] = _mask_key(api_key) if api_key else ""
    cfg["pet_ai_api_key_configured"] = bool(api_key)
    return ok(cfg)


@admin_router.put("/config")
def admin_pet_ai_config_update(
    payload: PetAiConfigPayload,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """更新宠物 AI 配置（只更新传入的键，其余保持不变）。"""
    data = payload.model_dump(exclude_none=True)
    settings_service.update_pet_ai_config(db, data)
    db.commit()
    cfg = settings_service.get_pet_ai_config(db)
    api_key = str(cfg.get("pet_ai_api_key") or "")
    cfg["pet_ai_api_key"] = _mask_key(api_key) if api_key else ""
    cfg["pet_ai_api_key_configured"] = bool(api_key)
    return ok(cfg)


@admin_router.get("/models")
def admin_pet_ai_models(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """从 DeepSeek 官方 API 动态拉取模型列表（后台模型下拉框用）。"""
    result = deepseek_client.list_models(db)
    return ok(result)


@admin_router.post("/test")
def admin_pet_ai_test(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """测试 DeepSeek 连接：拉一次模型列表确认 API Key 有效。"""
    result = deepseek_client.list_models(db)
    if result.get("success"):
        return ok({"ok": True, "msg": f"连接成功，共获取 {len(result['models'])} 个模型", "models": result["models"]})
    return ok({"ok": False, "msg": result.get("error") or "连接失败"})


@admin_router.get("/stats")
def admin_pet_ai_stats(
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """宠物 AI 统计（后台查看）。"""
    return ok(pet_ai_service.admin_stats(db))


class PetAiProductUpdate(BaseModel):
    """单只宠物的 AI 设定（宠物商城管理弹窗复用）。"""

    ai_enabled: bool | None = None
    ai_wake_enabled: bool | None = None
    ai_persona: str | None = None
    game_speech: dict | str | None = None


@admin_router.patch("/products/{product_id}/ai")
def admin_pet_ai_product_update(
    product_id: int,
    payload: PetAiProductUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(admin_user),
) -> dict:
    """更新单只宠物的 AI 设定（ai_enabled / ai_wake_enabled / ai_persona / game_speech）。"""
    product = db.get(PetProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="宠物商品不存在")
    data = payload.model_dump(exclude_none=True)
    for key in ("ai_enabled", "ai_wake_enabled", "ai_persona"):
        if key in data:
            setattr(product, key, data[key])
    if "game_speech" in data:
        import json

        gs = data["game_speech"]
        product.game_speech = json.dumps(gs, ensure_ascii=False) if isinstance(gs, dict) else (gs or None)
    db.commit()
    return ok({
        "id": product.id,
        "ai_enabled": product.ai_enabled,
        "ai_wake_enabled": product.ai_wake_enabled,
        "ai_persona": product.ai_persona,
        "game_speech": product.game_speech,
    })


def _mask_key(key: str) -> str:
    """API Key 脱敏：只显示前 4 位和后 4 位。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
