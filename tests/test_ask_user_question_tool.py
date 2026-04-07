"""ask_user_question 内建工具定义测试。"""

from __future__ import annotations

from typing import Any

from nini.agent.runner import AgentRunner


class _EmptyRegistry:
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return []


class _AskToolRegistry:
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "ask_user_question",
                    "description": "自定义实现",
                    "parameters": {"type": "object"},
                },
            }
        ]


async def _dummy_handler(*_args: object, **_kwargs: object) -> dict[str, str]:
    return {}


def test_runner_injects_builtin_ask_user_question_tool_when_handler_present() -> None:
    """有 handler 时，ask_user_question 应注入工具列表。"""
    runner = AgentRunner(tool_registry=_EmptyRegistry(), ask_user_question_handler=_dummy_handler)
    tools = runner._get_tool_definitions()  # noqa: SLF001
    names = [
        item["function"]["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    assert "ask_user_question" in names


def test_runner_does_not_inject_ask_user_question_without_handler() -> None:
    """无 handler（子 Agent 场景）时，ask_user_question 不得注入工具列表。"""
    runner = AgentRunner(tool_registry=_EmptyRegistry())
    tools = runner._get_tool_definitions()  # noqa: SLF001
    names = [
        item["function"]["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    assert "ask_user_question" not in names


def test_runner_does_not_duplicate_ask_user_question_tool() -> None:
    """注册表已含 ask_user_question 时，不应重复注入（无论是否有 handler）。"""
    runner = AgentRunner(tool_registry=_AskToolRegistry(), ask_user_question_handler=_dummy_handler)
    tools = runner._get_tool_definitions()  # noqa: SLF001
    names = [
        item["function"]["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    assert names.count("ask_user_question") == 1


def test_builtin_ask_user_question_tool_describes_label_and_description_roles() -> None:
    runner = AgentRunner(tool_registry=_EmptyRegistry())
    tool = runner._ask_user_question_tool_definition()  # noqa: SLF001
    function = tool["function"]
    question_item = function["parameters"]["properties"]["questions"]["items"]
    option_item = question_item["properties"]["options"]["items"]["properties"]

    assert "短标题" in function["description"]
    assert "短标题" in option_item["label"]["description"]
    assert "A/B/C" in option_item["label"]["description"]
    assert "消除歧义" in option_item["description"]["description"]
    assert "不能仅重复 label" in option_item["description"]["description"]


def test_normalize_ask_user_question_rejects_placeholder_label() -> None:
    payload = {
        "questions": [
            {
                "question": "请选择图表输出形式",
                "options": [
                    {"label": "A", "description": "生成交互式图表"},
                    {"label": "B", "description": "生成静态图片"},
                ],
            }
        ]
    }

    questions, error = AgentRunner._normalize_ask_user_question_questions(payload)  # noqa: SLF001

    assert questions is None
    assert "占位标题" in error


def test_normalize_ask_user_question_rejects_duplicate_description() -> None:
    payload = {
        "questions": [
            {
                "question": "请选择图表输出形式",
                "options": [
                    {"label": "交互式图表", "description": "交互式图表"},
                    {"label": "静态图片", "description": "导出静态图片文件"},
                ],
            }
        ]
    }

    questions, error = AgentRunner._normalize_ask_user_question_questions(payload)  # noqa: SLF001

    assert questions is None
    assert "description 不能与 label 完全相同" in error
