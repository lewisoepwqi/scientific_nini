"""技能系统架构修复测试。

覆盖范围：
- execute() 对 Markdown Skill 的错误提示
- register() 重复注册检测
- MarkdownSkill 的 category / to_manifest() 支持
- scan_markdown_skills() 的 frontmatter 解析与验证
- render_skills_snapshot() 的 category 输出
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.tools.base import Skill, SkillResult
from nini.tools.markdown_scanner import (
    VALID_CATEGORIES,
    MarkdownSkill,
    render_skills_snapshot,
    scan_markdown_skills,
)
from nini.tools.registry import SkillRegistry, create_default_registry


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


def _write_skill_md(
    path: Path,
    *,
    name: str = "",
    description: str = "",
    category: str = "",
    extra_frontmatter: str = "",
) -> None:
    """写入一个带 frontmatter 的 SKILL.md。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = []
    if name:
        fm_lines.append(f"name: {name}")
    if description:
        fm_lines.append(f"description: {description}")
    if category:
        fm_lines.append(f"category: {category}")
    if extra_frontmatter:
        fm_lines.append(extra_frontmatter)
    fm_block = "---\n" + "\n".join(fm_lines) + "\n---\n\n" if fm_lines else ""
    path.write_text(fm_block + "## 步骤\n1. 示例步骤\n", encoding="utf-8")


class _DummySkill(Skill):
    """用于测试注册逻辑的占位技能。"""

    def __init__(self, skill_name: str = "dummy"):
        self._name = skill_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "测试用占位技能"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, session: Session, **kwargs) -> SkillResult:
        return SkillResult(success=True, message="ok")


