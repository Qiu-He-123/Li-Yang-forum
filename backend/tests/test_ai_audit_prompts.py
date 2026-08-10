"""DeepSeek 场景化审核 prompt 回归测试。

背景（用户反馈的两个问题）：
1. "老装p" 等谐音/缩写辱骂漏检 → 旧版通用 prompt 只示例了"傻逼"，
   没有强调识别谐音/缩写/方言变体
2. 正常短评论（"是的"、"好"）被误判灌水 → 旧版把帖子的"无信息量即灌水"
   规则套用到评论，而短回复是评论的正常形态

修复：帖子 / 评论 / 漂流瓶 / 通用 四套独立 prompt，场景不同规则不同。
"""
import json

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.services import deepseek_service, settings_service


@pytest.fixture(autouse=True)
def _reset_deepseek_settings():
    """测试结束后恢复 DeepSeek 未启用状态，避免影响其他测试模块。"""
    yield
    with SessionLocal() as db:
        settings_service.set_setting(db, "deepseek_enabled", "false")
        settings_service.set_setting(db, "deepseek_api_key", "")


def _enable_deepseek(monkeypatch, db) -> None:
    """开启 DeepSeek 配置并把 httpx.Client 替换为假客户端。"""
    settings_service.set_setting(db, "deepseek_enabled", "true")
    settings_service.set_setting(db, "deepseek_api_key", "sk-test")


def _fake_audit(monkeypatch, content: str, content_type: str) -> tuple[dict, dict]:
    """调用 audit_content，返回 (结果, 捕获的请求 payload)。"""
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"pass": True, "reason": "", "category": "none", "severity": "none"},
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(deepseek_service.httpx, "Client", lambda *a, **k: FakeClient())

    with SessionLocal() as db:
        _enable_deepseek(monkeypatch, db)
        result = deepseek_service.audit_content(db, content, content_type)
    return result, captured


def test_prompts_are_scenario_specific():
    """四套 prompt 各自包含场景专属规则，不再共用一套。"""
    post = deepseek_service.SYSTEM_PROMPTS["post"]
    comment = deepseek_service.SYSTEM_PROMPTS["comment"]
    bottle = deepseek_service.SYSTEM_PROMPTS["bottle"]

    # 帖子：标题 + 正文一起审核
    assert "标题" in post
    # 评论：明确短回复不算灌水 + 谐音辱骂示例
    assert "是的" in comment and "好" in comment
    assert "老装p" in comment
    assert "灌水仅指" in comment
    # 漂流瓶：陌生人社交场景
    assert "漂流瓶" in bottle
    assert "加微信" in bottle
    # 三套 prompt 不应完全相同
    assert len({post, comment, bottle}) == 3


def test_comment_prompt_does_not_flag_short_replies_as_spam():
    """评论 prompt 必须把"是的""好"等正常短回复排除在灌水之外。"""
    comment = deepseek_service.SYSTEM_PROMPTS["comment"]
    assert '"是的"' in comment
    assert '"好"' in comment
    assert "不属灌水" in comment or "不属于灌水" in comment


def test_comment_prompt_covers_slang_insults():
    """评论 prompt 必须覆盖谐音/缩写辱骂（老装p 等）。"""
    comment = deepseek_service.SYSTEM_PROMPTS["comment"]
    for token in ("老装p", "傻x", "SB", "nmsl"):
        assert token in comment


def test_audit_content_uses_scenario_prompt(monkeypatch):
    """按 content_type 使用对应 prompt 发送请求。"""
    for content_type in ("post", "comment", "bottle"):
        _, captured = _fake_audit(monkeypatch, "测试内容", content_type)
        messages = captured["payload"]["messages"]
        system = messages[0]["content"]
        user = messages[1]["content"]
        assert system == deepseek_service.SYSTEM_PROMPTS[content_type]
        assert deepseek_service.SCENARIO_LABELS[content_type] in user


def test_unknown_content_type_falls_back_to_generic(monkeypatch):
    """未知场景回退到通用 prompt。"""
    _, captured = _fake_audit(monkeypatch, "测试内容", "unknown_scene")
    system = captured["payload"]["messages"][0]["content"]
    assert system == deepseek_service.SYSTEM_PROMPTS["generic"]
