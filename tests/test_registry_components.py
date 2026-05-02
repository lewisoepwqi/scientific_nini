"""拆分后的 ToolRegistry 组件测试。"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import (
    Tool,
    ToolError,
    ToolInputError,
    ToolResult,
    ToolSystemError,
    ToolTimeoutError,
)
from nini.tools.registry_catalog import ToolCatalogOps
from nini.tools.registry_core import FunctionToolRegistryOps
from nini.tools.registry_markdown import MarkdownToolRegistryOps


class _DummySkill(Tool):
    """用于测试注册与执行逻辑的占位工具。"""

    def __init__(self, tool_name: str = "dummy", *, expose_to_llm: bool = True):
        self._name = tool_name
        self._expose_to_llm = expose_to_llm

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "测试用工具"

    @property
    def expose_to_llm(self) -> bool:
        return self._expose_to_llm

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"value": {"type": "string"}}}

    async def execute(self, session: Session, **kwargs) -> ToolResult:
        return ToolResult(success=True, message=f"ok:{kwargs.get('value', '')}")


class _ErrorSkill(Tool):
    """用于测试异常分层调度的占位工具。"""

    def __init__(self, error: Exception):
        self._error = error

    @property
    def name(self) -> str:
        return "error_skill"

    @property
    def description(self) -> str:
        return "抛出异常的测试工具"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, session: Session, **kwargs) -> ToolResult:
        raise self._error


@pytest.fixture
def registry_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """构造最小 owner，用于直接测试拆分组件。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    monkeypatch.setattr(settings, "skills_extra_dirs", str(tmp_path / "skills-extra"))
    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "skills")

    owner = SimpleNamespace(
        _tools={},
        _markdown_tools=[],
        _markdown_enabled_overrides={},
        _fallback_manager=None,
        _diagnostics=None,
    )
    owner._function_ops = FunctionToolRegistryOps(owner)
    owner._markdown_ops = MarkdownToolRegistryOps(owner)
    owner._catalog_ops = ToolCatalogOps(owner)
    owner._function_ops.ensure_runtime_dependencies()
    owner._markdown_enabled_overrides = owner._markdown_ops.load_enabled_overrides()
    owner.list_function_tools = owner._function_ops.list_function_tools
    owner.list_markdown_tools = owner._markdown_ops.list_markdown_tools
    owner.get_markdown_tool = owner._markdown_ops.get_markdown_tool
    owner.write_tools_snapshot = owner._catalog_ops.write_tools_snapshot
    return owner


def _write_skill_md(path: Path, *, name: str, description: str, category: str = "workflow") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"category: {category}\n"
        "aliases: [实验技能]\n"
        "allowed-tools: [read_file]\n"
        "---\n\n"
        "# 步骤\n\n1. 读取数据\n",
        encoding="utf-8",
    )


def test_function_registry_ops_register_and_tool_definitions(registry_owner) -> None:
    """FunctionToolRegistryOps 应负责注册、列举与 LLM 工具定义。"""
    ops = registry_owner._function_ops
    ops.register(_DummySkill("alpha"))
    ops.register(_DummySkill("hidden", expose_to_llm=False))

    assert ops.list_tools() == ["alpha", "hidden"]
    assert ops.get("alpha") is not None

    definitions = ops.get_tool_definitions()
    assert [item["function"]["name"] for item in definitions] == ["alpha"]


def test_markdown_registry_ops_reload_disable_conflict_and_persist_override(
    registry_owner,
    tmp_path: Path,
) -> None:
    """MarkdownToolRegistryOps 应处理扫描、冲突禁用与启停覆盖。"""
    skills_dir = tmp_path / "skills-extra"
    _write_skill_md(skills_dir / "guide" / "SKILL.md", name="guide", description="说明文档")
    _write_skill_md(skills_dir / "alpha" / "SKILL.md", name="alpha", description="同名冲突")

    registry_owner._tools["alpha"] = _DummySkill("alpha")
    ops = registry_owner._markdown_ops

    items = ops.reload_markdown_tools(set(registry_owner._tools.keys()))

    guide = next(item for item in items if item["name"] == "guide")
    alpha = next(item for item in items if item["name"] == "alpha")
    assert guide["enabled"] is True
    assert alpha["enabled"] is False
    assert alpha["metadata"]["conflict_with"] == "function"

    updated = ops.set_markdown_tool_enabled("guide", False)
    assert updated is not None
    assert updated["enabled"] is False
    assert settings.skills_state_path.exists()


