"""Phase 7：CLI 命令与首启引导测试。"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from nini.__main__ import (
    _detect_kaleido_chrome_status,
    _detect_weasyprint_status,
    _render_markdown_tool_template,
    main,
)
from nini.config import settings
from nini.harness.models import HarnessRunSummary, HarnessSessionSnapshot


def test_cli_init_creates_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.nini"
    ret = main(["init", "--env-file", str(env_path)])
    assert ret == 0
    assert env_path.exists()
    text = env_path.read_text(encoding="utf-8")
    assert "NINI_TRIAL_API_KEY=" in text
    assert "NINI_OPENAI_API_KEY=" in text
    assert "NINI_OLLAMA_BASE_URL=" in text
    assert "NINI_KIMI_CODING_API_KEY=" in text
    assert "NINI_ZHIPU_BASE_URL=" in text
    assert "NINI_R_ENABLED=" in text
    assert "NINI_R_SANDBOX_TIMEOUT=" in text


def test_cli_init_without_force_refuses_overwrite(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.nini"
    env_path.write_text("EXISTING=1\n", encoding="utf-8")
    ret = main(["init", "--env-file", str(env_path)])
    assert ret == 1
    assert env_path.read_text(encoding="utf-8") == "EXISTING=1\n"


def test_cli_start_default_command_invokes_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    fake_uvicorn = SimpleNamespace(run=fake_run)
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    ret = main(["--port", "9001", "--host", "0.0.0.0"])
    assert ret == 0
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["port"] == 9001
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["log_level"] == "info"
    assert kwargs["log_config"] is None


def test_cli_start_log_level_updates_app_and_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    fake_uvicorn = SimpleNamespace(run=fake_run)
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.delenv("NINI_LOG_LEVEL", raising=False)

    ret = main(["start", "--log-level", "debug", "--no-open"])

    assert ret == 0
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs["log_level"] == "debug"
    assert kwargs["log_config"] is None
    assert settings.log_level == "debug"
    assert os.environ["NINI_LOG_LEVEL"] == "debug"


def test_cli_doctor_returns_success_with_default_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    ret = main(["doctor"])
    assert ret == 0


def test_cli_doctor_surface_outputs_visible_tools(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeRegistry:
        def list_tools(self):
            return ["task_state", "dataset_catalog", "export_report"]

        def list_markdown_tools(self):
            return [{"name": "writing-guide", "enabled": True}]

    monkeypatch.setattr("nini.tools.registry.create_default_tool_registry", lambda: _FakeRegistry())
    ret = main(["doctor", "--surface", "--surface-stage", "profile"])
    out = capsys.readouterr().out

    assert ret == 0
    assert '"stage": "profile"' in out
    assert '"visible_tools"' in out


def test_render_markdown_skill_template_removes_todo_placeholders() -> None:
    content = _render_markdown_tool_template(
        name="demo_skill",
        description="测试技能描述",
        category="report",
    )

    assert "TODO" not in content
    assert "## 适用场景" in content
    assert "## 步骤" in content
    assert "## 注意事项" in content
    assert "name: demo_skill" in content
    assert "category: report" in content


def test_detect_kaleido_chrome_status_when_kaleido_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str):
        if name == "kaleido":
            raise ImportError("no kaleido")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("nini.__main__.importlib.import_module", fake_import)
    ok, msg = _detect_kaleido_chrome_status()
    assert ok is False
    assert "kaleido 未安装" in msg


def test_detect_kaleido_chrome_status_when_chromium_probe_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ChromiumModule:
        chromium_based_browsers = ["chrome"]

        @staticmethod
        def get_browser_path(_browsers: list[str]) -> str:
            raise RuntimeError("probe failed")

    def fake_import(name: str):
        if name == "kaleido":
            return object()
        if name == "choreographer.browsers.chromium":
            return _ChromiumModule()
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("nini.__main__.importlib.import_module", fake_import)
    ok, msg = _detect_kaleido_chrome_status()
    assert ok is False
    assert "Chrome 状态未知" in msg
    assert "RuntimeError" in msg


def test_detect_weasyprint_status_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str):
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("nini.__main__.importlib.import_module", fake_import)
    ok, msg = _detect_weasyprint_status()
    assert ok is False
    assert "weasyprint 未安装" in msg


def test_detect_weasyprint_status_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _WeasyprintModule:
        __version__ = "99.9"

    def fake_import(name: str):
        if name == "weasyprint":
            return _WeasyprintModule()
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("nini.__main__.importlib.import_module", fake_import)
    ok, msg = _detect_weasyprint_status()
    assert ok is True
    assert "99.9" in msg


def test_cli_harness_list_outputs_summaries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        async def list_runs(self, session_id: str | None = None, limit: int = 20):
            _ = session_id, limit
            return [
                HarnessRunSummary(
                    run_id="run_demo",
                    session_id="session_demo",
                    turn_id="turn_demo",
                    status="completed",
                    trace_path="/tmp/run_demo.json",
                )
            ]

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["harness", "list"])
    out = capsys.readouterr().out

    assert ret == 0
    assert '"run_id": "run_demo"' in out


def test_cli_harness_replay_outputs_trace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        def replay_run(self, run_id: str, session_id: str | None = None):
            _ = session_id
            return {"run_id": run_id, "status": "blocked", "failure_tags": ["tool_loop"]}

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["harness", "replay", "run_demo"])
    out = capsys.readouterr().out

    assert ret == 0
    assert '"status": "blocked"' in out


def test_cli_harness_eval_outputs_failure_distribution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        async def aggregate_failures(self, session_id: str | None = None):
            _ = session_id
            return {"total_runs": 2, "failure_distribution": {"tool_loop": 1}}

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["harness", "eval"])
    out = capsys.readouterr().out

    assert ret == 0
    assert '"tool_loop": 1' in out


def test_cli_debug_summary_outputs_latest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        def load_latest_snapshot(self, session_id: str):
            return HarnessSessionSnapshot(
                session_id=session_id,
                turn_id="turn_demo",
                run_id="run_demo",
                stop_reason="completed",
            )

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["debug", "summary", "session_demo"])
    out = capsys.readouterr().out

    assert ret == 0
    assert '"turn_id": "turn_demo"' in out


def test_cli_debug_snapshot_returns_not_found_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        def load_snapshot(self, session_id: str, turn_id: str):
            _ = session_id, turn_id
            raise FileNotFoundError(turn_id)

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["debug", "snapshot", "session_demo", "--turn-id", "turn_missing"])
    out = capsys.readouterr().out

    assert ret == 1
    assert "未找到" in out


def test_cli_harness_eval_gate_returns_nonzero_when_gate_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _FakeStore:
        def evaluate_core_recipe_benchmarks(self, session_id: str | None = None):
            _ = session_id
            return {
                "core_recipe_benchmarks": {
                    "gate_passed": False,
                    "pass_rate": 0.5,
                    "sample_results": [],
                }
            }

    monkeypatch.setattr("nini.harness.store.HarnessTraceStore", _FakeStore)
    ret = main(["harness", "eval", "--gate"])
    out = capsys.readouterr().out

    assert ret == 1
    assert '"gate_passed": false' in out
