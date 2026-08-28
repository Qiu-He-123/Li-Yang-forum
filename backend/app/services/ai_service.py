"""AI 服务层。

T7-1 / T7-2 / Bug B / Bug C 修复：
- _chat 超时从 30s 改为 5s，重试从 3 次改为 1 次，网络错误立即返回空。
- check_image 直接返回 pass=True（原逻辑把 URL 字符串当 prompt 喂文本 LLM，无意义且阻塞 90 秒）。
- check_text / generate_tags / summary 失败时降级返回安全默认值，不阻塞业务。

T8-1 性能优化（根因修复）：
- 系统环境变量 OPENAI_API_KEY 会覆盖 .env 中的空值，导致 AI 调用尝试连接 api.openai.com。
- 由于网络不可达，每次调用超时 5 秒，发帖 2 次 AI 调用 = 10 秒，评论 1 次 = 5 秒。
- 引入熔断器（circuit breaker）：首次失败后 5 分钟内跳过所有 AI 调用，立即降级。
- 超时从 5s 降为 2s，首次失败也只需 2 秒（而非 5 秒）。
- 添加 last_status 字段，让调用方知道 AI 是否被跳过及原因。
"""
import time
from typing import Any

import httpx
from loguru import logger

from app.core.config import get_settings
from app.services.url_safety import validate_public_url

# 熔断器状态
_circuit_open_until: float = 0.0  # 熔断打开的截止时间戳（0 表示未熔断）
_circuit_failure_count: int = 0  # 连续失败次数
_CIRCUIT_RESET_SECONDS = 300  # 熔断后 5 分钟内跳过所有 AI 调用
_AI_TIMEOUT = 2  # 单次 AI 调用超时 2 秒（从 5s 降低）


class AIService:
    def _is_circuit_open(self) -> bool:
        """检查熔断器是否打开（AI 不可用）。"""
        global _circuit_open_until
        return time.time() < _circuit_open_until

    def _trip_circuit(self, reason: str) -> None:
        """触发熔断：记录失败，5 分钟内跳过所有 AI 调用。"""
        global _circuit_open_until, _circuit_failure_count
        _circuit_failure_count += 1
        _circuit_open_until = time.time() + _CIRCUIT_RESET_SECONDS
        logger.warning(
            "AI 熔断器打开：{}，未来 {} 秒内跳过所有 AI 调用（累计失败 {} 次）",
            reason,
            _CIRCUIT_RESET_SECONDS,
            _circuit_failure_count,
        )

    def get_status(self) -> dict[str, Any]:
        """返回 AI 服务当前状态，供调用方告知用户。"""
        settings = get_settings()
        if not settings.openai_api_key:
            return {"available": False, "reason": "未配置 OPENAI_API_KEY，AI 审核已跳过"}
        if self._is_circuit_open():
            remaining = int(_circuit_open_until - time.time())
            return {
                "available": False,
                "reason": f"AI 服务不可达，已临时降级（{remaining} 秒后重试）",
            }
        return {"available": True, "reason": ""}

    async def _chat(self, prompt: str) -> str:
        # 熔断器打开时直接返回空，不发起网络请求
        if self._is_circuit_open():
            logger.debug("AI 调用被熔断器跳过")
            return ""

        settings = get_settings()
        if not settings.openai_api_key:
            return ""

        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        # SSRF 防护：base_url 指向内网/保留地址时拒绝外呼
        if not validate_public_url(url):
            logger.warning("[SSRF] AI base_url 禁止指向内网地址，已拒绝: {}", settings.openai_base_url)
            self._trip_circuit("SSRF blocked base_url")
            return ""
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        payload: dict[str, Any] = {
            "model": settings.ai_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        # T8-1：超时从 5s 降为 2s，熔断后不再重试
        try:
            async with httpx.AsyncClient(timeout=_AI_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.info("AI request ok provider={}", settings.ai_provider)
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            error_type = type(exc).__name__
            logger.warning("AI request failed provider={} error={}", settings.ai_provider, error_type)
            # 触发熔断：5 分钟内跳过所有 AI 调用
            self._trip_circuit(f"{error_type}: {exc}"[:100])
            return ""

    async def check_text(self, content: str) -> dict[str, Any]:
        if not content.strip():
            return {"pass": False, "reason": "内容不能为空"}  # nosec B105
        result = await self._chat(f"审核校园社区内容是否包含辱骂、色情、诈骗、恶意广告。只返回 pass 或 block：{content[:1000]}")
        if not result:
            # T7-1：AI 不可用时放行，不阻塞发帖/评论
            logger.info("AI check_text unavailable, allowing content")
            return {"pass": True}  # nosec B105
        if "block" in result.lower():
            return {"pass": False, "reason": "内容疑似违规，请修改后再发布"}  # nosec B105
        return {"pass": True}  # nosec B105

    async def check_image(self, image: str) -> dict[str, Any]:
        # T7-2 / Bug C：图片审核直接放行。
        # 原实现把 URL 字符串当 prompt 喂文本 LLM，无意义且阻塞 90 秒。
        # TODO: Phase 后续接入视觉模型做真正的图片内容审核。
        return {"pass": True}  # nosec B105

    async def generate_tags(self, content: str) -> list[str]:
        result = await self._chat(f"为校园帖子生成最多 3 个中文标签，逗号分隔：{content[:1000]}")
        if not result:
            # T7-1：AI 不可用时返回空数组
            return []
        return [tag.strip(" #，,") for tag in result.replace("，", ",").split(",") if tag.strip()][:3]

    async def summary(self, content: str) -> str:
        result = await self._chat(f"用一句话总结举报内容，避免包含隐私原文：{content[:1000]}")
        return result or ""

    async def chat(self, prompt: str) -> str:
        return await self._chat(prompt)


ai_service = AIService()
