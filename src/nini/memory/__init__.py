"""记忆模块导出。"""

from nini.memory.manager import MemoryManager, get_memory_manager, set_memory_manager
from nini.memory.research_profile import (
    DEFAULT_RESEARCH_PROFILE_ID,
    ResearchProfile,
    ResearchProfileManager,
    get_research_profile_manager,
    get_research_profile_prompt,
)
from nini.memory.scientific_provider import ScientificMemoryProvider

__all__ = [
    "DEFAULT_RESEARCH_PROFILE_ID",
    "ResearchProfile",
    "ResearchProfileManager",
    "get_research_profile_manager",
    "get_research_profile_prompt",
    "MemoryManager",
    "ScientificMemoryProvider",
    "get_memory_manager",
    "set_memory_manager",
]
