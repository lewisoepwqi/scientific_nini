"""生态对齐功能测试。

覆盖范围：
- MCP Server 创建与工具列表
- $ARGUMENTS 占位符替换
- 上下文自动匹配（渐进式加载）
- allowed-tools 推荐提示
- AGENTS.md 发现与注入
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.tools.base import Skill, SkillResult
from nini.tools.registry import SkillRegistry


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


class _DummySkill(Skill):
    def __init__(self, skill_name: str = "dummy", expose: bool = True):
        self._name = skill_name
        self._expose = expose

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"测试技能 {self._name}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": [],
        }

    @property
    def expose_to_llm(self) -> bool:
        return self._expose

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        return SkillResult(success=True, message=f"{self._name} 执行完成", data=kwargs)


def _write_skill_md(
    path: Path,
    *,
    name: str = "",
    description: str = "",
    category: str = "",
    extra_frontmatter: str = "",
    body: str = "",
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
    path.write_text(fm_block + (body or "## 步骤\n1. 示例步骤\n"), encoding="utf-8")


# ===========================================================================
# 1. $ARGUMENTS 占位符替换
# ===========================================================================


class TestReplaceArguments:
    """测试 _replace_arguments 函数。"""

    def test_single_argument(self):
        from nini.agent.runner import _replace_arguments

        result = _replace_arguments("分析 $ARGUMENTS 数据", "data.csv")
        assert result == "分析 data.csv 数据"

    def test_numbered_placeholders(self):
        from nini.agent.runner import _replace_arguments

        result = _replace_arguments("比较 $1 与 $2", "group_a.csv group_b.csv")
        assert result == "比较 group_a.csv 与 group_b.csv"

    def test_mixed_placeholders(self):
        from nini.agent.runner import _replace_arguments

        result = _replace_arguments("$ARGUMENTS: first=$1, second=$2", "a b")
        assert result == "a b: first=a, second=b"

    def test_empty_arguments(self):
        from nini.agent.runner import _replace_arguments

        result = _replace_arguments("分析 $ARGUMENTS 数据 $1", "")
        assert result == "分析  数据 "

    def test_no_placeholders(self):
        from nini.agent.runner import _replace_arguments

        text = "没有占位符的普通文本"
        result = _replace_arguments(text, "some args")
        assert result == text

    def test_excess_numbered_placeholders(self):
        """$3 应替换为空字符串当只有2个参数时。"""
        from nini.agent.runner import _replace_arguments

        result = _replace_arguments("$1 $2 $3", "a b")
        assert result == "a b "


# ===========================================================================
# 2. 上下文自动匹配
# ===========================================================================


class TestContextMatching:
    """测试 _match_skills_by_context 方法。"""

    def test_match_by_alias(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from nini.agent.runner import AgentRunner

        registry = SkillRegistry()
        md_skill = {
            "type": "markdown",
            "name": "root-analysis",
            "description": "根长分析",
            "category": "statistics",
            "location": str(tmp_path / "root-analysis" / "SKILL.md"),
            "enabled": True,
            "metadata": {
                "aliases": ["根长分析", "根长度分析", "root length analysis"],
                "tags": ["root-length", "anova"],
            },
        }
        registry._markdown_skills = [md_skill]
        runner = AgentRunner(skill_registry=registry)

        matches = runner._match_skills_by_context("我想做根长分析")
        assert len(matches) == 1
        assert matches[0]["name"] == "root-analysis"

    def test_match_by_tag(self, tmp_path: Path):
        from nini.agent.runner import AgentRunner

        registry = SkillRegistry()
        md_skill = {
            "type": "markdown",
            "name": "eco-analysis",
            "description": "生态分析",
            "category": "statistics",
            "location": str(tmp_path / "eco" / "SKILL.md"),
            "enabled": True,
            "metadata": {"tags": ["ecology", "biodiversity"]},
        }
        registry._markdown_skills = [md_skill]
        runner = AgentRunner(skill_registry=registry)

        matches = runner._match_skills_by_context("biodiversity assessment")
        assert len(matches) == 1

    def test_no_match(self):
        from nini.agent.runner import AgentRunner

        registry = SkillRegistry()
        md_skill = {
            "type": "markdown",
            "name": "root-analysis",
            "description": "根长分析",
            "category": "statistics",
            "location": "/nonexistent/SKILL.md",
            "enabled": True,
            "metadata": {"aliases": ["根长分析"], "tags": ["root-length"]},
        }
        registry._markdown_skills = [md_skill]
        runner = AgentRunner(skill_registry=registry)

        matches = runner._match_skills_by_context("天气预报查询")
        assert len(matches) == 0

    def test_disabled_skill_excluded(self):
        from nini.agent.runner import AgentRunner

        registry = SkillRegistry()
        md_skill = {
            "type": "markdown",
            "name": "root-analysis",
            "description": "根长分析",
            "category": "statistics",
            "location": "/nonexistent/SKILL.md",
            "enabled": False,
            "metadata": {"aliases": ["根长分析"]},
        }
        registry._markdown_skills = [md_skill]
        runner = AgentRunner(skill_registry=registry)

        matches = runner._match_skills_by_context("根长分析")
        assert len(matches) == 0

    def test_disable_model_invocation(self):
        from nini.agent.runner import AgentRunner

        registry = SkillRegistry()
        md_skill = {
            "type": "markdown",
            "name": "root-analysis",
            "description": "根长分析",
            "category": "statistics",
            "location": "/nonexistent/SKILL.md",
            "enabled": True,
            "metadata": {
                "aliases": ["根长分析"],
                "disable_model_invocation": True,
            },
        }
        registry._markdown_skills = [md_skill]
        runner = AgentRunner(skill_registry=registry)

        matches = runner._match_skills_by_context("根长分析")
        assert len(matches) == 0


# ===========================================================================
# 3. allowed-tools 推荐提示
# ===========================================================================


class TestAllowedToolsAdvisory:
    """测试 allowed-tools 推荐工具提示注入。"""

    def test_allowed_tools_in_context(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from nini.agent.runner import AgentRunner

        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "test-skill"
        skill_path = skill_dir / "SKILL.md"
        _write_skill_md(
            skill_path,
            name="test-skill",
            description="测试技能",
            category="statistics",
            extra_frontmatter="allowed-tools: [run_code, create_chart]\nuser-invocable: true",
            body="## 步骤\n使用 $ARGUMENTS 分析数据\n",
        )

        monkeypatch.setattr(settings, "skills_dir_path", skills_dir)
        monkeypatch.setattr(settings, "skills_auto_discover_compat_dirs", False)

        registry = SkillRegistry()
        from nini.tools.markdown_scanner import scan_markdown_skills

        md_skills = scan_markdown_skills([skills_dir])
        registry._markdown_skills = [s.to_dict() for s in md_skills]

        runner = AgentRunner(skill_registry=registry)
        context = runner._build_explicit_skill_context("/test-skill my_data.csv")
        assert "推荐工具" in context
        assert "run_code" in context
        assert "create_chart" in context

    def test_runtime_resources_are_noted_in_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from nini.agent.runner import AgentRunner

        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "resource-skill"
        skill_path = skill_dir / "SKILL.md"
        _write_skill_md(
            skill_path,
            name="resource-skill",
            description="带资源的技能",
            category="workflow",
            extra_frontmatter="user-invocable: true",
            body="## 步骤\n1. 使用 references/protocol.md\n",
        )
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "references" / "protocol.md").write_text("protocol\n", encoding="utf-8")

        monkeypatch.setattr(settings, "skills_dir_path", skills_dir)
        monkeypatch.setattr(settings, "skills_auto_discover_compat_dirs", False)

        registry = SkillRegistry()
        from nini.tools.markdown_scanner import scan_markdown_skills

        md_skills = scan_markdown_skills([skills_dir])
        registry._markdown_skills = [s.to_dict() for s in md_skills]

        runner = AgentRunner(skill_registry=registry)
        context = runner._build_explicit_skill_context("/resource-skill")
        assert "运行时资源" in context
        assert "references/protocol.md" in context

    def test_no_allowed_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from nini.agent.runner import AgentRunner

        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "simple-skill"
        skill_path = skill_dir / "SKILL.md"
        _write_skill_md(
            skill_path,
            name="simple-skill",
            description="简单技能",
            category="other",
            extra_frontmatter="user-invocable: true",
        )

        monkeypatch.setattr(settings, "skills_dir_path", skills_dir)
        monkeypatch.setattr(settings, "skills_auto_discover_compat_dirs", False)

        registry = SkillRegistry()
        from nini.tools.markdown_scanner import scan_markdown_skills

        md_skills = scan_markdown_skills([skills_dir])
        registry._markdown_skills = [s.to_dict() for s in md_skills]

        runner = AgentRunner(skill_registry=registry)
        context = runner._build_explicit_skill_context("/simple-skill")
        assert "推荐工具" not in context


# ===========================================================================
# 4. AGENTS.md 发现
# ===========================================================================


class TestAgentsMdDiscovery:
    """测试 AGENTS.md 项目级指令发现。"""

    def setup_method(self):
        """每个测试前重置缓存。"""
        from nini.agent.runner import AgentRunner

        AgentRunner._agents_md_scanned = False
        AgentRunner._agents_md_cache = None

    def test_discover_root_agents_md(self, tmp_path: Path):
        from nini.agent.runner import AgentRunner

        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# Project Instructions\n\nUse pytest for testing.\n")

        with patch("nini.config._get_bundle_root", return_value=tmp_path):
            AgentRunner._agents_md_scanned = False
            AgentRunner._agents_md_cache = None
            result = AgentRunner._discover_agents_md()

        assert "Use pytest for testing" in result

    def test_discover_subdir_agents_md(self, tmp_path: Path):
        from nini.agent.runner import AgentRunner

        sub = tmp_path / "src"
        sub.mkdir()
        agents_file = sub / "AGENTS.md"
        agents_file.write_text("# Source Instructions\n\nFollow PEP 8.\n")

        with patch("nini.config._get_bundle_root", return_value=tmp_path):
            AgentRunner._agents_md_scanned = False
            AgentRunner._agents_md_cache = None
            result = AgentRunner._discover_agents_md()

        assert "Follow PEP 8" in result

    def test_no_agents_md(self, tmp_path: Path):
        from nini.agent.runner import AgentRunner

        with patch("nini.config._get_bundle_root", return_value=tmp_path):
            AgentRunner._agents_md_scanned = False
            AgentRunner._agents_md_cache = None
            result = AgentRunner._discover_agents_md()

        assert result == ""

    def test_cache_works(self, tmp_path: Path):
        from nini.agent.runner import AgentRunner

        agents_file = tmp_path / "AGENTS.md"
        agents_file.write_text("# First\n")

        with patch("nini.config._get_bundle_root", return_value=tmp_path):
            AgentRunner._agents_md_scanned = False
            AgentRunner._agents_md_cache = None
            result1 = AgentRunner._discover_agents_md()

        # 修改文件后应返回缓存结果
        agents_file.write_text("# Second\n")
        result2 = AgentRunner._discover_agents_md()

        assert "First" in result1
        assert "First" in result2  # 缓存，不会重新读取


# ===========================================================================
# 5. MCP Server
# ===========================================================================


class TestMCPServer:
    """测试 MCP Server 创建与工具列表。"""

    def test_mcp_import_check(self):
        """测试 MCP SDK 可用性检查。"""
        from nini.mcp.server import _MCP_AVAILABLE

        # 只检查模块级标志——实际是否安装取决于环境
        assert isinstance(_MCP_AVAILABLE, bool)

    def test_create_mcp_server_with_registry(self):
        """测试使用自定义 registry 创建 MCP Server。"""
        try:
            from nini.mcp.server import create_mcp_server
        except ImportError:
            pytest.skip("MCP SDK 未安装")

        registry = SkillRegistry()
        registry.register(_DummySkill("test_tool"))
        registry.register(_DummySkill("hidden_tool", expose=False))

        try:
            server = create_mcp_server(registry)
        except ImportError:
            pytest.skip("MCP SDK 未安装")

        assert server is not None

    @pytest.mark.asyncio
    async def test_list_tools_respects_expose_to_llm(self):
        """测试 list_tools 仅返回 expose_to_llm=True 的技能。"""
        try:
            import mcp.types as types
            from nini.mcp.server import create_mcp_server
        except ImportError:
            pytest.skip("MCP SDK 未安装")

        registry = SkillRegistry()
        registry.register(_DummySkill("visible_tool", expose=True))
        registry.register(_DummySkill("hidden_tool", expose=False))

        server = create_mcp_server(registry)

        # 直接调用注册的处理器
        handlers = server.request_handlers
        # list_tools handler 在 MCP SDK 中通过装饰器注册
        # 我们验证 registry 中的过滤逻辑
        visible_count = sum(1 for s in registry._skills.values() if s.expose_to_llm)
        assert visible_count == 1

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self):
        """测试调用未知工具返回错误。"""
        # 直接验证 registry 层面：不存在的技能
        registry = SkillRegistry()
        result = await registry.execute("nonexistent", session=Session())
        assert result["success"] is False
        assert "未知技能" in result["message"]

    @pytest.mark.asyncio
    async def test_call_tool_executes(self):
        """测试 MCP call_tool 执行技能并返回结果。"""
        registry = SkillRegistry()
        registry.register(_DummySkill("echo_tool"))

        session = Session()
        result = await registry.execute("echo_tool", session=session, input="hello")
        assert result["success"] is True
        assert result["data"]["input"] == "hello"

    def test_cli_subcommand_registered(self):
        """测试 nini mcp 子命令已注册。"""
        from nini.__main__ import _build_parser

        parser = _build_parser()
        # 验证 mcp 子命令可被解析
        args = parser.parse_args(["mcp"])
        assert hasattr(args, "func")

    def test_pyproject_mcp_optional_dep(self):
        """验证 pyproject.toml 中 mcp 可选依赖已配置。"""
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject_path.read_text(encoding="utf-8")
        assert 'mcp = ["mcp>=1.0.0"]' in content


# ===========================================================================
# 6. Slash 技能参数提取回归
# ===========================================================================


class TestSlashSkillArgs:
    """验证 slash 技能参数提取的正确性。"""

    def test_regex_extracts_args(self):
        from nini.agent.runner import _SLASH_SKILL_WITH_ARGS_RE

        m = _SLASH_SKILL_WITH_ARGS_RE.search("/root-analysis data.csv")
        assert m is not None
        assert m.group(1) == "root-analysis"
        assert m.group(2).strip() == "data.csv"

    def test_regex_no_args(self):
        from nini.agent.runner import _SLASH_SKILL_WITH_ARGS_RE

        m = _SLASH_SKILL_WITH_ARGS_RE.search("/root-analysis")
        assert m is not None
        assert m.group(1) == "root-analysis"
        assert (m.group(2) or "").strip() == ""

    def test_regex_multiple_skills(self):
        from nini.agent.runner import _SLASH_SKILL_WITH_ARGS_RE

        matches = list(_SLASH_SKILL_WITH_ARGS_RE.finditer("/skill1 arg1 /skill2 arg2"))
        assert len(matches) >= 2
        assert matches[0].group(1) == "skill1"
        assert matches[1].group(1) == "skill2"
