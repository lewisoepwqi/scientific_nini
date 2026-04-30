"""版本来源一致性测试。"""

from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

import nini
from nini.app import create_app
from nini.version import get_current_version


def _project_version() -> str:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_current_version_matches_project_metadata() -> None:
    assert get_current_version() == _project_version()


def test_package_fallback_version_matches_project_version() -> None:
    assert nini.__version__ == _project_version()


def test_fastapi_app_uses_current_version() -> None:
    app = create_app()
    assert app.version == get_current_version()


def test_version_falls_back_to_package_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    import nini.version as version_module

    def fake_metadata_version(_name: str) -> str:
        raise version_module.metadata.PackageNotFoundError

    monkeypatch.setattr(version_module.metadata, "version", fake_metadata_version)
    monkeypatch.setattr(nini, "__version__", "9.8.7")

    assert version_module.get_current_version() == "9.8.7"


def test_version_falls_back_to_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    import nini.version as version_module

    def fake_metadata_version(_name: str) -> str:
        raise version_module.metadata.PackageNotFoundError

    monkeypatch.setattr(version_module.metadata, "version", fake_metadata_version)
    monkeypatch.setattr(nini, "__version__", "")

    assert version_module.get_current_version() == version_module.FALLBACK_VERSION
