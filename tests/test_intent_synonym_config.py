"""测试意图同义词 YAML 外置配置加载逻辑。"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from nini.intent.optimized import OptimizedIntentAnalyzer, _load_synonym_map

# ─── Task 3.5：配置文件存在时使用 YAML 同义词 ───────────────────────────────────


def test_load_synonym_map_uses_yaml_when_file_exists(tmp_path: Path) -> None:
    """配置文件存在时，_load_synonym_map 应加载 YAML 内容（含仅在 YAML 中存在的测试词）。"""
    yaml_content = (
        "difference_analysis:\n"
        "  - 差异\n"
        "  - yaml_only_test_word\n"
        "visualization:\n"
        "  - 画图\n"
    )
    config_file = tmp_path / "config" / "intent_synonyms.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(yaml_content, encoding="utf-8")

    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        result = _load_synonym_map()

    assert "yaml_only_test_word" in result.get("difference_analysis", [])
    assert "画图" in result.get("visualization", [])


def test_analyzer_uses_yaml_synonyms(tmp_path: Path) -> None:
    """OptimizedIntentAnalyzer 在 YAML 配置存在时应使用 YAML 同义词。"""
    yaml_content = "difference_analysis:\n" "  - yaml_only_test_word\n"
    config_file = tmp_path / "config" / "intent_synonyms.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(yaml_content, encoding="utf-8")

    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        analyzer = OptimizedIntentAnalyzer()

    assert "yaml_only_test_word" in analyzer._synonym_map.get("difference_analysis", [])


# ─── Task 3.6：配置文件不存在时回退内置 ─────────────────────────────────────────


def test_load_synonym_map_falls_back_when_file_missing(tmp_path: Path) -> None:
    """config/intent_synonyms.yaml 不存在时，应回退内置 _SYNONYM_MAP 且不抛出异常。"""
    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        result = _load_synonym_map()

    # 回退时返回内置 dict 的副本，应含内置能力
    assert "difference_analysis" in result
    assert "visualization" in result


def test_analyzer_no_exception_when_config_missing(tmp_path: Path) -> None:
    """配置文件不存在时，OptimizedIntentAnalyzer 实例化不应抛出异常。"""
    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        analyzer = OptimizedIntentAnalyzer()

    assert analyzer._synonym_map  # 内置 dict 非空


# ─── Task 3.7：配置文件格式非法时回退并记录 WARNING ────────────────────────────


def test_load_synonym_map_fallback_on_invalid_format(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """顶层结构非 dict 时应回退内置并记录 WARNING 级别日志。"""
    config_file = tmp_path / "config" / "intent_synonyms.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("- item1\n- item2\n", encoding="utf-8")  # list 结构，非法

    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        with caplog.at_level(logging.WARNING, logger="nini.intent.optimized"):
            result = _load_synonym_map()

    assert "difference_analysis" in result  # 回退到内置
    assert any("回退内置" in r.message for r in caplog.records)


# ─── Task 3.8：value 非列表的条目被跳过，其余正常加载 ───────────────────────────


def test_load_synonym_map_skips_non_list_values(tmp_path: Path) -> None:
    """value 为字符串（非列表）的条目应被跳过，其余正常加载。"""
    yaml_content = (
        "difference_analysis:\n"
        "  - 差异\n"
        "bad_entry: this_is_a_string\n"  # value 为字符串，应跳过
        "visualization:\n"
        "  - 画图\n"
    )
    config_file = tmp_path / "config" / "intent_synonyms.yaml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(yaml_content, encoding="utf-8")

    with patch("nini.intent.optimized._get_bundle_root", return_value=tmp_path):
        result = _load_synonym_map()

    assert "bad_entry" not in result
    assert "差异" in result.get("difference_analysis", [])
    assert "画图" in result.get("visualization", [])
