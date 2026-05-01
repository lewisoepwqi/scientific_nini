"""运行期可观测性日志回归测试。"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from nini.agent.model_resolver import LLMChunk, ModelResolver
from nini.agent.runner import AgentRunner
from nini.knowledge.loader import KnowledgeLoader
from nini.sandbox.r_executor import RSandboxExecutor
from nini.workspace import WorkspaceManager


class _FakeClient:
    provider_id = "fake"
    provider_name = "Fake"

    def is_available(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "fake-model"

    async def chat(self, **_kwargs):
        yield LLMChunk(text="ok")


@pytest.mark.asyncio
async def test_model_resolver_logs_traceback_for_listing_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _raise_listing_failure(**_kwargs):
        raise RuntimeError("listing failed")

    monkeypatch.setattr(
        "nini.agent.model_lister.list_available_models",
        _raise_listing_failure,
    )

    resolver = ModelResolver(clients=[_FakeClient()])

    with caplog.at_level(logging.DEBUG, logger="nini.agent.model_resolver"):
        result = await resolver.test_connection("fake")

    assert result["success"] is True
    record = next(
        record for record in caplog.records if "测试连接获取模型列表失败" in record.message
    )
    assert record.exc_info is not None


def test_workspace_hydration_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = WorkspaceManager("session-observability")
    session = SimpleNamespace(datasets={})

    monkeypatch.setattr(
        manager,
        "list_datasets",
        lambda: [{"id": "dataset-1", "name": "broken.csv"}],
    )

    def _raise_load_failure(_dataset_id: str):
        raise RuntimeError("load failed")

    monkeypatch.setattr(manager, "load_dataset_by_id", _raise_load_failure)

    with caplog.at_level(logging.WARNING, logger="nini.workspace.manager"):
        loaded = manager.hydrate_session_datasets(session)

    assert loaded == 0
    record = next(record for record in caplog.records if "恢复工作区数据集失败" in record.message)
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_runner_tool_execution_logs_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FakeRegistry:
        async def execute_with_fallback(self, name: str, session: object, **kwargs):
            assert name == "demo_tool"
            assert getattr(session, "id") == "session-runner"
            assert kwargs == {"value": 1}
            return {"success": True}

    runner = AgentRunner(
        tool_registry=_FakeRegistry(),
        knowledge_loader=SimpleNamespace(supports_context_injector=False),
    )
    session = SimpleNamespace(id="session-runner")

    with caplog.at_level(logging.INFO, logger="nini.agent.runner"):
        result = await runner._execute_tool(session, "demo_tool", '{"value": 1}')

    assert result["success"] is True
    assert any("工具执行结束" in record.message for record in caplog.records)


def test_knowledge_loader_logs_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("nini.knowledge.loader.settings.knowledge_strategy", "keyword")
    (tmp_path / "stats.md").write_text(
        "<!-- keywords: t检验 -->\n<!-- priority: high -->\n适合双样本比较。",
        encoding="utf-8",
    )

    loader = KnowledgeLoader(tmp_path, enable_vector=False)

    with caplog.at_level(logging.INFO, logger="nini.knowledge.loader"):
        text, hits = loader.select_with_hits("请帮我做 t检验", max_entries=1)

    assert text
    assert len(hits) == 1
    assert any("知识检索完成" in record.message for record in caplog.records)


def test_r_sandbox_logs_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        "nini.sandbox.r_executor.settings",
        SimpleNamespace(sessions_dir=tmp_path, r_auto_install_packages=False),
    )
    monkeypatch.setattr(
        "nini.sandbox.r_executor.detect_r_installation",
        lambda: {"available": True, "message": "ok"},
    )
    monkeypatch.setattr("nini.sandbox.r_executor._extract_required_packages", lambda _code: set())
    monkeypatch.setattr(
        "nini.sandbox.r_executor.check_r_packages",
        lambda packages: {package: True for package in packages},
    )
    monkeypatch.setattr("nini.sandbox.r_executor._write_datasets_csv", lambda _d, _t: [])
    monkeypatch.setattr("nini.sandbox.r_executor._build_wrapper_script", lambda **_kwargs: "1+1")
    monkeypatch.setattr("nini.sandbox.r_executor._rscript_binary", lambda: "Rscript")
    monkeypatch.setattr("nini.sandbox.r_executor._r_env", lambda: {})

    class _FakePopen:
        pid = 12345
        returncode = 0

        def communicate(self, timeout=None):
            return ("ok", "")

    monkeypatch.setattr(
        "nini.sandbox.r_executor.subprocess.Popen",
        lambda *_args, **_kwargs: _FakePopen(),
    )

    executor = RSandboxExecutor(timeout_seconds=1, max_memory_mb=256)

    with caplog.at_level(logging.INFO, logger="nini.sandbox.r_executor"):
        result = executor._execute_sync(
            code="print(1)",
            session_id="sandbox-session",
            datasets={},
            dataset_name=None,
            persist_df=False,
        )

    assert result["success"] is True
    assert any("R 沙箱执行完成" in record.message for record in caplog.records)
