"""Agent 模块公共接口。"""

from nini.agent.hypothesis_context import Hypothesis, HypothesisContext
from nini.agent.registry import AgentDefinition, AgentRegistry
from nini.agent.spawner import SubAgentResult, SubAgentSpawner
from nini.agent.sub_session import SubSession

__all__ = [
    "AgentDefinition",
    "AgentRegistry",
    "Hypothesis",
    "HypothesisContext",
    "SubAgentResult",
    "SubAgentSpawner",
    "SubSession",
]