def test_markdown_registry_ops_duplicate_skills_log_summary_instead_of_warning(
    registry_owner,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """同名 Markdown 技能覆盖应输出汇总日志，而不是逐条 warning。"""
    skills_dir = tmp_path / "skills"
    extra_dir = tmp_path / "skills-extra"
    _write_skill_md(skills_dir / "guide" / "SKILL.md", name="guide", description="高优先级版本")
    _write_skill_md(extra_dir / "guide" / "SKILL.md", name="guide", description="低优先级版本")

    with caplog.at_level(logging.INFO):
        items = registry_owner._markdown_ops.reload_markdown_tools(
            set(registry_owner._tools.keys())
        )

    guide_items = [item for item in items if item["name"] == "guide"]
    assert len(guide_items) == 1
    assert any("同名 Markdown 技能覆盖" in record.message for record in caplog.records)
    assert not any("低优先级版本将被忽略" in record.message for record in caplog.records)


def test_catalog_ops_semantic_catalog_contains_matching_metadata(registry_owner) -> None:
    """ToolCatalogOps 应输出语义检索所需字段。"""
    registry_owner._function_ops.register(_DummySkill("alpha"))
    registry_owner._markdown_tools = [
        {
            "type": "markdown",
            "name": "guide",
            "description": "说明文档",
            "brief_description": "快速指南",
            "category": "workflow",
            "research_domain": "general",
            "difficulty_level": "intermediate",
            "typical_use_cases": ["入门"],
            "enabled": True,
            "location": "/tmp/guide/SKILL.md",
            "metadata": {
                "aliases": ["实验技能"],
                "tags": ["guide"],
                "allowed_tools": ["read_file"],
                "user_invocable": False,
                "disable_model_invocation": True,
            },
        }
    ]

    semantic_catalog = registry_owner._catalog_ops.get_semantic_catalog(skill_type="markdown")

    assert semantic_catalog == [
        {
            "name": "guide",
            "type": "markdown",
            "description": "说明文档",
            "brief_description": "快速指南",
            "category": "workflow",
            "research_domain": "general",
            "difficulty_level": "intermediate",
            "typical_use_cases": ["入门"],
            "enabled": True,
            "expose_to_llm": True,
            "user_invocable": False,
            "disable_model_invocation": True,
            "aliases": ["实验技能"],
            "tags": ["guide"],
            "allowed_tools": ["read_file"],
            "location": "/tmp/guide/SKILL.md",
        }
    ]


def test_catalog_ops_write_snapshot_outputs_markdown_and_function_sections(
    registry_owner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写快照时应包含 Function 与 Markdown 两类目录。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    registry_owner._function_ops.register(_DummySkill("alpha"))
    registry_owner._markdown_tools = [
        {
            "type": "markdown",
            "name": "guide",
            "description": "说明文档",
            "brief_description": "快速指南",
            "category": "workflow",
            "research_domain": "general",
            "difficulty_level": "intermediate",
            "typical_use_cases": [],
            "enabled": True,
            "location": "/tmp/guide/SKILL.md",
            "metadata": {},
        }
    ]

    registry_owner._catalog_ops.write_tools_snapshot()
    snapshot = settings.skills_snapshot_path.read_text(encoding="utf-8")

    assert "## available_tools" in snapshot
    assert "## available_markdown_skills" in snapshot
    assert "alpha" in snapshot
    assert "guide" in snapshot


def test_tool_exception_hierarchy_isinstance() -> None:
    """工具异常层次应满足继承关系与 isinstance 判定。"""
    input_error = ToolInputError("input")
    timeout_error = ToolTimeoutError("timeout")
    system_error = ToolSystemError("system")

    assert isinstance(input_error, ToolError)
    assert isinstance(timeout_error, ToolError)
    assert isinstance(system_error, ToolError)
    assert not isinstance(input_error, ToolTimeoutError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected", "level_name"),
    [
        (ToolInputError("参数错误"), {"success": False, "message": "参数错误"}, "INFO"),
        (
            ToolTimeoutError("执行超时"),
            {"success": False, "message": "执行超时", "retryable": True},
            "WARNING",
        ),
        (
            ToolSystemError("磁盘已满"),
            {"success": False, "message": "系统错误: 磁盘已满"},
            "ERROR",
        ),
        (
            RuntimeError("未知故障"),
            {"success": False, "message": "执行失败: 未知故障"},
            "ERROR",
        ),
    ],
)
async def test_function_registry_ops_execute_maps_exception_types(
    registry_owner,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected: dict[str, object],
    level_name: str,
) -> None:
    """execute 应按异常类型返回对应格式并记录合适日志级别。"""
    registry_owner._function_ops.register(_ErrorSkill(error), allow_override=True)
    caplog.set_level(logging.INFO)

    result = await registry_owner._function_ops.execute(
        "error_skill",
        Session(),
        lambda _: False,
    )

    assert result == expected
    assert any(record.levelname == level_name for record in caplog.records)
