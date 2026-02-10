"""Phase 6：clean_data / generate_report / export_chart 技能测试。"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import threading

import numpy as np
import pandas as pd
import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.skills.base import Skill, SkillResult
from nini.skills.registry import SkillRegistry
from nini.skills.registry import create_default_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    yield


def test_clean_data_generates_cleaned_dataset() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame(
        {
            "group": ["a", "a", "b", None],
            "value": [1.0, np.nan, 2.0, 3.0],
        }
    )

    result = asyncio.run(
        registry.execute(
            "clean_data",
            session=session,
            dataset_name="exp.csv",
            missing_strategy="mean",
            inplace=False,
            output_dataset_name="exp_clean.csv",
        )
    )

    assert result["success"] is True, result
    assert result["data"]["output_dataset"] == "exp_clean.csv"
    assert result["data"]["missing_after"] == 0
    assert "exp_clean.csv" in session.datasets
    assert session.datasets["exp_clean.csv"].isna().sum().sum() == 0


def test_generate_report_writes_artifact_and_knowledge() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame({"x": [1, 2, 3]})
    session.add_message("user", "请分析数据")
    session.add_tool_result("tc-1", '{"message":"t 检验结果显著"}')

    result = asyncio.run(
        registry.execute(
            "generate_report",
            session=session,
            title="测试报告",
            summary_text="药物组优于对照组。",
            filename="phase6_report.md",
            save_to_knowledge=True,
        )
    )

    assert result["success"] is True, result
    artifacts = result.get("artifacts") or []
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["name"] == "phase6_report.md"

    report_path = Path(artifact["path"])
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "# 测试报告" in text
    assert "药物组优于对照组。" in text

    knowledge_text = session.knowledge_memory.read()
    assert "## 测试报告" in knowledge_text


def test_export_chart_exports_html_artifact() -> None:
    registry = create_default_registry()
    session = Session()
    session.datasets["exp.csv"] = pd.DataFrame({"group": ["a", "b"], "value": [1.2, 2.4]})

    chart_res = asyncio.run(
        registry.execute(
            "create_chart",
            session=session,
            dataset_name="exp.csv",
            chart_type="bar",
            x_column="group",
            y_column="value",
            journal_style="nature",
            title="Bar Chart",
        )
    )
    assert chart_res["success"] is True, chart_res

    export_res = asyncio.run(
        registry.execute(
            "export_chart",
            session=session,
            format="html",
            filename="phase6_export",
        )
    )
    assert export_res["success"] is True, export_res
    artifact = export_res["artifacts"][0]
    assert artifact["name"] == "phase6_export.html"
    assert Path(artifact["path"]).exists()
    assert artifact["download_url"].endswith("/phase6_export.html")


def test_skill_execute_runs_in_worker_thread() -> None:
    """技能执行应在线程池中运行，避免阻塞主事件循环。"""

    class ThreadProbeSkill(Skill):
        @property
        def name(self) -> str:
            return "thread_probe"

        @property
        def description(self) -> str:
            return "测试技能线程执行位置"

        @property
        def parameters(self) -> dict[str, object]:
            return {"type": "object", "properties": {}}

        async def execute(self, session: Session, **kwargs) -> SkillResult:
            return SkillResult(
                success=True,
                data={"thread_id": threading.get_ident()},
                message="ok",
            )

    registry = SkillRegistry()
    registry.register(ThreadProbeSkill())
    session = Session()

    main_thread_id = threading.get_ident()
    result = asyncio.run(registry.execute("thread_probe", session=session))

    assert result["success"] is True, result
    assert result["data"]["thread_id"] != main_thread_id


def test_registry_execute_signature_avoids_name_collision() -> None:
    """`execute` 的技能名参数不应占用 `name`，避免与工具入参冲突。"""
    sig = inspect.signature(SkillRegistry.execute)
    params = sig.parameters
    assert "skill_name" in params
    assert "name" not in params

    bound = sig.bind(
        object(),
        "save_workflow",
        session=object(),
        name="模板A",
    )
    assert bound.arguments["skill_name"] == "save_workflow"


def test_organize_workspace_creates_folder_and_moves_file() -> None:
    registry = create_default_registry()
    session = Session()
    wm = WorkspaceManager(session.id)
    note = wm.save_text_note("实验记录", "lab-notes.md")

    result = asyncio.run(
        registry.execute(
            "organize_workspace",
            session=session,
            create_folders=[{"name": "研究笔记"}],
            moves=[{"file_id": note["id"], "folder_name": "研究笔记"}],
        )
    )

    assert result["success"] is True, result
    created = result["data"]["created_folders"]
    moved = result["data"]["moved_files"]
    assert len(created) == 1
    assert len(moved) == 1
    folder_id = created[0]["id"]
    files = wm.list_workspace_files()
    moved_note = next((f for f in files if f["id"] == note["id"]), None)
    assert moved_note is not None
    assert moved_note["folder"] == folder_id
