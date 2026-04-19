"""代码档案 bundle 构建测试。"""

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
