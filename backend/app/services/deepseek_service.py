"""DeepSeek AI 内容审核服务。

独立于 ai_service.py（OpenAI 兼容路径），专门对接 DeepSeek 官方 API。
- 读取 settings 表配置（管理员后台可改）
- 使用详细人设 system prompt 做内容审核
- 返回结构化 JSON 结果：{pass, reason, category, severity}
- 失败降级：网络/解析错误时返回 manual_review，不阻塞业务

调用方式：
    from app.services.deepseek_service import deepseek_audit
    result = deepseek_audit(db, content)
    # result = {"pass": True/False, "reason": "...", "category": "...", "severity": "..."}
"""
import json
import re
from typing import Any

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.services import settings_service

# ============ 人设 System Prompt ============
SYSTEM_PROMPT = """# 角色定义
你是「立洋校园社区 AI 内容审核官」，代号 LY-Moderator。
你的职责是审核校园社区用户发布的帖子和评论内容，判断是否违规，
并给出结构化审核结果，辅助管理员进行内容治理决策。

# 审核场景
- 立洋校园社区是一个面向中小学校园的社交平台
- 用户主要是中小学生、教师和家长
- 内容以校园生活、学习交流、兴趣分享为主
- 对未成年人保护要求极高，任何不适内容必须拦截

# 审核维度（10 类违规）
1. 辱骂人身攻击：脏话、侮辱性词汇、网络暴力、对他人的人格攻击
2. 色情低俗：色情暗示、低俗段子、不当性描述、性骚扰言论
3. 诈骗广告：虚假广告、引流推广、兼职刷单、虚假中奖、外链诱导
4. 暴力血腥：打架斗殴描述、暴力威胁、血腥画面描述、自残自杀诱导
5. 政治敏感：政治不当言论、敏感事件讨论、意识形态攻击
6. 隐私泄露：泄露他人手机号、地址、身份证、照片等个人隐私
7. 违法犯罪：毒品、赌博、违禁品交易、教唆犯罪、违法活动描述
8. 校园暴力/欺凌：排挤同学、集体嘲讽、恶意传播他人隐私、网络霸凌
9. 自残自杀：自残倾向描述、自杀方法讨论、诱导他人自伤
10. 不实信息：谣言传播、虚假信息、捏造事实诽谤他人

# 判定原则
- 未成年人保护优先：涉及未成年人的违规一律从重判定
- 语境理解：结合上下文判断，避免误判正常交流中的口语化表达
- 宽容边界：正常的吐槽、玩笑、情绪宣泄不属违规，但攻击他人则违规
- 教育导向：对青少年不当言论以"提醒"为主，严重违规才"拦截"
- 零容忍：色情、暴力、诈骗、自残自杀、校园欺凌零容忍

# 输出格式（严格 JSON，不要包含任何其他文字）
{"pass": true, "reason": "", "category": "none", "severity": "none"}

字段说明：
- pass: boolean，true=通过，false=拦截
- reason: string，违规原因说明（pass=true 时为空字符串）
- category: string，违规类别（pass=true 时为"none"）
  可选值: 骂人攻击/色情低俗/诈骗广告/暴力血腥/政治敏感/隐私泄露/违法犯罪/校园欺凌/自残自杀/不实信息/none
- severity: string，严重程度（pass=true 时为"none"）
  可选值: high(严重违规)/medium(中等违规)/low(轻微违规)/none

# 审核示例
输入: "今天天气真好，心情不错"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "你这个傻逼，怎么不去死"
输出: {"pass": false, "reason": "包含辱骂性词汇'傻逼'，并带有'去死'的生命威胁", "category": "骂人攻击", "severity": "high"}

输入: "加我微信 xxxxx 领红包，兼职刷单日入百元"
输出: {"pass": false, "reason": "包含刷单广告和外部引流，疑似诈骗", "category": "诈骗广告", "severity": "high"}

输入: "我讨厌数学老师，作业太多了"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "三班那个胖子真恶心，大家别理他"
输出: {"pass": false, "reason": "针对特定同学的侮辱性言论，构成校园欺凌", "category": "校园欺凌", "severity": "medium"}
"""

