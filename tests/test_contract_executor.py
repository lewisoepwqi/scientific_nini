"""真实 contract 执行器与主链路集成测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from nini.agent.events import EventType
from nini.agent.runner import AgentRunner
from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.models.database import init_db
from nini.models.skill_contract import SkillContract, SkillStep


@dataclass(slots=True)
class _ResolverResponse:
    text: str
    tool_calls: list[dict[str, Any]]


class _ContractResolver:
    async def chat_complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> _ResolverResponse:
        prompt = str(messages[-1]["content"] if messages else "")
        if tools:
            return _ResolverResponse(
                text="",
                tool_calls=[
                    {
                        "id": "call_contract_echo",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": json.dumps(
                                {"value": "候选材料 3 条，主题=糖尿病"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            )

        assert "候选材料 3 条，主题=糖尿病" in prompt
        return _ResolverResponse(
            text="最终方案草稿（O2 草稿级）\n已综合候选材料 3 条，主题=糖尿病。",
            tool_calls=[],
        )


class _EchoTool:
    name = "echo_tool"
    description = "回显结构化材料"
    parameters = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "description": "要返回的材料摘要",
            }
        },
        "required": ["value"],
    }

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class _ContractRegistry:
    def __init__(self) -> None:
        self._tool = _EchoTool()
        contract = SkillContract(
            trust_ceiling="t1",
            steps=[
                SkillStep(
                    id="collect_inputs",
                    name="收集输入",
                    description="整理用户主题并生成候选材料",
                    tool_hint="echo_tool",
                ),
                SkillStep(
                    id="finalize",
                    name="生成方案",
                    description="基于候选材料生成最终方案草稿",
                    depends_on=["collect_inputs"],
                    review_gate=True,
                ),
            ],
        )
        self._skill = {
            "type": "markdown",
            "name": "demo-contract",
            "description": "演示 contract skill",
            "enabled": True,
            "metadata": {
                "contract": contract.model_dump(mode="json"),
                "user_invocable": True,
            },
        }
        self._instruction = """
# 演示 contract skill

## 第一步：收集输入（collect_inputs）

### LLM 提示模板

```text
请整理本轮主题，生成适合工具处理的材料摘要。
```

## 第二步：生成方案（finalize）

### LLM 提示模板

```text
请基于以下候选材料生成最终方案草稿：
{collect_inputs_output}

输出必须标注 O2 草稿级。
```
""".strip()

    def list_markdown_tools(self) -> list[dict[str, Any]]:
        return [self._skill]

    def get_tool_instruction(self, name: str) -> dict[str, Any] | None:
        if name != "demo-contract":
            return None
        return {
            "name": "demo-contract",
            "instruction": self._instruction,
            "location": "skill:demo-contract",
            "metadata": self._skill["metadata"],
        }

    def get(self, name: str) -> Any | None:
        if name == "echo_tool":
            return self._tool
        return None

    async def execute_with_fallback(
        self,
        tool_name: str,
        session: Session,
        **kwargs: Any,
    ) -> dict[str, Any]:
        assert tool_name == "echo_tool"
        return {
            "success": True,
            "message": str(kwargs.get("value", "")).strip(),
            "data": {
                "text": str(kwargs.get("value", "")).strip(),
            },
        }


class _EmptyKnowledgeLoader:
    def select_with_hits(self, *_: Any, **__: Any) -> tuple[str, list[dict[str, Any]]]:
        return "", []


@pytest.fixture
async def isolated_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "api_key", "")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    await init_db()


@pytest.mark.asyncio
async def test_agent_runner_executes_explicit_contract_skill_with_review_gate(
    isolated_runtime,
) -> None:
    del isolated_runtime
    session = Session()
    runner = AgentRunner(
        tool_registry=_ContractRegistry(),
        resolver=_ContractResolver(),
        knowledge_loader=_EmptyKnowledgeLoader(),
    )

    events = []
    with (
        patch("nini.config_manager.get_active_provider_id", AsyncMock(return_value=None)),
        patch("nini.config_manager.list_user_configured_provider_ids", AsyncMock(return_value=[])),
        patch(
            "nini.config_manager.get_trial_status",
            AsyncMock(
                return_value={
                    "expired": False,
                    "activated": True,
                    "fast_calls_remaining": 3,
                    "deep_calls_remaining": 1,
                }
            ),
        ),
    ):
        async for event in runner.run(
            session,
            "/demo-contract 糖尿病",
            turn_id="turn-contract",
        ):
            events.append(event)
            if (
                event.type == EventType.SKILL_STEP
                and isinstance(event.data, dict)
                and event.data.get("status") == "review_required"
            ):
                active_runner = getattr(session, "_active_contract_runner", None)
                assert active_runner is not None
                active_runner.approve_review("finalize")

    step_statuses = [
        event.data.get("status")
        for event in events
        if event.type == EventType.SKILL_STEP and isinstance(event.data, dict)
    ]
    assert step_statuses == [
        "started",
        "completed",
        "review_required",
        "started",
        "completed",
    ]
    assert any(event.type == EventType.SKILL_SUMMARY for event in events)
    assert any(event.type == EventType.TEXT for event in events)
    assert any(event.type == EventType.DONE for event in events)
    assert session.messages[-1]["role"] == "assistant"
    assert "最终方案草稿（O2 草稿级）" in session.messages[-1]["content"]
    assert session.messages[-1]["output_level"] == "o2"
    assert getattr(session, "_active_contract_runner", None) is None
