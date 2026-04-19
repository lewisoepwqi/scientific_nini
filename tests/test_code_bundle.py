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
