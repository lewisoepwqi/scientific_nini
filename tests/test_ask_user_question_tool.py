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


def test_runner_injects_builtin_ask_user_question_tool() -> None:
    runner = AgentRunner(skill_registry=_EmptyRegistry())
    tools = runner._get_tool_definitions()  # noqa: SLF001
    names = [
        item["function"]["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    assert "ask_user_question" in names


def test_runner_does_not_duplicate_ask_user_question_tool() -> None:
    runner = AgentRunner(skill_registry=_AskToolRegistry())
    tools = runner._get_tool_definitions()  # noqa: SLF001
    names = [
        item["function"]["name"]
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    assert names.count("ask_user_question") == 1
