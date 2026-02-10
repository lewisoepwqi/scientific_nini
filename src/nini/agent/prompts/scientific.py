"""科研领域系统 Prompt。"""

from nini.agent.prompts.builder import build_system_prompt


def get_system_prompt() -> str:
    """获取格式化后的系统 Prompt。"""
    return build_system_prompt()

