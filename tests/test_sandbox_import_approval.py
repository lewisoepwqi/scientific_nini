"""沙盒扩展包审批测试。"""

from __future__ import annotations

import asyncio
import builtins
import json
from pathlib import Path

import pytest

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.sandbox.executor import _make_safe_import, sandbox_executor
from nini.sandbox.policy import (
    SandboxPolicyError,
    SandboxReviewRequired,
    get_allowed_import_roots,
    validate_code,
)
from nini.tools.registry import create_default_tool_registry


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()

    async def _mock_get_active_provider_id():
        return "dummy"

    async def _mock_list_user_configured_provider_ids():
        return ["dummy"]

    monkeypatch.setattr("nini.config_manager.get_active_provider_id", _mock_get_active_provider_id)
    monkeypatch.setattr(
        "nini.config_manager.list_user_configured_provider_ids",
        _mock_list_user_configured_provider_ids,
    )
    yield
    session_manager._sessions.clear()


def test_validate_code_aggregates_reviewable_imports() -> None:
    code = "import sympy\nimport plotnine\nresult = 1"

    with pytest.raises(SandboxReviewRequired) as exc_info:
        validate_code(code)

    assert exc_info.value.packages == ["plotnine", "sympy"]
    payload = exc_info.value.to_payload()
    assert len(payload["violations"]) == 2


def test_validate_code_hard_denies_high_risk_import() -> None:
    with pytest.raises(SandboxPolicyError) as exc_info:
        validate_code("import requests\nresult = 1")

    assert "不允许导入模块" in str(exc_info.value)
    assert "高风险模块" in str(exc_info.value)


def test_validate_code_denies_unknown_import() -> None:
    with pytest.raises(SandboxPolicyError) as exc_info:
        validate_code("import definitely_unknown_pkg\nresult = 1")

    assert "不允许导入模块" in str(exc_info.value)


def test_safe_import_matches_policy_before_and_after_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied_import = _make_safe_import(get_allowed_import_roots())
    with pytest.raises(SandboxReviewRequired):
        denied_import("sympy")

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sympy":
            return {"module": name}
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    allowed_import = _make_safe_import(get_allowed_import_roots(["sympy"]))
    assert allowed_import("sympy") == {"module": "sympy"}


@pytest.mark.asyncio
async def test_sandbox_executor_raises_review_required_for_reviewable_import() -> None:
    session = Session()

    with pytest.raises(SandboxReviewRequired) as exc_info:
        await sandbox_executor.execute(
            code="import sympy\nresult = 1",
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

    assert exc_info.value.packages == ["sympy"]


def test_run_code_returns_structured_review_request() -> None:
    registry = create_default_tool_registry()
    session = Session()

    result = asyncio.run(
        registry.execute(
            "run_code",
            session=session,
            code="import sympy\nresult = 1",
        )
    )

    assert result["success"] is False
    assert result["data"]["_sandbox_review_required"] is True
    assert result["data"]["requested_packages"] == ["sympy"]
    assert result["data"]["sandbox_violations"][0]["root"] == "sympy"


class _SandboxApprovalResolver:
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
                text="尝试执行 run_code",
                tool_calls=[
                    {
                        "id": "tool-run-code-1",
                        "type": "function",
                        "function": {
                            "name": "run_code",
                            "arguments": json.dumps(
                                {
                                    "code": "import sympy\nresult = 1",
                                    "intent": "验证沙盒审批",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            )
            return

        yield _Chunk(text="审批后继续完成。", tool_calls=[])


class _SandboxApprovalRegistry:
    def __init__(self, *, always_require_review: bool = False) -> None:
        self.execute_calls = 0
        self.always_require_review = always_require_review

    def get_tool_definitions(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_code",
                    "description": "运行代码",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def list_markdown_skills(self) -> list[dict[str, object]]:
        return []

    async def execute(self, skill_name: str, session: Session, **kwargs):
        self.execute_calls += 1
        if skill_name != "run_code":
            return {"error": f"unknown skill: {skill_name}"}
        approved = kwargs.get("extra_allowed_imports") or []
        if self.always_require_review or "sympy" not in approved:
            return {
                "success": False,
                "message": "继续执行前需要用户审批导入扩展包：sympy",
                "data": {
                    "_sandbox_review_required": True,
                    "requested_packages": ["sympy"],
                    "sandbox_violations": [
                        {
                            "message": "导入扩展包 'sympy' 需要用户审批",
                            "module": "sympy",
                            "root": "sympy",
                            "risk_level": "reviewable",
                        }
                    ],
                },
            }
        return {"success": True, "message": "run_code 审批后执行成功", "data": {"result": 1}}

    async def execute_with_fallback(self, skill_name: str, session: Session, **kwargs):
        return await self.execute(skill_name, session=session, **kwargs)


@pytest.mark.asyncio
async def test_runner_requests_sandbox_import_approval_and_retries() -> None:
    session = Session()
    registry = _SandboxApprovalRegistry()

    async def _ask_handler(_session: Session, _tool_call_id: str, _payload: dict[str, object]):
        return {"approval": "本会话允许"}

    runner = AgentRunner(
        resolver=_SandboxApprovalResolver(),
        skill_registry=registry,
        ask_user_question_handler=_ask_handler,
    )

    events = []
    async for event in runner.run(session, "请运行需要 sympy 的代码"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    assert any(event.type == EventType.ASK_USER_QUESTION for event in events)
    assert registry.execute_calls == 2
    assert session.has_sandbox_import_approval("sympy")
    run_code_results = [
        event for event in events if event.type == EventType.TOOL_RESULT and event.tool_name == "run_code"
    ]
    assert run_code_results[-1].data["status"] == "success"


@pytest.mark.asyncio
async def test_runner_stops_when_sandbox_import_is_denied() -> None:
    session = Session()
    registry = _SandboxApprovalRegistry()

    async def _ask_handler(_session: Session, _tool_call_id: str, _payload: dict[str, object]):
        return {"approval": "拒绝"}

    runner = AgentRunner(
        resolver=_SandboxApprovalResolver(),
        skill_registry=registry,
        ask_user_question_handler=_ask_handler,
    )

    events = []
    async for event in runner.run(session, "请运行需要 sympy 的代码"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    assert registry.execute_calls == 1
    run_code_results = [
        event for event in events if event.type == EventType.TOOL_RESULT and event.tool_name == "run_code"
    ]
    assert run_code_results[-1].data["status"] == "error"
    assert "用户拒绝放行" in run_code_results[-1].data["data"]["result"]["message"]


@pytest.mark.asyncio
async def test_runner_blocks_repeated_sandbox_review_after_single_retry() -> None:
    session = Session()
    registry = _SandboxApprovalRegistry(always_require_review=True)

    async def _ask_handler(_session: Session, _tool_call_id: str, _payload: dict[str, object]):
        return {"approval": "仅本次允许"}

    runner = AgentRunner(
        resolver=_SandboxApprovalResolver(),
        skill_registry=registry,
        ask_user_question_handler=_ask_handler,
    )

    events = []
    async for event in runner.run(session, "请运行需要 sympy 的代码"):
        events.append(event)
        if event.type == EventType.DONE:
            break

    assert registry.execute_calls == 2
    run_code_results = [
        event for event in events if event.type == EventType.TOOL_RESULT and event.tool_name == "run_code"
    ]
    assert run_code_results[-1].data["status"] == "error"
    assert run_code_results[-1].data["data"]["result"]["error_code"] == "SANDBOX_IMPORT_APPROVAL_REPEAT"
