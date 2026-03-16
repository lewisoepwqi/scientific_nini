"""测试意图同义词 YAML 外置化加载逻辑。"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from nini.intent.optimized import _SYNONYM_MAP, _load_synonym_map


def _make_yaml(tmp_path: Path, content: str) -> Path:
    """在临时目录写入 YAML 并返回路径。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    yaml_path = config_dir / "intent_synonyms.yaml"
    yaml_path.write_text(content, encoding="utf-8")
    return tmp_path


def test_load_synonym_map_from_yaml(tmp_path: Path) -> None:
    """配置文件存在时，分析器使用 YAML 中的同义词。"""
    # 在 YAML 中加入一个仅在 YAML 中存在的测试词
    data = dict(_SYNONYM_MAP)
    data["difference_analysis"] = list(data["difference_analysis"]) + ["yaml专属测试词"]
    content = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    project_root = _make_yaml(tmp_path, content)

    with patch("nini.intent.optimized._PROJECT_ROOT", project_root):
        result = _load_synonym_map()

    assert "yaml专属测试词" in result["difference_analysis"]
    # 验证其他 capability 也正常加载
    assert "相关" in result.get("correlation_analysis", [])


def test_load_synonym_map_fallback_no_file(tmp_path: Path) -> None:
    """配置文件不存在时，正常回退到内置 dict，不抛出异常。"""
    with patch("nini.intent.optimized._PROJECT_ROOT", tmp_path):
        result = _load_synonym_map()

    # 应该返回内置 _SYNONYM_MAP 的副本
    assert result == dict(_SYNONYM_MAP)


def test_load_synonym_map_fallback_invalid_format(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """配置文件格式非法（非 dict）时，回退内置并记录 WARNING。"""
    # 写入一个列表而非 dict
    project_root = _make_yaml(tmp_path, "- item1\n- item2\n")

    with patch("nini.intent.optimized._PROJECT_ROOT", project_root):
        with caplog.at_level(logging.WARNING, logger="nini.intent.optimized"):
            result = _load_synonym_map()

    assert result == dict(_SYNONYM_MAP)
    assert any("回退内置" in record.message for record in caplog.records)


def test_load_synonym_map_skips_non_list_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """配置文件中某 value 非列表（如字符串）时，该条目被跳过，其余正常加载。"""
    content = (
        "difference_analysis:\n"
        "  - 差异\n"
        "  - 显著性\n"
        "correlation_analysis: '这是一个字符串而非列表'\n"
        "visualization:\n"
        "  - 可视化\n"
        "  - 画图\n"
    )
    project_root = _make_yaml(tmp_path, content)

    with patch("nini.intent.optimized._PROJECT_ROOT", project_root):
        with caplog.at_level(logging.WARNING, logger="nini.intent.optimized"):
            result = _load_synonym_map()

    # difference_analysis 和 visualization 正常加载
    assert "差异" in result["difference_analysis"]
    assert "可视化" in result["visualization"]
    # correlation_analysis 被跳过
    assert "correlation_analysis" not in result
    # 应有 WARNING 日志
    assert any("correlation_analysis" in record.message for record in caplog.records)
