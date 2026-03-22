"""Agent 追加研究画像观察记录的工具。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.memory.profile_narrative import get_profile_narrative_manager
from nini.memory.research_profile import DEFAULT_RESEARCH_PROFILE_ID
from nini.tools.base import Tool, ToolResult


class UpdateProfileNotesTool(Tool):
    """向研究画像的'分析习惯与观察'段追加一条 Agent 观察记录。

    用于 Agent 在分析过程中自动记录用户的行为模式和稳定偏好，供后续会话参考。
    适合在发现用户一致性习惯时调用，例如：
    - 用户总是在统计检验前先检查数据正态性
    - 用户习惯使用对数变换处理右偏数据
    - 用户偏好在结论中报告效应量的实际意义
    """

    @property
    def name(self) -> str:
        return "update_profile_notes"

    @property
    def description(self) -> str:
        return (
            "向研究画像的'分析习惯与观察'段追加一条观察记录。"
            "记录用户在分析中展现的稳定偏好、习惯或特殊要求，这些记录会在后续会话中"
            "自动注入上下文，帮助 Agent 更好理解用户需求。"
            "请仅在发现用户明确的、可重复的行为模式时调用，不要记录单次偶发操作。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "要记录的观察内容，一句话描述，不超过 150 字。",
                },
            },
            "required": ["observation"],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def expose_to_llm(self) -> bool:
        return True

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        observation = str(kwargs.get("observation", "")).strip()
        if not observation:
            return ToolResult(success=False, message="observation 不能为空")

        # 超长截断
        if len(observation) > 200:
            observation = observation[:200] + "..."

        profile_id = (
            str(getattr(session, "research_profile_id", DEFAULT_RESEARCH_PROFILE_ID) or "").strip()
            or DEFAULT_RESEARCH_PROFILE_ID
        )

        manager = get_profile_narrative_manager()
        ok = manager.append_agent_observation(profile_id, observation)

        if ok:
            preview = observation[:60] + ("..." if len(observation) > 60 else "")
            return ToolResult(success=True, message=f"已记录到研究画像：{preview}")
        return ToolResult(success=False, message="写入画像叙述层失败，请检查文件权限")
