"""宠物 AI 主动消息调度器（决策 AI + 时钟轮询）。

机制（对应需求「主动消息」）：
1. 每隔 PROACTIVE_SCAN_SECONDS 秒扫描一次：用户领养且开启主动唤醒（ai_wake_enabled）的 AI 宠物。
2. 对每个「用户-宠物」：
   - 若当前处于睡觉中 → 跳过。
   - 若距上次消息（last_message_at）已超过后台「主动消息间隔（pet_ai_proactive_interval_min）」分钟，
     且尚未决策出下次主动时间（next_proactive_at 为空）→ 调用决策 AI（pet_ai_service.decide_next_proactive），
     由 AI 基于最近聊天记录 + 用户动态，返回下次主动消息延迟（分钟），写入 next_proactive_at。
   - 若 now >= next_proactive_at → 触发 generate_proactive_message，生成一条符合人设的主动消息，
     并通过 WebSocket 推送给用户（悬浮宠飘窗 / 消息列表实时展示）。
3. 每日主动次数（pet_ai_daily_proactive_max）由 pet_ai_service 内部计数控制，达到上限不再触发。

调度任务与用户聊天共享 DeepSeek 配额时，本调度器不做高并发抢占：
- 每次扫描最多处理 MAX_SCAN_PAIRS 对（默认 8），
- 每对在独立短会话中处理，
避免阻塞用户聊天、抢占 API 配额。
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from loguru import logger

from app.core.database import SessionLocal
from app.core.time_utils import now_utc
from app.services import connection_manager, pet_ai_service, settings_service

# 扫描周期（秒）：时钟轮询粒度
PROACTIVE_SCAN_SECONDS = 15
# 每次扫描最多处理的用户-宠物对数（防止长时间阻塞 / 抢占用户聊天资源）
MAX_SCAN_PAIRS = 8


async def _push_to_user(user_id: int, payload: dict[str, Any]) -> None:
    """通过 WebSocket 向用户推送宠物 AI 主动消息。"""
    try:
        await connection_manager.manager.send_to_user(user_id, payload)
    except Exception as exc:
        logger.warning("[PROACTIVE] 推送失败 user={} err={}", user_id, type(exc).__name__)


def _scan_once() -> list[dict[str, Any]]:
    """一轮扫描（同步，在线程池执行）。返回待推送的主动消息列表。

    Returns:
        [{"user_id": int, "payload": {...}}, ...]
    """
    pushed: list[dict[str, Any]] = []

    # 跨会话拉取「用户-宠物」对（避免长事务）
    with SessionLocal() as db:
        pairs = pet_ai_service.list_all_ai_pets(db)
        if not pairs:
            return pushed

    now = now_utc()
    processed = 0
    for pet, up in pairs:
        if processed >= MAX_SCAN_PAIRS:
            break
        try:
            with SessionLocal() as db:
                from app.models import User

                user = db.get(User, up.user_id)
                if not user:
                    continue
                cfg = settings_service.get_pet_ai_config(db)
                interval_min = max(1, int(cfg.get("pet_ai_proactive_interval_min") or 30))
                idle_threshold = timedelta(minutes=interval_min)
                state = pet_ai_service.get_or_create_state(db, up.user_id, pet.id)
                now = now_utc()

                # 睡觉中 → 跳过
                if state.sleeping_until and state.sleeping_until > now:
                    continue
                # 每日主动次数已达上限 → 跳过
                daily_max = int(cfg.get("pet_ai_daily_proactive_max") or 0)
                if daily_max > 0 and (state.daily_proactive_count or 0) >= daily_max:
                    continue
                # 距上次消息未到「主动消息间隔」 → 跳过
                last_at = state.last_message_at
                if last_at is None or (now - last_at) < idle_threshold:
                    continue

                # 决策出下次主动时间
                if not state.next_proactive_at:
                    delay_min, enabled = pet_ai_service.decide_next_proactive(db, user, pet, up)
                    if not enabled:
                        # 决策 AI 认为当前不宜打扰 → 30 分钟后再看
                        state.next_proactive_at = now + timedelta(minutes=30)
                        db.commit()
                        continue
                    state.next_proactive_at = now + timedelta(minutes=max(5, delay_min))
                    db.commit()
                    continue

                # 到达触发时间 → 生成主动消息
                if state.next_proactive_at <= now:
                    result = pet_ai_service.generate_proactive_message(db, user, pet, up)
                    state.next_proactive_at = None
                    db.commit()
                    if result.get("messages") and not result.get("skipped"):
                        pushed.append({
                            "user_id": up.user_id,
                            "payload": {
                                "type": "pet_ai_proactive",
                                "pet_id": pet.id,
                                "pet_name": pet.name or "小宠物",
                                "messages": result["messages"],
                                "state": result.get("state") or pet_ai_service.state_to_dict(db, up.user_id, pet.id),
                            },
                        })
        except Exception as exc:
            logger.warning("[PROACTIVE] 处理 user={} pet={} 失败 err={}", up.user_id, pet.id, type(exc).__name__)
        processed += 1
    return pushed


async def run_loop() -> None:
    """后台常驻循环：每 PROACTIVE_SCAN_SECONDS 秒扫描一次。"""
    while True:
        await asyncio.sleep(PROACTIVE_SCAN_SECONDS)
        try:
            pushed = await asyncio.to_thread(_scan_once)
            for item in pushed:
                await _push_to_user(item["user_id"], item["payload"])
        except Exception as exc:
            logger.warning("[PROACTIVE] 扫描异常 err={}", type(exc).__name__)
