"""Agent 注册中心。

提供 AgentDefinition 数据类和 AgentRegistry 注册中心，
支持加载内置 Specialist Agent 定义和自定义 YAML 配置。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 内置 Agent YAML 目录（随包发布）
_BUILTIN_AGENTS_DIR = Path(__file__).parent / "prompts" / "agents" / "builtin"
# 自定义 Agent YAML 目录（用户自定义，覆盖内置）
_CUSTOM_AGENTS_DIR = Path(__file__).parent / "prompts" / "agents"


@dataclass
class AgentDefinition:
    """Specialist Agent 的完整配置声明。"""

    agent_id: str
    name: str
    description: str
    system_prompt: str
    purpose: str
    allowed_tools: list[str] = field(default_factory=list)
    max_tokens: int = 8000
    timeout_seconds: int = 300
    paradigm: str = "react"
    max_spawn_depth: int = 0  # 允许派发子 Agent 的最大嵌套深度（0 = 禁止，1 = 允许一级嵌套）
    model_preference: str | None = None  # 子 Agent 首选模型等级：haiku/sonnet/opus/None（继承父模型）


class AgentRegistry:
    """Specialist Agent 注册中心。

    初始化时自动加载内置 Agent 定义（builtin/*.yaml）
    和用户自定义 Agent 定义（agents/*.yaml，同名覆盖内置）。
    """

    def __init__(self, tool_registry: Any = None) -> None:
        """初始化注册中心。

        Args:
            tool_registry: ToolRegistry 实例，用于校验 allowed_tools 工具名
        """
        self._agents: dict[str, AgentDefinition] = {}
        self._tool_registry = tool_registry
        self._load_builtin_agents()
        self._load_custom_agents()

    def register(self, agent_def: AgentDefinition) -> None:
        """注册一个 Agent 定义，并校验 allowed_tools 中的工具名。

        不存在的工具名记录 WARNING，不阻断注册。
        """
        if self._tool_registry is not None:
            available = set(self._tool_registry.list_tools())
            for tool_name in agent_def.allowed_tools:
                if tool_name not in available:
                    logger.warning(
                        "Agent '%s' 的 allowed_tools 包含未注册工具: '%s'",
                        agent_def.agent_id,
                        tool_name,
                    )
        # 校验 paradigm 字段合法性
        _valid_paradigms = {"react", "hypothesis_driven"}
        if agent_def.paradigm not in _valid_paradigms:
            logger.warning(
                "Agent '%s' 的 paradigm '%s' 不合法，有效值为 %s",
                agent_def.agent_id,
                agent_def.paradigm,
                _valid_paradigms,
            )
        self._agents[agent_def.agent_id] = agent_def
        logger.debug("注册 Agent: %s (%s)", agent_def.agent_id, agent_def.name)

    def get(self, agent_id: str) -> AgentDefinition | None:
        """按 ID 查询 Agent 定义，不存在时返回 None。"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentDefinition]:
        """返回所有已注册 Agent 定义列表。"""
        return list(self._agents.values())

    def _load_builtin_agents(self) -> None:
        """加载内置 Agent YAML 配置（builtin/ 目录）。"""
        if not _BUILTIN_AGENTS_DIR.exists():
            logger.debug("内置 Agent 目录不存在，跳过: %s", _BUILTIN_AGENTS_DIR)
            return
        self._load_yaml_dir(_BUILTIN_AGENTS_DIR)

    def _load_custom_agents(self) -> None:
        """加载自定义 Agent YAML 配置（agents/ 根目录，不含 builtin/ 子目录）。"""
        if not _CUSTOM_AGENTS_DIR.exists():
            logger.debug("自定义 Agent 目录不存在，跳过: %s", _CUSTOM_AGENTS_DIR)
            return
        # 只扫描根目录下的 yaml 文件，不递归
        for yaml_path in sorted(_CUSTOM_AGENTS_DIR.glob("*.yaml")):
            self._load_yaml_file(yaml_path)

    def _load_yaml_dir(self, directory: Path) -> None:
        """从指定目录加载所有 YAML 文件。"""
        for yaml_path in sorted(directory.glob("*.yaml")):
            self._load_yaml_file(yaml_path)

    def _load_yaml_file(self, yaml_path: Path) -> None:
        """解析单个 YAML 文件并注册 AgentDefinition。"""
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                logger.warning("YAML 文件格式无效（非 dict）: %s", yaml_path)
                return
            _valid_model_preferences = {"haiku", "sonnet", "opus"}
            raw_model_pref = data.get("model_preference")
            if raw_model_pref is None:
                model_preference = None
            elif str(raw_model_pref) in _valid_model_preferences:
                model_preference = str(raw_model_pref)
            else:
                logger.warning(
                    "Agent YAML '%s' 的 model_preference '%s' 非法，有效值为 %s，已重置为 None",
                    yaml_path,
                    raw_model_pref,
                    _valid_model_preferences,
                )
                model_preference = None
            agent_def = AgentDefinition(
                agent_id=str(data.get("agent_id", "")),
                name=str(data.get("name", "")),
                description=str(data.get("description", "")),
                system_prompt=str(data.get("system_prompt", "")),
                purpose=str(data.get("purpose", "default")),
                allowed_tools=list(data.get("allowed_tools", [])),
                max_tokens=int(data.get("max_tokens", 8000)),
                timeout_seconds=int(data.get("timeout_seconds", 300)),
                paradigm=str(data.get("paradigm", "react")),
                max_spawn_depth=int(data.get("max_spawn_depth", 0)),
                model_preference=model_preference,
            )
            if not agent_def.agent_id:
                logger.warning("YAML 缺少 agent_id 字段，跳过: %s", yaml_path)
                return
            self.register(agent_def)
        except Exception as exc:
            logger.warning("加载 Agent YAML 失败 (%s): %s", yaml_path, exc)
