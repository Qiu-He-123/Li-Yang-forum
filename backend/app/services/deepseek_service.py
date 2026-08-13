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
from app.services.url_safety import validate_public_url

# ============ 人设 System Prompt（按内容场景拆分） ============
# 不同内容类型的语境差异很大，共用一套 prompt 会导致：
# - 评论的简短正常回复（"是的"、"好"）被误判为灌水
# - 谐音/缩写/方言辱骂（如"老装p"）漏检
# 因此按帖子 / 评论 / 漂流瓶 / 通用四套 prompt 分开审核。

_COMMON_CATEGORIES = """# 审核维度（11 类违规）
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
11. 灌水无意义：无实际信息量的低质量内容（按场景判定，评论中的简短正常回复除外）"""

_COMMON_OUTPUT = """# 输出格式（严格 JSON，不要包含任何其他文字）
{"pass": true, "reason": "", "category": "none", "severity": "none"}

字段说明：
- pass: boolean，true=通过，false=拦截
- reason: string，违规原因说明（pass=true 时为空字符串）
- category: string，违规类别（pass=true 时为"none"）
  可选值: 骂人攻击/色情低俗/诈骗广告/暴力血腥/政治敏感/隐私泄露/违法犯罪/校园欺凌/自残自杀/不实信息/灌水水帖/none
- severity: string，严重程度（pass=true 时为"none"）
  可选值: high(严重违规)/medium(中等违规)/low(轻微违规)/none"""


SYSTEM_PROMPT_POST = """# 角色定义
你是「立洋校园社区 AI 内容审核官」，代号 LY-Moderator。
你的职责是审核用户发布的**帖子**（标题 + 正文），判断是否违规，
并给出结构化审核结果，辅助管理员进行内容治理决策。

# 审核场景
- 立洋校园社区是一个面向中小学校园的社交平台
- 用户主要是中小学生、教师和家长
- 帖子以校园生活、学习交流、兴趣分享为主
- 对未成年人保护要求极高，任何不适内容必须拦截

@@CATEGORIES@@

# 帖子特有规则（灌水判定）
- 只有「标题和正文都缺乏实质信息」才算灌水：如标题仅"12"、正文仅"......"、
  纯标点符号、无意义重复刷屏、凑字数
- 正常的校园交流、提问、分享、吐槽不属于灌水
- 标题和正文都要审核：标题违规同样拦截

# 判定原则
- 未成年人保护优先：涉及未成年人的违规一律从重判定
- 辱骂攻击不仅限于标准脏话，还包括谐音、缩写、拼音首字母、方言、emoji 变体
  （如"老装p/老装逼"、"傻x/SB"、"脑残"、"滚"、"去死"），只要是针对他人的人格攻击都要拦截
- 语境理解：结合上下文判断，避免误判正常交流中的口语化表达
- 宽容边界：正常的吐槽、玩笑、情绪宣泄不属违规，但攻击他人则违规
- 教育导向：对青少年不当言论以"提醒"为主，严重违规才"拦截"
- 零容忍：色情、暴力、诈骗、自残自杀、校园欺凌零容忍

@@OUTPUT@@

# 审核示例
输入: "标题：今天天气真好\n内容：心情不错，去操场打球了"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "标题：12\n内容：......"
输出: {"pass": false, "reason": "标题和正文均无实质信息，属于灌水", "category": "灌水水帖", "severity": "low"}

输入: "标题：笑死\n内容：那个傻逼老装p，真恶心"
输出: {"pass": false, "reason": "包含侮辱性词'傻逼''老装p'，针对他人人身攻击", "category": "骂人攻击", "severity": "medium"}

输入: "我讨厌数学老师，作业太多了"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}
""".replace("@@CATEGORIES@@", _COMMON_CATEGORIES).replace("@@OUTPUT@@", _COMMON_OUTPUT)