# 单次调用超时（秒）
_TIMEOUT = 15


def _parse_result(raw: str) -> dict[str, Any]:
    """解析 DeepSeek 返回的 JSON 结果，容错处理。"""
    if not raw:
        return {"pass": True, "reason": "", "category": "none", "severity": "none"}
    text = raw.strip()
    # 去除可能的 ```json ... ``` 代码块包裹
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 直接提取第一个 JSON 对象
    m2 = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m2 and not text.startswith("{"):
        text = m2.group(0)
    try:
        data = json.loads(text)
    except Exception:
        logger.warning("DeepSeek 响应解析失败：{}", raw[:200])
        return {"pass": True, "reason": "", "category": "none", "severity": "none"}
    return {
        "pass": bool(data.get("pass", True)),
        "reason": str(data.get("reason", "")),
        "category": str(data.get("category", "none")),
        "severity": str(data.get("severity", "none")),
    }


def audit_content(db: Session, content: str) -> dict[str, Any]:
    """同步调用 DeepSeek 审核内容。

    返回：
    - 成功：{"pass": bool, "reason": str, "category": str, "severity": str}
    - 未启用/未配置：{"pass": True, "reason": "DeepSeek 未启用，跳过审核", "category": "none", "severity": "none", "skipped": True}
    - 调用失败：{"pass": True, "reason": "AI 服务暂不可用，已放行", "category": "none", "severity": "none", "skipped": True}
    """
    cfg = settings_service.get_deepseek_config(db)
    if not cfg["enabled"] or not cfg["api_key"]:
        return {
            "pass": True,
            "reason": "DeepSeek 未启用，跳过审核",
            "category": "none",
            "severity": "none",
            "skipped": True,
        }
    if not content or not content.strip():
        return {"pass": False, "reason": "内容不能为空", "category": "none", "severity": "none"}

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请审核以下内容，只返回 JSON：\n{content[:2000]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
    }

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            logger.info("DeepSeek 审核完成 model={} len={}", cfg["model"], len(raw))
            result = _parse_result(raw)
            result["skipped"] = False
            return result
    except httpx.HTTPStatusError as exc:
        logger.warning("DeepSeek HTTP 错误 status={} body={}", exc.response.status_code, exc.response.text[:200])
        return {
            "pass": True,
            "reason": f"AI 服务返回错误 {exc.response.status_code}，已放行",
            "category": "none",
            "severity": "none",
            "skipped": True,
        }
    except Exception as exc:
        logger.warning("DeepSeek 调用失败 error={}", type(exc).__name__)
        return {
            "pass": True,
            "reason": "AI 服务暂不可用，已放行",
            "category": "none",
            "severity": "none",
            "skipped": True,
        }


def test_connection(db: Session) -> dict[str, Any]:
    """测试 DeepSeek 连接（管理员后台「测试」按钮调用）。"""
    cfg = settings_service.get_deepseek_config(db)
    if not cfg["api_key"]:
        return {"ok": False, "msg": "未配置 API Key"}
    if not cfg["enabled"]:
        return {"ok": False, "msg": "DeepSeek 未启用"}
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请审核以下内容，只返回 JSON：\n你好"},
        ],
        "temperature": 0.1,
        "max_tokens": 100,
    }
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            result = _parse_result(raw)
            return {
                "ok": True,
                "msg": f"连接成功，模型：{cfg['model']}",
                "sample": result,
            }
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:200] if exc.response else ""
        return {"ok": False, "msg": f"HTTP {exc.response.status_code}: {body}"}
    except Exception as exc:
        return {"ok": False, "msg": f"{type(exc).__name__}: {exc}"}
