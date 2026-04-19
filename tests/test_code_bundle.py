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