# ---------------------------------------------------------------------------
# 1. execute() 对 Markdown Skill 的错误提示
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_markdown_skill_returns_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """尝试 execute 一个 Markdown 技能名应返回明确的提示词技能说明。"""
    skills_dir = tmp_path / "skills"
    _write_skill_md(
        skills_dir / "my_guide" / "SKILL.md",
        name="my_guide",
        description="指导说明",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    registry = create_default_registry()
    session = Session()
    result = await registry.execute("my_guide", session=session)

    assert result["success"] is False
    assert "提示词类型技能" in result["message"]
    assert "my_guide" in result["message"]


@pytest.mark.asyncio
async def test_execute_unknown_skill_returns_unknown_error() -> None:
    """执行不存在的技能名应返回 '未知技能'。"""
    registry = SkillRegistry()
    session = Session()
    result = await registry.execute("nonexistent_skill", session=session)

    assert result["success"] is False
    assert "未知技能" in result["message"]


# ---------------------------------------------------------------------------
# 2. register() 重复注册检测
# ---------------------------------------------------------------------------


def test_register_duplicate_raises_value_error() -> None:
    """重复注册同名技能应抛出 ValueError。"""
    registry = SkillRegistry()
    registry.register(_DummySkill("alpha"))

    with pytest.raises(ValueError, match="技能名称冲突"):
        registry.register(_DummySkill("alpha"))


def test_register_duplicate_with_allow_override() -> None:
    """传入 allow_override=True 时允许覆盖。"""
    registry = SkillRegistry()
    skill_a = _DummySkill("alpha")
    skill_b = _DummySkill("alpha")

    registry.register(skill_a)
    registry.register(skill_b, allow_override=True)

    assert registry.get("alpha") is skill_b


def test_register_different_names_no_conflict() -> None:
    """注册不同名称的技能不应冲突。"""
    registry = SkillRegistry()
    registry.register(_DummySkill("alpha"))
    registry.register(_DummySkill("beta"))

    assert set(registry.list_skills()) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# 3. MarkdownSkill 的 category 与 to_manifest()
# ---------------------------------------------------------------------------


def test_markdown_skill_to_dict_includes_category() -> None:
    """MarkdownSkill.to_dict() 应包含 category 字段。"""
    skill = MarkdownSkill(
        name="test_skill",
        description="测试",
        location="/tmp/SKILL.md",
        category="visualization",
    )
    d = skill.to_dict()

    assert d["category"] == "visualization"
    assert d["type"] == "markdown"


def test_markdown_skill_to_manifest() -> None:
    """MarkdownSkill.to_manifest() 应返回正确的 SkillManifest。"""
    skill = MarkdownSkill(
        name="pub_fig",
        description="生成期刊图表",
        location="/tmp/SKILL.md",
        category="visualization",
    )
    manifest = skill.to_manifest()

    assert manifest.name == "pub_fig"
    assert manifest.description == "生成期刊图表"
    assert manifest.category == "visualization"
    assert manifest.parameters == {}


# ---------------------------------------------------------------------------
# 4. scan_markdown_skills() 解析与验证
# ---------------------------------------------------------------------------


def test_scan_parses_category_from_frontmatter(tmp_path: Path) -> None:
    """扫描应正确解析 frontmatter 中的 category 字段。"""
    _write_skill_md(
        tmp_path / "my_skill" / "SKILL.md",
        name="my_skill",
        description="测试技能",
        category="statistics",
    )
    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    assert results[0].category == "statistics"


def test_scan_defaults_category_to_other(tmp_path: Path) -> None:
    """缺少 category 时应回退到 'other'。"""
    _write_skill_md(
        tmp_path / "no_cat" / "SKILL.md",
        name="no_cat",
        description="无分类",
    )
    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    assert results[0].category == "other"


def test_scan_invalid_category_falls_back_to_other(tmp_path: Path) -> None:
    """非法 category 应回退到 'other' 并输出警告。"""
    _write_skill_md(
        tmp_path / "bad_cat" / "SKILL.md",
        name="bad_cat",
        description="非法分类",
        category="nonexistent_category",
    )
    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    assert results[0].category == "other"


def test_scan_fallback_name_from_folder(tmp_path: Path) -> None:
    """缺少 frontmatter name 时应回退到文件夹名。"""
    _write_skill_md(
        tmp_path / "folder_name_skill" / "SKILL.md",
        description="有描述无名称",
    )
    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    assert results[0].name == "folder_name_skill"


def test_scan_no_frontmatter_at_all(tmp_path: Path) -> None:
    """完全没有 frontmatter 的 SKILL.md 也应能被扫描。"""
    skill_path = tmp_path / "raw_skill" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text("这是一个纯文本技能定义\n", encoding="utf-8")

    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    assert results[0].name == "raw_skill"
    assert results[0].description == "这是一个纯文本技能定义"
    assert results[0].category == "other"


def test_scan_empty_dir(tmp_path: Path) -> None:
    """空目录应返回空列表。"""
    empty = tmp_path / "empty_skills"
    empty.mkdir()
    assert scan_markdown_skills(empty) == []


def test_scan_nonexistent_dir(tmp_path: Path) -> None:
    """不存在的目录应返回空列表。"""
    assert scan_markdown_skills(tmp_path / "does_not_exist") == []


def test_scan_parses_agent_skill_metadata(tmp_path: Path) -> None:
    """应兼容解析 Agent Skills 扩展 frontmatter 字段。"""
    _write_skill_md(
        tmp_path / "compat_skill" / "SKILL.md",
        name="compat_skill",
        description="兼容技能",
        category="workflow",
        extra_frontmatter=(
            "agents:\n"
            "  - openai/codex\n"
            "  - anthropic/claude-code\n"
            "aliases:\n"
            "  - 根长分析\n"
            "  - root length analysis\n"
            "allowed-tools:\n"
            "  - read_file\n"
            "  - run_tests\n"
            "argument-hint: issue-id\n"
            "user-invocable: true"
        ),
    )
    results = scan_markdown_skills(tmp_path)

    assert len(results) == 1
    metadata = results[0].metadata
    assert metadata.get("agents") == ["openai/codex", "anthropic/claude-code"]
    assert metadata.get("aliases") == ["根长分析", "root length analysis"]
    assert metadata.get("allowed_tools") == ["read_file", "run_tests"]
    assert metadata.get("argument_hint") == "issue-id"
    assert metadata.get("user_invocable") is True


def test_scan_supports_multiple_roots_with_priority(tmp_path: Path) -> None:
    """多目录扫描时应保留发现优先级信息。"""
    high_root = tmp_path / "high"
    low_root = tmp_path / "low"
    _write_skill_md(
        high_root / "same_skill" / "SKILL.md",
        name="same_skill",
        description="高优先级版本",
    )
    _write_skill_md(
        low_root / "same_skill" / "SKILL.md",
        name="same_skill",
        description="低优先级版本",
    )

    results = scan_markdown_skills([high_root, low_root])
    assert len(results) == 2
    assert results[0].metadata["discovery_priority"] == 0
    assert results[1].metadata["discovery_priority"] == 1


# ---------------------------------------------------------------------------
# 5. render_skills_snapshot() 包含 category
# ---------------------------------------------------------------------------


def test_snapshot_includes_category() -> None:
    """快照输出应包含 category 字段。"""
    skills = [
        {
            "name": "t_test",
            "type": "function",
            "category": "statistics",
            "enabled": True,
            "description": "t 检验",
            "location": "nini.tools.statistics.TTestSkill",
        },
        {
            "name": "pub_fig",
            "type": "markdown",
            "category": "visualization",
            "enabled": True,
            "description": "期刊图表",
            "location": "/skills/publication_figure/SKILL.md",
        },
    ]
    text = render_skills_snapshot(skills)

    assert "category: statistics" in text
    assert "category: visualization" in text


# ---------------------------------------------------------------------------
# 6. 集成：create_default_registry 全流程
# ---------------------------------------------------------------------------


def test_create_default_registry_no_duplicate_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认注册流程不应出现重复名称冲突。"""
    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty_skills")
    (tmp_path / "empty_skills").mkdir()

    registry = create_default_registry()
    names = registry.list_skills()
    assert len(names) == len(set(names)), "存在重复注册的技能名称"


def test_catalog_includes_category_for_both_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """聚合目录中 Function 和 Markdown 技能都应带有 category。"""
    skills_dir = tmp_path / "skills"
    _write_skill_md(
        skills_dir / "guide" / "SKILL.md",
        name="guide",
        description="指南",
        category="report",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    registry = create_default_registry()
    catalog = registry.list_skill_catalog()

    for item in catalog:
        assert "category" in item, f"技能 {item['name']} 缺少 category 字段"


def test_valid_categories_constant() -> None:
    """VALID_CATEGORIES 应包含预期的标准分类。"""
    expected = {
        "data",
        "statistics",
        "visualization",
        "export",
        "report",
        "workflow",
        "utility",
        "other",
    }
    assert VALID_CATEGORIES == expected


# ===========================================================================
# Phase 3 测试：分类统一、ToolAdapter、CLI
# ===========================================================================

# ---------------------------------------------------------------------------
# 7. 分类统一：所有 Function Skill 必须使用标准分类
# ---------------------------------------------------------------------------


def test_all_function_skills_use_valid_categories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """所有 Function Skill 的 category 必须在 VALID_CATEGORIES 中。"""
    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    registry = create_default_registry()
    for item in registry.list_function_skills():
        assert (
            item["category"] in VALID_CATEGORIES
        ), f"技能 {item['name']} 使用了非标准分类 '{item['category']}'"


def test_no_skills_use_deprecated_categories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不应存在已废弃的分类值（code, composite）。"""
    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    registry = create_default_registry()
    deprecated = {"code", "composite"}
    for item in registry.list_function_skills():
        assert (
            item["category"] not in deprecated
        ), f"技能 {item['name']} 使用了已废弃分类 '{item['category']}'"


# ---------------------------------------------------------------------------
# 8. ToolAdapter 测试
# ---------------------------------------------------------------------------


def test_tool_adapter_to_openai_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ToolAdapter 应能导出 OpenAI 工具列表。"""
    from nini.tools.tool_adapter import ToolAdapter

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    registry = create_default_registry()
    adapter = ToolAdapter(registry)
    tools = adapter.to_openai_tools()

    assert len(tools) > 0
    for tool in tools:
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "parameters" in tool["function"]


def test_tool_adapter_to_mcp_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ToolAdapter 应能导出 MCP 工具列表。"""
    from nini.tools.tool_adapter import ToolAdapter

    skills_dir = tmp_path / "skills"
    _write_skill_md(
        skills_dir / "guide" / "SKILL.md",
        name="guide",
        description="指南",
        category="report",
    )
    monkeypatch.setattr(settings, "skills_dir_path", skills_dir)

    registry = create_default_registry()
    adapter = ToolAdapter(registry)
    tools = adapter.to_mcp_tools()

    assert len(tools) > 0
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool

    # 确认包含 Markdown Skill
    mcp_names = {t["name"] for t in tools}
    assert "guide" in mcp_names


def test_tool_adapter_to_claude_code_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ToolAdapter 应能导出 Claude Code Markdown 格式。"""
    from nini.tools.tool_adapter import ToolAdapter

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    registry = create_default_registry()
    adapter = ToolAdapter(registry)
    md = adapter.to_claude_code_markdown()

    assert "# Nini 技能目录" in md
    assert "t_test" in md


def test_to_mcp_tool_single_skill() -> None:
    """to_mcp_tool 应正确转换单个技能。"""
    from nini.tools.tool_adapter import to_mcp_tool

    skill = _DummySkill("test_mcp")
    mcp = to_mcp_tool(skill)

    assert mcp["name"] == "test_mcp"
    assert mcp["description"] == "测试用占位技能"
    assert mcp["inputSchema"] == {"type": "object", "properties": {}}


def test_to_openai_tool_single_skill() -> None:
    """to_openai_tool 应正确转换单个技能。"""
    from nini.tools.tool_adapter import to_openai_tool

    skill = _DummySkill("test_openai")
    oai = to_openai_tool(skill)

    assert oai["type"] == "function"
    assert oai["function"]["name"] == "test_openai"


# ---------------------------------------------------------------------------
# 9. CLI 测试
# ---------------------------------------------------------------------------


def test_cli_skills_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills list 应输出技能列表。"""
    import argparse

    from nini.__main__ import _cmd_skills_list

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    args = argparse.Namespace(type="all", category=None, output_format="table")
    ret = _cmd_skills_list(args)

    assert ret == 0
    out = capsys.readouterr().out
    assert "t_test" in out
    assert "create_chart" in out


def test_cli_skills_list_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills list --format json 应输出合法 JSON。"""
    import argparse
    import json

    from nini.__main__ import _cmd_skills_list

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    args = argparse.Namespace(type="all", category=None, output_format="json")
    ret = _cmd_skills_list(args)

    assert ret == 0
    out = capsys.readouterr().out
    catalog = json.loads(out)
    assert isinstance(catalog, list)
    assert len(catalog) > 0


def test_cli_skills_list_filter_by_category(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills list --category statistics 应仅显示统计类技能。"""
    import argparse
    import json

    from nini.__main__ import _cmd_skills_list

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    args = argparse.Namespace(type="all", category="statistics", output_format="json")
    _cmd_skills_list(args)

    out = capsys.readouterr().out
    catalog = json.loads(out)
    for item in catalog:
        assert item["category"] == "statistics"


def test_cli_skills_create_function(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills create 应创建 Function Skill 脚手架。"""
    import argparse

    from nini.__main__ import _cmd_skills_create

    # 把脚手架目标目录指向 tmp_path
    skills_module_dir = tmp_path / "skills_module"
    skills_module_dir.mkdir()
    monkeypatch.setattr(
        "nini.__main__._create_function_skill",
        lambda name, desc, cat: _create_function_skill_in(skills_module_dir, name, desc, cat),
    )

    args = argparse.Namespace(
        skill_name="test_skill",
        skill_type="function",
        category="statistics",
        description="测试技能",
    )
    ret = _cmd_skills_create(args)
    assert ret == 0


def _create_function_skill_in(target_dir: Path, name: str, description: str, category: str) -> int:
    """测试辅助：在指定目录创建 Function Skill 脚手架。"""
    target = target_dir / f"{name}.py"
    target.write_text(f"# {name} - {description} ({category})\n", encoding="utf-8")
    print(f"已创建 Function Skill 脚手架：{target}")
    return 0


def test_cli_skills_create_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills create --type markdown 应创建 Markdown Skill 脚手架。"""
    import argparse

    from nini.__main__ import _cmd_skills_create

    skills_root = tmp_path / "skills_root"
    monkeypatch.setattr(
        "nini.__main__._create_markdown_skill",
        lambda name, desc, cat: _create_markdown_skill_in(skills_root, name, desc, cat),
    )

    args = argparse.Namespace(
        skill_name="test_guide",
        skill_type="markdown",
        category="report",
        description="测试指南",
    )
    ret = _cmd_skills_create(args)
    assert ret == 0


def _create_markdown_skill_in(skills_root: Path, name: str, description: str, category: str) -> int:
    """测试辅助：在指定目录创建 Markdown Skill 脚手架。"""
    target_dir = skills_root / name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "SKILL.md"
    target.write_text(
        f"---\nname: {name}\ndescription: {description}\ncategory: {category}\n---\n",
        encoding="utf-8",
    )
    print(f"已创建 Markdown Skill 脚手架：{target}")
    return 0


def test_cli_skills_create_invalid_name(capsys: pytest.CaptureFixture[str]) -> None:
    """非法技能名称应被拒绝。"""
    import argparse

    from nini.__main__ import _cmd_skills_create

    args = argparse.Namespace(
        skill_name="Invalid-Name",
        skill_type="function",
        category="other",
        description="",
    )
    ret = _cmd_skills_create(args)
    assert ret == 1
    assert "不合法" in capsys.readouterr().out


def test_cli_skills_export_mcp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """nini skills export --format mcp 应输出合法 JSON。"""
    import argparse
    import json

    from nini.__main__ import _cmd_skills_export

    monkeypatch.setattr(settings, "skills_dir_path", tmp_path / "empty")
    (tmp_path / "empty").mkdir()

    args = argparse.Namespace(export_format="mcp", output=None)
    ret = _cmd_skills_export(args)
    assert ret == 0

    out = capsys.readouterr().out
    tools = json.loads(out)
    assert isinstance(tools, list)
    assert all("inputSchema" in t for t in tools)
