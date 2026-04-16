"""Excel 多 sheet 加载模式测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.tools.registry import create_default_tool_registry
from nini.workspace import WorkspaceManager


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


def _prepare_multi_sheet_excel(session: Session, dataset_name: str = "multi.xlsx") -> None:
    manager = WorkspaceManager(session.id)
    manager.ensure_dirs()

    dataset_id = "excel_multi_sheet"
    save_path = manager.uploads_dir / f"{dataset_id}_{dataset_name}"

    df_a = pd.DataFrame({"id": [1, 2], "value_a": [10, 20]})
    df_b = pd.DataFrame({"id": [3, 4], "value_b": [30, 40]})
    with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
        df_a.to_excel(writer, sheet_name="SheetA", index=False)
        df_b.to_excel(writer, sheet_name="SheetB", index=False)

    manager.add_dataset_record(
        dataset_id=dataset_id,
        name=dataset_name,
        file_path=save_path,
        file_type="xlsx",
        file_size=save_path.stat().st_size,
        row_count=2,
        column_count=2,
    )


@pytest.mark.asyncio
async def test_load_dataset_single_sheet_mode() -> None:
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "load_dataset",
        session=session,
        dataset_name="multi.xlsx",
        sheet_mode="single",
        sheet_name="SheetB",
    )

    assert result["success"] is True, result
    output_name = result["data"]["output_dataset"]
    assert output_name in session.datasets
    df = session.datasets[output_name]
    assert list(df.columns) == ["id", "value_b"]
    assert df["id"].tolist() == [3, 4]


@pytest.mark.asyncio
async def test_load_dataset_all_sheets_separate_mode() -> None:
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "load_dataset",
        session=session,
        dataset_name="multi.xlsx",
        sheet_mode="all",
        combine_sheets=False,
    )

    assert result["success"] is True, result
    created = result["data"]["created_datasets"]
    assert len(created) == 2
    names = {item["name"] for item in created}
    assert "multi.xlsx[SheetA]" in names
    assert "multi.xlsx[SheetB]" in names
    assert "multi.xlsx[SheetA]" in session.datasets
    assert "multi.xlsx[SheetB]" in session.datasets


@pytest.mark.asyncio
async def test_load_dataset_all_sheets_combined_mode() -> None:
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "load_dataset",
        session=session,
        dataset_name="multi.xlsx",
        sheet_mode="all",
        combine_sheets=True,
        include_sheet_column=True,
        output_dataset_name="combined_multi",
    )

    assert result["success"] is True, result
    output_name = result["data"]["output_dataset"]
    assert output_name == "combined_multi"
    assert output_name in session.datasets
    combined = session.datasets[output_name]
    assert len(combined) == 4
    assert "__sheet_name__" in combined.columns
    assert set(combined["__sheet_name__"].tolist()) == {"SheetA", "SheetB"}


@pytest.mark.asyncio
async def test_load_dataset_single_mode_missing_sheet_name_shows_available_sheets() -> None:
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "load_dataset",
        session=session,
        dataset_name="multi.xlsx",
        sheet_mode="single",
    )

    assert result["success"] is False
    message = str(result["message"])
    assert "sheet_mode=single" in message
    assert "SheetA" in message
    assert "SheetB" in message


# ---- profile 操作的 sheet 支持 ----


@pytest.mark.asyncio
async def test_profile_with_sheet_name_loads_specific_sheet() -> None:
    """profile 操作指定 sheet_name 应加载并预览该 sheet。"""
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="profile",
        dataset_name="multi.xlsx",
        view="preview",
        sheet_name="SheetB",
    )

    assert result["success"] is True, result
    data = result["data"]
    assert data["sheet_name"] == "SheetB"
    assert "preview" in data
    preview = data["preview"]
    assert preview["sheet_name"] == "SheetB"
    # SheetB 的数据是 id=[3,4], value_b=[30,40]
    assert preview["total_rows"] == 2
    col_names = [c["name"] for c in preview["columns"]]
    assert "value_b" in col_names
    assert "value_a" not in col_names


@pytest.mark.asyncio
async def test_profile_without_sheet_name_shows_available_sheets() -> None:
    """profile 操作未指定 sheet_name 时，多 sheet Excel 应返回 available_sheets 提示。"""
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="profile",
        dataset_name="multi.xlsx",
        view="basic",
    )

    assert result["success"] is True, result
    data = result["data"]
    assert "available_sheets" in data
    assert "SheetA" in data["available_sheets"]
    assert "SheetB" in data["available_sheets"]


@pytest.mark.asyncio
async def test_profile_with_invalid_sheet_name_returns_error() -> None:
    """profile 操作指定不存在的 sheet_name 应返回包含可用 sheet 的错误信息。"""
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    result = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="profile",
        dataset_name="multi.xlsx",
        view="preview",
        sheet_name="NonExistent",
    )

    assert result["success"] is False
    message = str(result["message"])
    assert "NonExistent" in message or "读取 sheet 失败" in message


@pytest.mark.asyncio
async def test_load_via_dataset_catalog_with_sheet_name_no_mode() -> None:
    """dataset_catalog load 传 sheet_name 但不传 sheet_mode 时，应加载指定 sheet 而非第一个 sheet。"""
    registry = create_default_tool_registry()
    session = Session()
    _prepare_multi_sheet_excel(session)

    # 不传 sheet_mode，只传 sheet_name="SheetB"
    result = await registry.execute(
        "dataset_catalog",
        session=session,
        operation="load",
        dataset_name="multi.xlsx",
        sheet_name="SheetB",
    )

    assert result["success"] is True, result.get("message")
    output_name = result["data"]["dataset_name"]
    assert "SheetB" in output_name
    assert output_name in session.datasets
    df = session.datasets[output_name]
    assert list(df.columns) == ["id", "value_b"]
    assert df["id"].tolist() == [3, 4]
