"""代码档案 bundle 构建测试。"""

import pytest

from nini.workspace.code_bundle import _make_slug


def test_make_slug_prefers_intent():
    assert _make_slug("X 列标准化", None, "exploration") == "x-列标准化"


def test_make_slug_falls_back_to_label():
    assert _make_slug(None, "Sales Chart", "visualization") == "sales-chart"


def test_make_slug_falls_back_to_purpose():
    assert _make_slug(None, None, "visualization") == "visualization"


def test_make_slug_truncates_long_text():
    long = "a" * 100
    result = _make_slug(long, None, "exploration")
    assert len(result) <= 40


def test_make_slug_sanitizes_special_chars():
    assert _make_slug("a/b c!@#d", None, "exploration") == "a-b-c-d"


def test_make_slug_handles_empty_strings():
    assert _make_slug("   ", "", "exploration") == "exploration"


from nini.workspace.code_bundle import _extract_dependencies


def test_extract_deps_empty_script():
    assert _extract_dependencies("", "python") == []


def test_extract_deps_stdlib_filtered():
    code = "import json\nimport re\nimport math"
    assert _extract_dependencies(code, "python") == []


def test_extract_deps_scientific_packages():
    code = "import pandas as pd\nimport numpy as np"
    deps = _extract_dependencies(code, "python")
    assert sorted(deps) == ["numpy", "pandas"]


def test_extract_deps_from_import():
    code = "from sklearn.linear_model import LinearRegression"
    assert _extract_dependencies(code, "python") == ["scikit-learn"]


def test_extract_deps_alias_mapping():
    code = "import cv2\nfrom PIL import Image"
    deps = _extract_dependencies(code, "python")
    assert sorted(deps) == ["Pillow", "opencv-python"]


def test_extract_deps_deduplicates():
    code = "import pandas\nimport pandas as pd\nfrom pandas import DataFrame"
    assert _extract_dependencies(code, "python") == ["pandas"]


def test_extract_deps_r_returns_empty_mvp():
    # MVP: R 依赖识别尚未实现，返回空清单（由 install.R 模板提供基础依赖）
    assert _extract_dependencies("library(ggplot2)", "r") == []


def test_extract_deps_syntax_error_returns_empty():
    # 语法错误不应抛，返回空列表，README 会提示用户手工核对
    assert _extract_dependencies("def broken(", "python") == []


from nini.workspace.code_bundle import _patch_script


def test_patch_script_includes_metadata_header():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "abc123",
        "session_id": "sess7890",
        "created_at": "2026-04-18T03:56:56Z",
        "intent": "x 列标准化",
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert "意图：x 列标准化" in result
    assert "执行 ID：abc123" in result
    assert "purpose=exploration" in result


def test_patch_script_injects_df_when_dataset_name_set():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "a",
        "session_id": "s",
        "created_at": "t",
        "intent": None,
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert 'datasets = {p.stem: pd.read_csv(p) for p in _DATASETS_DIR.glob("*.csv")}' in result
    assert 'df = datasets["raw"].copy()' in result


def test_patch_script_skips_df_binding_when_no_dataset():
    code = "print('hello')"
    tool_args = {"purpose": "exploration"}
    meta = {
        "execution_id": "a",
        "session_id": "s",
        "created_at": "t",
        "intent": None,
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert "datasets =" in result
    assert "df = datasets[" not in result


def test_patch_script_preserves_original_code():
    code = "output_df = df.copy()\noutput_df['x_norm'] = output_df['x'] * 2"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "a",
        "session_id": "s",
        "created_at": "t",
        "intent": None,
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert "output_df = df.copy()" in result
    assert "output_df['x_norm'] = output_df['x'] * 2" in result


def test_patch_script_appends_to_csv_fallback():
    code = "output_df = df.copy()"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "a",
        "session_id": "s",
        "created_at": "t",
        "intent": None,
        "tool_name": "run_code",
    }
    result = _patch_script(code, "python", tool_args, meta)
    assert 'if "output_df" in dir()' in result
    assert "output_df.to_csv" in result


def test_patch_script_r_minimal_header_only():
    code = "df %>% mutate(x_norm = scale(x))"
    tool_args = {"dataset_name": "raw.csv", "purpose": "exploration"}
    meta = {
        "execution_id": "a",
        "session_id": "s",
        "created_at": "t",
        "intent": "test",
        "tool_name": "run_r_code",
    }
    result = _patch_script(code, "r", tool_args, meta)
    assert "# 意图：test" in result
    assert "df %>% mutate" in result


from nini.workspace import WorkspaceManager
from nini.workspace.code_bundle import _resolve_dataset_files, _resolve_output_names