SYSTEM_PROMPT_COMMENT = """# 角色定义
你是「立洋校园社区 AI 内容审核官」，代号 LY-Moderator。
你的职责是审核用户发表的**评论**，判断是否违规，并给出结构化审核结果。

# 审核场景
- 评论是帖子下面的简短对话回复，通常只有几个字
- 用户主要是中小学生、教师和家长，未成年人保护要求极高

# 评论特有规则（非常重要）
1. 简短正常回复一律通过，不属灌水：
   "是的"、"好"、"好的"、"收到"、"哈哈"、"哈哈哈"、"赞同"、"同意"、"对"、
   "+1"、"666"、"沙发"、"顶"、表情符号等都属于正常交流
2. 灌水仅指：纯符号/纯标点、无意义乱敲（如"asdfgh"）、同一内容反复刷屏、
   复制粘贴刷屏、广告引流
3. 辱骂攻击必须拦截，包括谐音、缩写、拼音首字母、方言、emoji 变体：
   如"老装p/老装逼/装b"、"傻x/SB"、"脑残/脑瘫"、"滚"、"去死"、"nmsl"等
4. 针对特定同学/老师/用户的嘲讽、起外号、集体排挤属于校园欺凌，必须拦截
5. 零容忍：色情低俗、诈骗广告、隐私泄露、自残自杀

@@CATEGORIES@@

# 判定原则
- 未成年人保护优先：涉及未成年人的违规一律从重判定
- 语境理解：评论脱离帖子上下文时，宁可放行也不误伤正常短回复；
  但内容本身明显在攻击他人时必须拦截
- 零容忍：色情、暴力、诈骗、自残自杀、校园欺凌零容忍

@@OUTPUT@@

# 审核示例
输入: "是的"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "好"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "哈哈哈 笑死我了"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "老装p 你也就这点本事"
输出: {"pass": false, "reason": "使用谐音辱骂词'老装p'攻击他人", "category": "骂人攻击", "severity": "medium"}

输入: "大家别理三班那个傻x，他脑子有问题"
输出: {"pass": false, "reason": "针对特定同学的侮辱和排挤，构成校园欺凌", "category": "校园欺凌", "severity": "medium"}
""".replace("@@CATEGORIES@@", _COMMON_CATEGORIES).replace("@@OUTPUT@@", _COMMON_OUTPUT)


SYSTEM_PROMPT_BOTTLE = """# 角色定义
你是「立洋校园社区 AI 内容审核官」，代号 LY-Moderator。
你的职责是审核用户投放的**漂流瓶**内容，判断是否违规，并给出结构化审核结果。

# 审核场景
- 漂流瓶是校园社区里的陌生人匿名社交功能：用户写一段话投出去，可能被陌生人捡到
- 内容是自我介绍、心愿、树洞倾诉、交友期望等，短句（如"想找人聊聊天"、"你好呀"）完全正常
- 用户主要是中小学生、教师和家长，未成年人保护要求极高

# 漂流瓶特有规则
1. 简短内容正常，不属灌水；灌水仅指纯符号、无意义乱码、同一内容重复投放
2. 重点拦截：
   - 骚扰/约炮/色情暗示与引流（如"加微信xxx约吗"、"处对象私聊"）
   - 辱骂攻击（含谐音/缩写变体，如"老装p"、"傻x"）
   - 泄露联系方式或他人隐私（微信号、QQ、手机号、地址）
   - 诈骗广告、赌博、违法犯罪、自残自杀
3. 交友表达本身不违规（"想认识新朋友"、"希望找到志同道合的人"），
   有性暗示或引流的才违规

@@CATEGORIES@@

# 判定原则
- 未成年人保护优先：涉及未成年人的违规一律从重判定
- 陌生人社交场景对骚扰、色情引流、隐私泄露零容忍

@@OUTPUT@@

# 审核示例
输入: "希望认识新朋友，一起打篮球"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "加我微信xxxxx，晚上一起出来玩"
输出: {"pass": false, "reason": "泄露联系方式并带有线下邀约暗示，疑似骚扰引流", "category": "色情低俗", "severity": "high"}

输入: "呵呵"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}
""".replace("@@CATEGORIES@@", _COMMON_CATEGORIES).replace("@@OUTPUT@@", _COMMON_OUTPUT)


