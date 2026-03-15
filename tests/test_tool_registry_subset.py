"""测试 ToolRegistry.create_subset() 方法。"""

import logging
import pytest
from nini.tools.registry import create_default_tool_registry


def test_subset_contains_only_allowed_tools():
    registry = create_default_tool_registry()
    subset = registry.create_subset(["stat_test", "dataset_catalog"])
    names = subset.list_skills()
    assert "stat_test" in names
    assert "dataset_catalog" in names
    # 其他工具不应存在
    assert "code_session" not in names


def test_nonexistent_tool_skipped_with_warning(caplog):
    registry = create_default_tool_registry()
    with caplog.at_level(logging.WARNING, logger="nini.tools.registry"):
        subset = registry.create_subset(["stat_test", "nonexistent_tool"])
    names = subset.list_skills()
    assert "stat_test" in names
    assert "nonexistent_tool" not in names
    assert any("nonexistent_tool" in r.message for r in caplog.records)


def test_original_registry_unaffected():
    registry = create_default_tool_registry()
    original_count = len(registry.list_skills())
    registry.create_subset(["stat_test"])
    assert len(registry.list_skills()) == original_count


def test_empty_subset():
    registry = create_default_tool_registry()
    subset = registry.create_subset([])
    assert subset.list_skills() == []


def test_get_tool_definitions_only_has_subset_tools():
    registry = create_default_tool_registry()
    subset = registry.create_subset(["stat_test"])
    # 工具定义只应包含 stat_test
    defs = subset.get_tool_definitions()
    names = [d["function"]["name"] for d in defs]
    assert all(n == "stat_test" for n in names)