@pytest.fixture
def workspace_with_dataset(tmp_path, monkeypatch):
    """生成临时工作区，含一个 CSV 数据集。"""
    from nini.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    ws = WorkspaceManager("sess12345678")
    ws.ensure_dirs()
    csv_path = ws.uploads_dir / "raw.csv"
    csv_content = "x,y\n1,2\n3,4\n"
    csv_path.write_text(csv_content, encoding="utf-8")
    ws.add_dataset_record(
        dataset_id="ds_raw_test",
        name="raw.csv",
        file_path=csv_path,
        file_type="csv",
        file_size=len(csv_content.encode("utf-8")),
        row_count=2,
        column_count=2,
    )
    return ws


def test_resolve_dataset_files_by_name(workspace_with_dataset):
    ws = workspace_with_dataset
    tool_args = {"dataset_name": "raw.csv"}
    files = _resolve_dataset_files(ws, tool_args)
    assert len(files) == 1
    assert files[0].name == "raw.csv"
    assert files[0].exists()


def test_resolve_dataset_files_no_match(workspace_with_dataset):
    tool_args = {"dataset_name": "nonexistent.csv"}
    assert _resolve_dataset_files(workspace_with_dataset, tool_args) == []


def test_resolve_dataset_files_no_dataset_arg(workspace_with_dataset):
    assert _resolve_dataset_files(workspace_with_dataset, {}) == []


def test_resolve_output_names_uses_index(workspace_with_dataset):
    ws = workspace_with_dataset
    index = ws._load_index()
    index.setdefault("artifacts", []).append(
        {
            "id": "art_xyz",
            "name": "sales_chart.png",
            "file_type": "png",
        }
    )
    ws._save_index(index)
    names = _resolve_output_names(ws, ["art_xyz", "unknown_id"])
    assert "sales_chart.png" in names
    assert "unknown_id" in names


from nini.workspace.code_bundle import _render_batch_readme, _render_single_readme


def test_render_single_readme_includes_key_sections():
    record = {
        "id": "abc123",
        "session_id": "sess7890abcdef",
        "created_at": "2026-04-18T03:56:56Z",
        "language": "python",
        "intent": "x 列标准化",
        "tool_args": {"purpose": "exploration", "dataset_name": "raw.csv"},
    }
    readme = _render_single_readme(
        record, dataset_files=["raw.csv"], output_names=["normalized.csv"]
    )
    assert "# x 列标准化" in readme
    assert "sess7890" in readme
    assert "abc123" in readme
    assert "datasets/raw.csv" in readme
    assert "normalized.csv" in readme
    assert "bash run.sh" in readme


def test_render_single_readme_visualization_caveat():
    record = {
        "id": "a",
        "session_id": "s",
        "created_at": "t",
        "language": "python",
        "intent": "销售图表",
        "tool_args": {"purpose": "visualization"},
    }
    readme = _render_single_readme(record, dataset_files=[], output_names=[])
    assert "fig.show()" in readme or "fig.write_html" in readme


def test_render_batch_readme_lists_all_steps():
    records = [
        {
            "id": "a1",
            "created_at": "2026-04-18T01:00:00Z",
            "intent": "步骤1",
            "language": "python",
            "tool_args": {"purpose": "exploration"},
        },
        {
            "id": "a2",
            "created_at": "2026-04-18T02:00:00Z",
            "intent": "步骤2",
            "language": "python",
            "tool_args": {"purpose": "visualization"},
        },
    ]
    slugs = ["01_步骤1", "02_步骤2"]
    readme = _render_batch_readme(records, slugs, session_id="sess7890abcdef")
    assert "步骤1" in readme
    assert "步骤2" in readme
    assert "01_步骤1/script" in readme
    assert "02_步骤2/script" in readme


import io
import zipfile

from nini.workspace.code_bundle import build_single_bundle


def test_build_single_bundle_contains_all_files(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code="output_df = df.copy()\noutput_df['y2'] = output_df['y'] * 2",
        output="已保存",
        status="success",
        language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="测试归档",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "README.md" in names
    assert "script.py" in names
    assert "requirements.txt" in names
    assert "run.sh" in names
    assert "datasets/raw.csv" in names


def test_build_single_bundle_script_has_patch_header(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code="output_df = df.copy()",
        output="",
        status="success",
        language="python",
        tool_name="run_code",
        tool_args={"purpose": "exploration", "dataset_name": "raw.csv"},
        intent="测试",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        script = zf.read("script.py").decode("utf-8")
    assert "Nini 代码档案" in script
    assert 'df = datasets["raw"].copy()' in script
    assert "output_df = df.copy()" in script


def test_build_single_bundle_missing_execution_raises(workspace_with_dataset):
    with pytest.raises(ValueError, match="不存在"):
        build_single_bundle(workspace_with_dataset, "nonexistent_id")


def test_build_single_bundle_r_script_uses_r_extension(workspace_with_dataset):
    ws = workspace_with_dataset
    exec_record = ws.save_code_execution(
        code="df <- data.frame(x=1:3)",
        output="",
        status="success",
        language="r",
        tool_name="run_r_code",
        tool_args={"purpose": "exploration"},
        intent="r 测试",
    )
    zip_bytes = build_single_bundle(ws, exec_record["id"])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "script.R" in names
    assert "script.py" not in names
