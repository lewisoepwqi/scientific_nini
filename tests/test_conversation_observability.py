"""对话可观测性与压缩能力测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import Session, session_manager
from nini.app import create_app
from nini.config import settings
from nini.memory.compression import compress_session_history
from tests.client_utils import LocalASGIClient


class _DummyResolver:
    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        class _Chunk:
            text = "已完成分析。"
            tool_calls = []
            usage = None

        yield _Chunk()


class _DummyKnowledgeLoader:
    def select_with_hits(self, *args, **kwargs):
        return (
            "这是检索命中的知识内容",
            [
                {
                    "source": "demo.md",
                    "score": 2.0,
                    "hits": 1,
                    "snippet": "这是检索命中的知识内容",
                }
            ],
        )


class _ReportResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls: list[dict[str, object]]):
                self.text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="",
                tool_calls=[
                    {
                        "id": "call_report_1",
                        "type": "function",
                        "function": {
                            "name": "generate_report",
                            "arguments": json.dumps(
                                {
                                    "title": "自动报告",
                                    "summary_text": "保持一致性测试",
                                    "dataset_names": ["exp.csv"],
                                    "include_recent_messages": False,
                                    "save_to_knowledge": False,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            )
            return

        # 修复后不应执行到第二次 LLM 调用
        yield _Chunk(text="这段不应出现", tool_calls=[])


class _DummySkillRegistry:
    def get_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "generate_report",
                    "description": "生成报告",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute(self, skill_name: str, session: Session, **kwargs):
        if skill_name != "generate_report":
            return {"error": f"unknown skill: {skill_name}"}
        markdown = (
            "# 自动报告\n\n" "## 数据集概览\n" "- exp.csv\n\n" "## 分析摘要\n" "保持一致性测试\n"
        )
        return {
            "success": True,
            "message": "报告已生成并保存",
            "data": {
                "title": "自动报告",
                "filename": "auto_report.md",
                "report_markdown": markdown,
            },
            "artifacts": [
                {
                    "name": "auto_report.md",
                    "type": "report",
                    "path": str(
                        settings.sessions_dir
                        / session.id
                        / "workspace"
                        / "artifacts"
                        / "auto_report.md"
                    ),
                    "download_url": f"/api/artifacts/{session.id}/auto_report.md",
                }
            ],
        }


class _TwoStepToolResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls: list[dict[str, object]]):
                self.text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="",
                tool_calls=[
                    {
                        "id": "call_echo_1",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": json.dumps({"value": "ok"}, ensure_ascii=False),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="最终回复", tool_calls=[])


class _PlanAwareToolResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls: list[dict[str, object]]):
                self.text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text=(
                    "1. 加载并检查数据集 - 使用工具: echo_tool\n"
                    "2. 汇总分析结论 - 使用工具: echo_tool"
                ),
                tool_calls=[
                    {
                        "id": "call_plan_1",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": json.dumps({"value": "ok"}, ensure_ascii=False),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="计划执行完成", tool_calls=[])


class _ContextOverflowThenSuccessResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("maximum context length exceeded")

        class _Chunk:
            text = "自动压缩后继续完成。"
            tool_calls = []
            usage = None

        yield _Chunk()


class _ReasoningOnlyResolver:
    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        class _Chunk:
            text = "最终答案"
            reasoning = "先检查数据分布。"
            raw_text = "<think>先检查数据分布。</think>最终答案"
            tool_calls = []
            usage = None

        yield _Chunk()


class _ReasoningToolResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, reasoning: str, raw_text: str, tool_calls):
                self.text = text
                self.reasoning = reasoning
                self.raw_text = raw_text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="执行步骤",
                reasoning="先规划执行步骤。",
                raw_text="<think>先规划执行步骤。</think>执行步骤",
                tool_calls=[
                    {
                        "id": "call_reasoning_1",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": json.dumps({"value": "ok"}, ensure_ascii=False),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="已完成", reasoning="", raw_text="已完成", tool_calls=[])


class _EchoSkillRegistry:
    def get_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "echo_tool",
                    "description": "回声测试工具",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute(self, skill_name: str, session: Session, **kwargs):
        if skill_name != "echo_tool":
            return {"error": f"unknown skill: {skill_name}"}
        return {"success": True, "message": "echo ok", "data": {"value": kwargs.get("value")}}


class _RetryEchoSkillRegistry(_EchoSkillRegistry):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, skill_name: str, session: Session, **kwargs):
        self.calls += 1
        if skill_name != "echo_tool":
            return {"error": f"unknown skill: {skill_name}"}
        if self.calls == 1:
            return {"success": False, "error": "temporary failure"}
        return {
            "success": True,
            "message": "echo ok after retry",
            "data": {"value": kwargs.get("value")},
        }


class _BlockedByAllowedToolsResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls):
                self.text = text
                self.reasoning = ""
                self.raw_text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="尝试执行工具",
                tool_calls=[
                    {
                        "id": "call_guard_1",
                        "type": "function",
                        "function": {
                            "name": "echo_tool",
                            "arguments": json.dumps({"value": "blocked"}, ensure_ascii=False),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="已结束", tool_calls=[])


class _GuardedSkillRegistry(_EchoSkillRegistry):
    def __init__(self) -> None:
        self.execute_calls = 0

    def list_markdown_skills(self) -> list[dict[str, object]]:
        return [
            {
                "type": "markdown",
                "name": "guarded-skill",
                "description": "受限技能",
                "category": "workflow",
                "location": "/tmp/guarded/SKILL.md",
                "enabled": True,
                "metadata": {
                    "user_invocable": True,
                    "allowed_tools": ["run_code"],
                },
            }
        ]

    async def execute(self, skill_name: str, session: Session, **kwargs):
        self.execute_calls += 1
        return await super().execute(skill_name, session, **kwargs)


class _LoadDatasetBypassResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
        self.calls += 1

        class _Chunk:
            def __init__(self, *, text: str, tool_calls):
                self.text = text
                self.reasoning = ""
                self.raw_text = text
                self.tool_calls = tool_calls
                self.usage = None

        if self.calls == 1:
            yield _Chunk(
                text="先加载数据",
                tool_calls=[
                    {
                        "id": "call_load_1",
                        "type": "function",
                        "function": {
                            "name": "load_dataset",
                            "arguments": json.dumps(
                                {"dataset_name": "all.xlsx"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="加载完成", tool_calls=[])


class _LoadDatasetGuardedSkillRegistry:
    def __init__(self) -> None:
        self.execute_calls = 0

    def get_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "load_dataset",
                    "description": "加载数据集",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def list_markdown_skills(self) -> list[dict[str, object]]:
        return [
            {
                "type": "markdown",
                "name": "guarded-skill",
                "description": "受限技能",
                "category": "workflow",
                "location": "/tmp/guarded/SKILL.md",
                "enabled": True,
                "metadata": {
                    "user_invocable": True,
                    "allowed_tools": ["run_code"],
                },
            }
        ]

    async def execute(self, skill_name: str, session: Session, **kwargs):
        self.execute_calls += 1
        if skill_name != "load_dataset":
            return {"error": f"unknown skill: {skill_name}"}
        return {"success": True, "message": "load ok"}


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.mark.asyncio
async def test_runner_emits_retrieval_event_before_text() -> None:
    session = Session()
    session.add_message("user", "请给我 t 检验建议")

    runner = AgentRunner(
        resolver=_DummyResolver(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )
    events = []
    async for event in runner.run(session, "继续", append_user_message=False):
        events.append(event)
        if event.type == EventType.DONE:
            break

    event_types = [e.type.value for e in events]
    assert "retrieval" in event_types
    assert "text" in event_types
    retrieval_idx = event_types.index("retrieval")
    text_idx = event_types.index("text")
    assert retrieval_idx < text_idx

    retrieval_event = next(e for e in events if e.type == EventType.RETRIEVAL)
    assert retrieval_event.data["query"] == "请给我 t 检验建议"
    assert len(retrieval_event.data["results"]) == 1


@pytest.mark.asyncio
async def test_generate_report_uses_saved_markdown_as_final_response() -> None:
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame({"x": [1, 2, 3]})
    resolver = _ReportResolver()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_DummySkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "生成报告"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    text_payloads = [str(e.data) for e in events if e.type == EventType.TEXT]
    assert resolver.calls == 1
    assert any("## 分析摘要" in payload for payload in text_payloads)
    assert all("这段不应出现" not in payload for payload in text_payloads)
    assert session.messages[-1]["role"] == "assistant"
    assert "## 分析摘要" in str(session.messages[-1]["content"])


@pytest.mark.asyncio
async def test_runner_unlimited_iterations_when_max_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_max_iterations", 0)

    session = Session()
    resolver = _TwoStepToolResolver()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_EchoSkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "继续分析"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    event_types = [e.type.value for e in events]
    assert resolver.calls == 2
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "error" not in event_types
    assert session.messages[-1]["role"] == "assistant"
    assert session.messages[-1]["content"] == "最终回复"


@pytest.mark.asyncio
async def test_runner_emits_plan_progress_with_required_fields() -> None:
    """验证 fallback 文本解析模式会推进计划状态并发出结构化进度事件。"""
    session = Session()
    session.add_message("user", "请按步骤执行分析")

    resolver = _PlanAwareToolResolver()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_EchoSkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "继续", append_user_message=False):
        events.append(event)
        if event.type == EventType.DONE:
            break

    event_types = [event.type.value for event in events]
    # 文本解析会发出 analysis_plan/plan_progress，并产生 plan_step_update
    assert "analysis_plan" in event_types
    assert "plan_progress" in event_types
    assert "plan_step_update" in event_types

    progress_events = [event for event in events if event.type == EventType.PLAN_PROGRESS]
    step_update_events = [event for event in events if event.type == EventType.PLAN_STEP_UPDATE]
    analysis_plan_events = [event for event in events if event.type == EventType.ANALYSIS_PLAN]
    # 至少包含 pending -> in_progress -> done
    assert len(progress_events) >= 3
    assert len(step_update_events) >= 1
    assert len(analysis_plan_events) >= 1

    required_keys = {
        "current_step_index",
        "total_steps",
        "step_title",
        "step_status",
        "next_hint",
    }
    for event in progress_events:
        payload = event.data if isinstance(event.data, dict) else {}
        assert required_keys.issubset(payload.keys())

    seq_values = [
        int(event.metadata.get("seq", 0))
        for event in progress_events
        if isinstance(event.metadata, dict)
    ]
    assert seq_values == sorted(seq_values)
    assert all(value > 0 for value in seq_values)

    # 所有计划相关事件必须落在同一单调 seq 时钟域，避免前端乱序保护误丢事件
    ordered_plan_events = [
        event
        for event in events
        if event.type
        in {EventType.ANALYSIS_PLAN, EventType.PLAN_PROGRESS, EventType.PLAN_STEP_UPDATE}
    ]
    ordered_seq_values = [
        int(event.metadata.get("seq", 0))
        for event in ordered_plan_events
        if isinstance(event.metadata, dict)
    ]
    assert len(ordered_seq_values) == len(ordered_plan_events)
    assert ordered_seq_values == sorted(ordered_seq_values)
    assert all(value > 0 for value in ordered_seq_values)

    statuses = [str((event.data or {}).get("step_status")) for event in progress_events]
    assert "in_progress" in statuses
    assert "done" in statuses


@pytest.mark.asyncio
async def test_runner_attaches_action_tracking_metadata_no_auto_retry() -> None:
    """验证 max_retries=0：工具失败后不自动重试，由 LLM 自行决定。"""
    session = Session()
    session.add_message("user", "按计划执行")

    resolver = _TwoStepToolResolver()
    registry = _RetryEchoSkillRegistry()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=registry,
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "继续", append_user_message=False):
        events.append(event)
        if event.type == EventType.DONE:
            break

    tool_call_event = next(event for event in events if event.type == EventType.TOOL_CALL)
    assert isinstance(tool_call_event.metadata, dict)
    assert isinstance(tool_call_event.metadata.get("action_id"), str)
    # max_retries=0 时不附加 retry_policy
    assert tool_call_event.metadata.get("retry_policy") is None

    tool_result_event = next(event for event in events if event.type == EventType.TOOL_RESULT)
    assert isinstance(tool_result_event.metadata, dict)
    assert tool_result_event.metadata.get("action_id") == tool_call_event.metadata.get("action_id")
    # 没有自动重试，retry_count 应为 0
    assert tool_result_event.metadata.get("retry_count") == 0
    assert tool_result_event.metadata.get("max_retries") == 0

    attempt_events = [event for event in events if event.type == EventType.TASK_ATTEMPT]
    # 仅 1 次尝试（in_progress + failed），不再有 retrying
    assert len(attempt_events) == 2
    attempt_statuses = [
        str(event.data.get("status")) for event in attempt_events if isinstance(event.data, dict)
    ]
    assert "in_progress" in attempt_statuses
    assert "failed" in attempt_statuses
    assert "retrying" not in attempt_statuses

    # 工具只被调用 1 次（不自动重试）
    assert registry.calls == 1


@pytest.mark.asyncio
async def test_runner_auto_compresses_and_retries_on_context_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session()
    for i in range(6):
        role = "user" if i % 2 == 0 else "assistant"
        session.add_message(role, f"历史消息-{i}")

    resolver = _ContextOverflowThenSuccessResolver()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_EchoSkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    async def _fake_compress(session_obj: Session, ratio: float = 0.5, min_messages: int = 4):
        archived_count = max(len(session_obj.messages) - 2, 0)
        session_obj.messages = session_obj.messages[-2:]
        session_obj.set_compressed_context("自动压缩摘要")
        return {
            "success": True,
            "archived_count": archived_count,
            "remaining_count": len(session_obj.messages),
        }

    monkeypatch.setattr("nini.agent.runner.compress_session_history_with_llm", _fake_compress)

    events = []
    async for event in runner.run(session, "继续分析"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    event_types = [e.type.value for e in events]
    assert resolver.calls == 2
    assert "context_compressed" in event_types
    assert "text" in event_types
    assert "done" in event_types
    assert "error" not in event_types
    assert session.messages[-1]["content"] == "自动压缩后继续完成。"


@pytest.mark.asyncio
async def test_runner_emits_reasoning_event_and_keeps_final_answer_clean() -> None:
    session = Session()
    runner = AgentRunner(
        resolver=_ReasoningOnlyResolver(),
        skill_registry=_EchoSkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "继续分析"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    reasoning_payloads = [e.data for e in events if e.type == EventType.REASONING]
    assert any(
        isinstance(payload, dict) and payload.get("content") == "先检查数据分布。"
        for payload in reasoning_payloads
    )
    assert session.messages[-1]["role"] == "assistant"
    assert session.messages[-1]["content"] == "最终答案"


@pytest.mark.asyncio
async def test_runner_preserves_raw_assistant_content_for_tool_calls() -> None:
    session = Session()
    resolver = _ReasoningToolResolver()
    runner = AgentRunner(
        resolver=resolver,
        skill_registry=_EchoSkillRegistry(),
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    async for event in runner.run(session, "执行带工具调用的推理"):
        if event.type == EventType.DONE:
            break

    assistant_tool_msgs = [
        msg for msg in session.messages if msg.get("role") == "assistant" and msg.get("tool_calls")
    ]
    assert len(assistant_tool_msgs) == 1
    content = assistant_tool_msgs[0].get("content")
    assert isinstance(content, str)
    assert "<think>" in content
    assert "</think>" in content


@pytest.mark.asyncio
async def test_runner_does_not_block_tool_outside_allowed_tools_recommendation() -> None:
    session = Session()
    registry = _GuardedSkillRegistry()
    runner = AgentRunner(
        resolver=_BlockedByAllowedToolsResolver(),
        skill_registry=registry,
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "/guarded-skill 执行流程"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    tool_results = [e for e in events if e.type == EventType.TOOL_RESULT]
    assert tool_results
    last_result = tool_results[-1]
    assert isinstance(last_result.data, dict)
    assert last_result.data.get("status") == "success"
    assert registry.execute_calls == 1


@pytest.mark.asyncio
async def test_runner_allows_load_dataset_when_not_in_allowed_tools() -> None:
    session = Session()
    registry = _LoadDatasetGuardedSkillRegistry()
    runner = AgentRunner(
        resolver=_LoadDatasetBypassResolver(),
        skill_registry=registry,
        knowledge_loader=_DummyKnowledgeLoader(),
    )

    events = []
    async for event in runner.run(session, "/guarded-skill 先加载数据"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    tool_results = [
        e for e in events if e.type == EventType.TOOL_RESULT and e.tool_name == "load_dataset"
    ]
    assert tool_results
    assert isinstance(tool_results[-1].data, dict)
    assert tool_results[-1].data.get("status") == "success"
    assert registry.execute_calls == 1


def test_compress_session_history_archives_and_updates_context() -> None:
    session = Session()
    for i in range(8):
        role = "user" if i % 2 == 0 else "assistant"
        session.add_message(role, f"消息-{i}")

    result = compress_session_history(session)

    assert result["success"] is True, result
    assert result["archived_count"] >= 4
    assert result["remaining_count"] >= 1
    assert "消息-0" in session.compressed_context
    archive_path = Path(result["archive_path"])
    assert archive_path.exists()


def test_api_compress_session_endpoint() -> None:
    app = create_app()
    with LocalASGIClient(app) as client:
        create_resp = client.post("/api/sessions")
        session_id = create_resp.json()["data"]["session_id"]

        session = session_manager.get_session(session_id)
        assert session is not None
        for i in range(6):
            session.add_message("user" if i % 2 == 0 else "assistant", f"历史-{i}")

        resp = client.post(f"/api/sessions/{session_id}/compress", params={"mode": "lightweight"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["data"]["archived_count"] >= 4
        assert payload["data"]["remaining_count"] >= 1
