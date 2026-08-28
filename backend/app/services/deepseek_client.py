"""DeepSeek API 客户端（宠物 AI 引擎专用）。

独立于 deepseek_service.py（内容审核），封装 DeepSeek 官方 API：
- chat: 对话补全（OpenAI 兼容格式，支持工具调用 tools）
- list_models: 拉取可用模型列表（后台模型下拉框用）
- 30 秒超时 + 指数退避重试（最多 3 次）
- 失败时返回结构化错误，调用方友好提示，不抛异常

配置来源：settings_service 的 pet_ai_* 配置项（后台可动态修改）。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from loguru import logger

from app.services import settings_service

# 单次请求超时（秒）
TIMEOUT = 30
# 最大重试次数（网络错误 / 5xx / 429 时重试）
MAX_RETRIES = 3

# 响应中的可重试状态码
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _get_config(db) -> dict[str, Any]:
    """读取宠物 AI 的 DeepSeek 配置。"""
    return settings_service.get_pet_ai_config(db)


class DeepSeekError(Exception):
    """DeepSeek 调用异常（含友好提示信息）。"""

    def __init__(self, message: str, code: str = "deepseek_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def chat(
    db,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **extra: Any,
) -> dict[str, Any]:
    """发送一轮对话请求（非流式）。

    Args:
        messages: OpenAI 风格消息列表 [{"role":"system","content":"..."}, ...]
        tools: DeepSeek 风格工具定义列表，如
            [{"type":"function","function":{"name":"...","description":"...",
              "parameters":{"type":"object","properties":{...},"required":[...]}}}]
        temperature: 采样温度（宠物拟人对话默认 0.7）
        max_tokens: 最大生成 token 数

    Returns:
        {"success": bool, "text": str, "tool_calls": [{"name","arguments"}],
         "finish_reason": str, "usage": dict|None, "error": str|None}

    Raises:
        DeepSeekError: 未配置 API Key / base_url 非法（SSRF 防护）时抛出
    """
    cfg = _get_config(db)
    api_key = str(cfg.get("pet_ai_api_key") or "").strip()
    base_url = str(cfg.get("pet_ai_base_url") or "https://api.deepseek.com/v1").rstrip("/")
    model = str(cfg.get("pet_ai_model") or "deepseek-chat").strip()

    if not api_key:
        raise DeepSeekError("宠物 AI 未配置 DeepSeek API Key，请在后台设置", "not_configured")

    # SSRF 防护：base_url 指向内网/保留地址时拒绝外呼
    from app.services.url_safety import validate_public_url

    url = f"{base_url}/chat/completions"
    if not validate_public_url(url):
        raise DeepSeekError("宠物 AI base_url 配置非法（禁止指向内网地址）", "invalid_base_url")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    payload.update(extra)

    # 深度思考开关（默认关闭）：开启时显式传 thinking=enabled；
    # 关闭时完全不传 thinking（非思考模型默认非思考，避免思考型模型忽略该参数仍返回 reasoning_content，
    # 更避免给不支持该参数的模型误传导致额外 400）。reasoner/r1 推理模型恒思考，不传 thinking。
    if "thinking" not in payload:
        model_lc = model.lower()
        if "reasoner" not in model_lc and "r1" not in model_lc:
            enabled = str(cfg.get("pet_ai_deep_think") or "false").strip().lower() in ("1", "true", "yes", "on", "enabled")
            if enabled:
                payload["thinking"] = {"type": "enabled"}

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return _parse_response(resp.json())
            if resp.status_code in _RETRYABLE_STATUS and attempt < MAX_RETRIES:
                backoff = min(2 ** attempt, 10)
                logger.warning("[DeepSeek] 可重试错误 status={} attempt={}，{}s 后重试",
                               resp.status_code, attempt, backoff)
                time.sleep(backoff)
                continue
            # 4xx 或重试耗尽：返回结构化错误
            detail = (resp.text or "")[:200]
            return {
                "success": False,
                "text": "",
                "tool_calls": [],
                "finish_reason": "http_error",
                "error": f"HTTP {resp.status_code}: {detail}",
                "usage": None,
            }
        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning("[DeepSeek] 请求超时 attempt={} err={}", attempt, type(exc).__name__)
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("[DeepSeek] 请求异常 attempt={} err={}", attempt, type(exc).__name__)
        if attempt < MAX_RETRIES:
            time.sleep(min(2 ** attempt, 10))

    logger.warning("[DeepSeek] 重试耗尽 err={}", type(last_exc).__name__ if last_exc else "unknown")
    return {
        "success": False,
        "text": "",
        "tool_calls": [],
        "finish_reason": "network_error",
        "error": "网络异常，AI 暂时无法响应",
        "usage": None,
    }


def list_models(db) -> dict[str, Any]:
    """从 DeepSeek 官方 API 拉取可用模型列表。

    Returns:
        {"success": bool, "models": [str,...], "error": str|None}
    """
    cfg = _get_config(db)
    api_key = str(cfg.get("pet_ai_api_key") or "").strip()
    base_url = str(cfg.get("pet_ai_base_url") or "https://api.deepseek.com/v1").rstrip("/")
    if not api_key:
        return {"success": False, "models": [], "error": "未配置 DeepSeek API Key"}

    from app.services.url_safety import validate_public_url

    url = f"{base_url}/models"
    if not validate_public_url(url):
        return {"success": False, "models": [], "error": "base_url 配置非法（禁止指向内网地址）"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return {"success": True, "models": models, "error": None}
        return {"success": False, "models": [], "error": f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"}
    except Exception as exc:
        logger.warning("[DeepSeek] 拉取模型列表失败 err={}", type(exc).__name__)
        return {"success": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}


def _parse_response(data: dict[str, Any]) -> dict[str, Any]:
    """解析 DeepSeek 响应，提取文本与工具调用。"""
    try:
        choices = data.get("choices") or []
        if not choices:
            return {
                "success": False, "text": "", "tool_calls": [],
                "finish_reason": "empty", "error": "AI 返回空响应", "usage": None,
            }
        msg = choices[0].get("message", {}) or {}
        text = str(msg.get("content") or "").strip()
        finish_reason = str(choices[0].get("finish_reason") or "")
        # 深度思考模式会返回 reasoning_content。若后续把该 assistant 消息回传给 API（如工具调用循环），
        # DeepSeek 要求必须原样带上 reasoning_content，否则报 400。
        reasoning_content = str(msg.get("reasoning_content") or "").strip()

        tool_calls: list[dict[str, Any]] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {}) or {}
            name = str(fn.get("name") or "")
            args_str = str(fn.get("arguments") or "{}")
            import json as _json

            try:
                args = _json.loads(args_str) if args_str else {}
            except Exception:
                args = {"raw": args_str}
            tool_calls.append({"name": name, "arguments": args})

        usage = data.get("usage") or None
        return {
            "success": True,
            "text": text,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "reasoning_content": reasoning_content,
            "error": None,
            "usage": usage,
        }
    except Exception as exc:
        logger.warning("[DeepSeek] 响应解析失败 err={}", type(exc).__name__)
        return {
            "success": False, "text": "", "tool_calls": [],
            "finish_reason": "parse_error", "error": "AI 响应解析失败", "usage": None,
        }
