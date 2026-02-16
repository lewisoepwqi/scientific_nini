"""Phase 7：CLI 命令与首启引导测试。"""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from nini.__main__ import main
from nini.config import settings


def test_cli_init_creates_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.nini"
    ret = main(["init", "--env-file", str(env_path)])
    assert ret == 0
    assert env_path.exists()
    text = env_path.read_text(encoding="utf-8")
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


def test_cli_doctor_returns_success_with_default_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    ret = main(["doctor"])
    assert ret == 0
