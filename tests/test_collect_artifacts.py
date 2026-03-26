"""collect_artifacts 工具测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.memory.compression import StatisticResult, get_analysis_memory
from nini.models import MethodsLedgerEntry, ReportSessionRecord, ResourceType
from nini.tools.collect_artifacts import CollectArtifactsTool
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    yield


def _persist_report_record(session_id: str) -> None:
    manager = WorkspaceManager(session_id)
    manager.ensure_dirs()

    record = ReportSessionRecord(
        id="report_test_001",
        session_id=session_id,
        title="分析记录",
        methods_ledger=[
            MethodsLedgerEntry(
                entry_id="method_001",
                step_name="差异分析",
                method_name="独立样本 t 检验",
                tool_name="stat_test",
                data_sources=["demo.csv"],
                key_parameters={"alpha": 0.05},
                notes="用于比较实验组与对照组",
            )
        ],
    )
    report_path = manager.build_managed_resource_path(
        ResourceType.REPORT,
        "report_test_001.json",
        default_name="report",
    )
    report_path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manager.upsert_managed_resource(
        resource_id=record.id,
        resource_type=ResourceType.REPORT,
        name=record.title,
        path=report_path,
        source_kind="reports",
        metadata={"methods_entry_count": len(record.methods_ledger)},
    )


@pytest.mark.asyncio
async def test_collect_artifacts_returns_structured_bundle_for_populated_session() -> None:
    session = Session(id="session_collect_full")
    session.datasets["demo.csv"] = pd.DataFrame(
        {"group": ["A", "A", "B", "B"], "score": [1.2, 1.5, 2.3, 2.1]}
    )

    memory = get_analysis_memory(session.id, "demo.csv")
    memory.add_statistic(
        StatisticResult(
            test_name="独立样本 t 检验",
            test_statistic=2.45,
            p_value=0.021,
            degrees_of_freedom=6,
            effect_size=0.73,
            effect_type="cohens_d",
            significant=True,
        )
    )

    manager = WorkspaceManager(session.id)
    manager.ensure_dirs()
    dataset_path = manager.uploads_dir / "demo.csv"
    dataset_path.write_text("group,score\nA,1.2\nA,1.5\nB,2.3\nB,2.1\n", encoding="utf-8")
    manager.add_dataset_record(
        dataset_id="dataset_demo",
        name="demo.csv",
        file_path=dataset_path,
        file_type="csv",
        file_size=dataset_path.stat().st_size,
        row_count=4,
        column_count=2,
    )
    chart_path = manager.artifacts_dir / "group_difference.png"
    chart_path.write_bytes(b"fake-png")
    manager.add_artifact_record(
        name="group_difference.png",
        artifact_type="chart",
        file_path=chart_path,
        format_hint="png",
    )
    _persist_report_record(session.id)

    result = await CollectArtifactsTool().execute(session)

    assert result.success is True
    assert result.data["summary"]["mode"] == "analysis_bridge"
    assert result.data["summary"]["statistical_result_count"] == 1
    assert result.data["summary"]["chart_count"] == 1
    assert result.data["summary"]["method_count"] == 1
    assert result.data["summary"]["dataset_count"] == 1
    assert result.data["statistical_results"][0]["method_name"] == "独立样本 t 检验"
    assert result.data["statistical_results"][0]["p_value"] == pytest.approx(0.021)
    assert result.data["charts"][0]["title"] == "group_difference.png"
    assert result.data["methods"][0]["step_name"] == "差异分析"
    assert result.data["datasets"][0]["columns"] == ["group", "score"]


@pytest.mark.asyncio
async def test_collect_artifacts_returns_empty_bundle_for_blank_session() -> None:
    result = await CollectArtifactsTool().execute(Session(id="session_collect_empty"))

    assert result.success is True
    assert result.data["statistical_results"] == []
    assert result.data["charts"] == []
    assert result.data["methods"] == []
    assert result.data["datasets"] == []
    assert result.data["summary"]["mode"] == "pure_guidance"
    assert result.data["summary"]["has_analysis_artifacts"] is False


def test_collect_artifacts_is_registered_in_default_registry() -> None:
    registry = create_default_tool_registry()

    assert registry.get("collect_artifacts") is not None
