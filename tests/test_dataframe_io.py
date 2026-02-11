"""DataFrame 读取工具测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nini.utils.dataframe_io import (
    read_dataframe,
    read_excel_all_sheets,
    read_excel_sheet_dataframe,
)


def test_read_dataframe_xlsx_uses_openpyxl_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, str] = {}

    def fake_read_excel(
        path: Path,
        engine: str | None = None,
        sheet_name: object | None = None,
    ):  # type: ignore[override]
        called["engine"] = str(engine)
        called["sheet_name"] = str(sheet_name)
        return pd.DataFrame({"a": [1]})

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    df = read_dataframe(Path("/tmp/demo.xlsx"), "xlsx")
    assert called["engine"] == "openpyxl"
    assert called["sheet_name"] == "0"
    assert len(df) == 1


def test_read_dataframe_xls_missing_xlrd_raises_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_read_excel(
        path: Path,
        engine: str | None = None,
        sheet_name: object | None = None,
    ):  # type: ignore[override]
        raise ImportError(
            "Import xlrd failed. Install xlrd >= 2.0.1 for xls Excel support."
        )

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)

    with pytest.raises(ValueError) as exc:
        read_dataframe(Path("/tmp/legacy.xls"), "xls")

    text = str(exc.value)
    assert "xlrd" in text
    assert "pip install" in text


def test_read_dataframe_csv_ok(tmp_path: Path) -> None:
    path = tmp_path / "demo.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    df = read_dataframe(path, "csv")
    assert list(df.columns) == ["a", "b"]
    assert int(df.iloc[0]["a"]) == 1


def test_read_dataframe_xls_encrypted_raises_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_read_excel(
        path: Path,
        engine: str | None = None,
        sheet_name: object | None = None,
    ):  # type: ignore[override]
        raise Exception("Workbook is encrypted")

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)

    with pytest.raises(ValueError) as exc:
        read_dataframe(Path("/tmp/encrypted.xls"), "xls")

    text = str(exc.value)
    assert "文件已加密" in text
    assert "Excel/WPS" in text


def test_read_excel_sheet_dataframe_passes_sheet_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, str] = {}

    def fake_read_excel(
        path: Path,
        engine: str | None = None,
        sheet_name: object | None = None,
    ):  # type: ignore[override]
        called["engine"] = str(engine)
        called["sheet_name"] = str(sheet_name)
        return pd.DataFrame({"x": [1]})

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    df = read_excel_sheet_dataframe(Path("/tmp/demo.xlsx"), "xlsx", sheet_name="S2")
    assert called["engine"] == "openpyxl"
    assert called["sheet_name"] == "S2"
    assert list(df.columns) == ["x"]


def test_read_excel_all_sheets_returns_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_read_excel(
        path: Path,
        engine: str | None = None,
        sheet_name: object | None = None,
    ):  # type: ignore[override]
        assert sheet_name is None
        return {"A": pd.DataFrame({"x": [1]}), "B": pd.DataFrame({"x": [2]})}

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    result = read_excel_all_sheets(Path("/tmp/demo.xlsx"), "xlsx")
    assert set(result.keys()) == {"A", "B"}