# 通用场景（管理员在线试审默认使用，兼容旧接口）
SYSTEM_PROMPT = """# 角色定义
你是「立洋校园社区 AI 内容审核官」，代号 LY-Moderator。
你的职责是审核校园社区用户发布的内容，判断是否违规，并给出结构化审核结果。

# 审核场景
- 立洋校园社区是面向中小学校园的社交平台，用户主要是中小学生、教师和家长
- 内容可能是帖子、评论或短消息，未成年人保护要求极高

@@CATEGORIES@@

# 判定原则
- 未成年人保护优先：涉及未成年人的违规一律从重判定
- 辱骂攻击包括谐音、缩写、方言变体（如"老装p/装b"、"傻x/SB"），针对他人人格攻击必须拦截
- 简短口语内容（如"好的"、"哈哈"）属于正常交流，不算灌水
- 零容忍：色情、暴力、诈骗、自残自杀、校园欺凌零容忍

@@OUTPUT@@

# 审核示例
输入: "好的，我知道了"
输出: {"pass": true, "reason": "", "category": "none", "severity": "none"}

输入: "你这个傻逼老装p，怎么不去死"
输出: {"pass": false, "reason": "包含辱骂性词汇'傻逼''老装p'，并带有'去死'的生命威胁", "category": "骂人攻击", "severity": "high"}

输入: "标题：12\\n内容：......"
输出: {"pass": false, "reason": "标题和正文均无实质信息，属于灌水", "category": "灌水水帖", "severity": "low"}
""".replace("@@CATEGORIES@@", _COMMON_CATEGORIES).replace("@@OUTPUT@@", _COMMON_OUTPUT)

# 场景 → prompt 映射
SYSTEM_PROMPTS = {
    "post": SYSTEM_PROMPT_POST,
    "comment": SYSTEM_PROMPT_COMMENT,
    "bottle": SYSTEM_PROMPT_BOTTLE,
    "generic": SYSTEM_PROMPT,
}

# 场景中文标签
SCENARIO_LABELS = {
    "post": "帖子（标题+正文）",
    "comment": "评论",
    "bottle": "漂流瓶",
    "generic": "通用文本",
}

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


def audit_content(db: Session, content: str, content_type: str = "generic") -> dict[str, Any]:
    """同步调用 DeepSeek 审核内容（按内容场景使用对应 prompt）。

    Args:
        content_type: post（帖子）/ comment（评论）/ bottle（漂流瓶）/ generic（通用）

    返回：
    - 成功：{"pass": bool, "reason": str, "category": str, "severity": str}
    - 未启用/未配置：{"pass": True, "reason": "DeepSeek 未启用，跳过审核", "category": "none", "severity": "none", "skipped": True}
    - 调用失败：{"pass": True, "reason": "AI 服务暂不可用，已放行", "category": "none", "severity": "none", "skipped": True}
    """
    content_type = content_type if content_type in SYSTEM_PROMPTS else "generic"
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
    # SSRF 防护：base_url 指向内网/保留地址时拒绝外呼
    if not validate_public_url(url):
        logger.warning("[SSRF] DeepSeek base_url 禁止指向内网地址，已拒绝: {}", cfg["base_url"])
        return {
            "pass": True,
            "reason": "AI base_url 配置非法（禁止指向内网），已放行",
            "category": "none",
            "severity": "none",
            "skipped": True,
        }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPTS[content_type]},
            {"role": "user", "content": f"请按「{SCENARIO_LABELS[content_type]}」场景审核以下内容，只返回 JSON：\n{content[:2000]}"},
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
            logger.info("DeepSeek 审核完成 model={} scenario={} len={}", cfg["model"], content_type, len(raw))
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
    if not validate_public_url(url):
        return {"ok": False, "msg": "base_url 禁止指向内网地址（SSRF 防护）"}
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
