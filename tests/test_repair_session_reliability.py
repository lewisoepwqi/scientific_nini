"""历史会话可靠性修复脚本测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from nini.config import settings
from nini.memory.db import get_session_db, load_meta_from_db, upsert_meta_fields
from nini.memory.compression import (
    StatisticResult,
    clear_session_analysis_memory_cache,
    clear_session_analysis_memories,
    get_analysis_memory,
)


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


def test_repair_pending_actions_removes_task_state_idempotent_conflict() -> None:
    from scripts.repair_session_reliability import repair_pending_actions

    session_dir = settings.sessions_dir / "sess_pending"
    session_dir.mkdir(parents=True)
    meta = {
        "pending_actions": [
            {
                "type": "tool_failure_unresolved",
                "key": 'task_state::{"operation": "init"}',
                "summary": "task_state 失败：任务列表已初始化且无法重新初始化。",
                "source_tool": "task_state",
            },
            {
                "type": "tool_failure_unresolved",
                "key": "stat_model::real-error",
                "summary": "stat_model 失败：参数错误。",
                "source_tool": "stat_model",
            },
        ]
    }
    (session_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    report = repair_pending_actions(session_dir, apply_changes=True)

    repaired = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert report["removed_pending_actions"] == 1
    assert len(repaired["pending_actions"]) == 1
    assert repaired["pending_actions"][0]["source_tool"] == "stat_model"


def test_repair_pending_actions_removes_workspace_read_false_blockers_and_updates_db() -> None:
    from scripts.repair_session_reliability import repair_pending_actions

    session_dir = settings.sessions_dir / "sess_workspace_read"
    upload_dir = session_dir / "workspace" / "uploads"
    upload_dir.mkdir(parents=True)
    (upload_dir / "4ac463bc2600_血压心率_20220407.xlsx").write_bytes(b"PK\x03\x04excel")

    meta = {
        "pending_actions": [
            {
                "type": "tool_failure_unresolved",
                "key": 'workspace_session::{"file_path": "血压心率_20220407.xlsx", "operation": "read"}',
                "summary": "workspace_session 失败：文件不存在: 血压心率_20220407.xlsx",
                "source_tool": "workspace_session",
                "blocking": True,
                "failure_category": "blocking_failure",
            },
            {
                "type": "tool_failure_unresolved",
                "key": (
                    'workspace_session::{"file_path": '
                    '"uploads/4ac463bc2600_血压心率_20220407.xlsx", "operation": "read"}'
                ),
                "summary": (
                    "workspace_session 失败：读取文件失败: "
                    "'utf-8' codec can't decode byte 0x8c in position 15: invalid start byte"
                ),
                "source_tool": "workspace_session",
                "blocking": True,
                "failure_category": "blocking_failure",
            },
        ]
    }
    (session_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    conn = get_session_db(session_dir, create=True)
    assert conn is not None
    try:
        upsert_meta_fields(conn, meta)
    finally:
        conn.close()

    report = repair_pending_actions(session_dir, apply_changes=True)

    repaired_json = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert report["removed_pending_actions"] == 2
    assert repaired_json["pending_actions"] == []

    conn = get_session_db(session_dir, create=False)
    assert conn is not None
    try:
        repaired_db = load_meta_from_db(conn)
    finally:
        conn.close()
    assert repaired_db["pending_actions"] == []


def test_repair_analysis_memories_rebuilds_correlation_statistics() -> None:
    from scripts.repair_session_reliability import repair_analysis_memories

    session_id = "sess_repair"
    session_dir = settings.sessions_dir / session_id
    (session_dir / "workspace" / "uploads").mkdir(parents=True)

    df = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
            "z": [6, 5, 4, 3, 2, 1],
        }
    )
    df.to_csv(session_dir / "workspace" / "uploads" / "upload_demo.csv", index=False)

    memory = get_analysis_memory(session_id, "demo.csv")
    memory.add_statistic(
        StatisticResult(
            test_name="Spearman 相关性分析",
            p_value=None,
            effect_size=None,
            significant=False,
            ltm_id="ltm-bad-1",
        )
    )
    clear_session_analysis_memory_cache(session_id)

    tool_call = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_stat_1",
                "type": "function",
                "function": {
                    "name": "stat_model",
                    "arguments": json.dumps(
                        {
                            "method": "correlation",
                            "dataset_name": "demo.csv",
                            "columns": ["x", "y", "z"],
                            "correlation_method": "spearman",
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }
    (session_dir / "memory.jsonl").write_text(
        json.dumps(tool_call, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    fake_store = MagicMock()
    fake_store.delete_memory = MagicMock(return_value=True)

    with (
        patch(
            "scripts.repair_session_reliability.get_long_term_memory_store", return_value=fake_store
        ),
        patch(
            "scripts.repair_session_reliability.consolidate_session_memories",
            new=AsyncMock(return_value=3),
        ),
    ):
        report = repair_analysis_memories(
            session_id,
            session_dir=session_dir,
            apply_changes=True,
        )

    repaired = get_analysis_memory(session_id, "demo.csv")
    assert report["repaired_statistics"] == 3
    assert fake_store.delete_memory.called
    assert len(repaired.statistics) == 3
    assert all(item.p_value is not None for item in repaired.statistics)
    assert all(isinstance(item.significant, bool) for item in repaired.statistics)

    clear_session_analysis_memories(session_id)
