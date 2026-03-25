"""归档文件名防碰撞测试。

验证 _archive_messages 在同一秒内生成的两个归档文件名不同。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from nini.config import settings


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离数据目录。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()


def test_archive_filenames_unique_within_same_second() -> None:
    """同一秒内生成的两个归档文件名应不同（UUID 短码防碰撞）。"""
    from nini.memory.compression import _archive_messages

    with patch("nini.memory.compression._now_ts", return_value="20260325_120000"):
        path1 = _archive_messages("sess_test", [{"role": "user", "content": "hello"}])
        path2 = _archive_messages("sess_test", [{"role": "user", "content": "world"}])

    assert path1.name != path2.name
    assert path1.name.startswith("compressed_20260325_120000_")
    assert path2.name.startswith("compressed_20260325_120000_")
    assert path1.name.endswith(".json")
    assert path2.name.endswith(".json")
