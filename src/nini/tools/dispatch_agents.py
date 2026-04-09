"""dispatch_agents 工具 —— 将任务并行分发给多个 Specialist Agent 后拼接原始结果。

继承 tools/base.py:Tool，主 Agent 直接声明 agent_id，通过 SubAgentSpawner 并行执行，
各子 Agent 原始输出拼接后返回，主 Agent 自行综合。
该工具不暴露给子 Agent（防止递归派发），仅主 Agent 可调用。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import session_manager
from nini.agent.spawner import SubAgentResult
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class DispatchAgentsTool(Tool):
    """多 Agent 并行派发工具。

    主 Agent 直接声明 agent_id 和任务描述，工具并行执行后拼接各子 Agent 原始输出返回。
    """

    def __init__(
        self,
        agent_registry: Any = None,
        spawner: Any = None,
    ) -> None:
        self._agent_registry = agent_registry
        self._spawner = spawner

    @property
    def name(self) -> str:
        return "dispatch_agents"

    @property
    def description(self) -> str:
        return (
            "将任务并行分发给多个专业 Agent 执行，返回各 Agent 的原始输出供你综合。"
            "适合文献检索、批量阅读、并行调研等可并行场景。"
            "你必须直接声明 agent_id，可用 Agent 见 system prompt 中的列表。"
            "最小示例：agents=[{\"agent_id\": \"literature_search\", \"task\": \"检索XXX相关文献\"}]"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "agents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "string",
                                "description": "目标 Agent 的 ID，必须是可用列表中的合法值",
                            },
                            "task": {
                                "type": "string",
                                "description": "分配给该 Agent 的具体任务描述",
                            },
                        },
                        "required": ["agent_id", "task"],
                        "additionalProperties": False,
                    },
                    "description": "要并行执行的 Agent 任务列表",
                },
            },
            "required": ["agents"],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def expose_to_llm(self) -> bool:
        # 通过 Orchestrator 路径暴露，不走普通工具白名单
        return False

    async def execute(
        self,
        session: Any,
        *,
        agents: list[dict[str, Any]] | None = None,
        turn_id: str | None = None,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del kwargs  # 吸收框架可能传入的额外参数
        """执行多 Agent 并行派发。

        Args:
            session: 当前会话
            agents: Agent 任务列表，每项含 agent_id 和 task
            turn_id: 父会话 turn ID

        Returns:
            ToolResult，message 字段包含各子 Agent 原始输出拼接文本
        """
        if self._spawner is None:
            return ToolResult(
                success=False,
                message="dispatch_agents 未正确初始化，spawner 未注入。",
                metadata={"error_code": "DISPATCH_AGENTS_NOT_INITIALIZED"},
            )

        agents_list: list[dict[str, Any]] = agents or []
        dispatch_run_id = self._build_dispatch_run_id(turn_id=turn_id, tool_call_id=tool_call_id)

        # 空列表快速返回
        if not agents_list:
            return ToolResult(success=True, message="", metadata={"agent_count": 0})

        # 校验所有 agent_id 合法性
        invalid_ids = self._validate_agent_ids(agents_list)
        if invalid_ids:
            available = self._list_available_agent_ids()
            return ToolResult(
                success=False,
                message=(
                    f"以下 agent_id 不存在：{', '.join(invalid_ids)}。\n"
                    f"可用 agent_id：{', '.join(available)}"
                ),
                metadata={
                    "error_code": "INVALID_AGENT_IDS",
                    "invalid_ids": invalid_ids,
                    "available_ids": available,
                },
            )

        # 构造 (agent_id, task) 对
        task_pairs = [(item["agent_id"], item["task"]) for item in agents_list]

        # 推送 dispatch 开始事件
        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="started",
            payload={"agent_count": len(task_pairs)},
        )

        # 并行执行
        sub_results: list[SubAgentResult] = await self._spawner.spawn_batch(
            task_pairs,
            session,
            parent_turn_id=turn_id,
        )

        # 拼接原始输出
        message = self._build_result_message(sub_results, agents_list)

        # 统计
        success_count = sum(1 for r in sub_results if r.success)
        failure_count = sum(1 for r in sub_results if not r.success and not getattr(r, "stopped", False))
        stopped_count = sum(1 for r in sub_results if getattr(r, "stopped", False))
        dispatch_success = success_count > 0 or (failure_count == 0 and stopped_count == 0)

        # 记录运行事件
        self._record_dispatch_run_events(
            session=session,
            dispatch_run_id=dispatch_run_id,
            turn_id=turn_id,
            sub_results=sub_results,
            agents_list=agents_list,
        )

        await self._push_dispatch_workflow_event(
            session=session,
            turn_id=turn_id,
            dispatch_run_id=dispatch_run_id,
            phase="completed",
            payload={
                "agent_count": len(task_pairs),
                "success_count": success_count,
                "failure_count": failure_count,
                "stopped_count": stopped_count,
            },
        )

        return ToolResult(
            success=dispatch_success,
            message=message,
            metadata={
                "agent_count": len(task_pairs),
                "success_count": success_count,
                "failure_count": failure_count,
                "stopped_count": stopped_count,
                "dispatch_run_id": dispatch_run_id,
            },
        )

    def _validate_agent_ids(self, agents_list: list[dict[str, Any]]) -> list[str]:
        """返回不存在于 AgentRegistry 的非法 agent_id 列表。"""
        if self._agent_registry is None:
            return []
        available = {a.agent_id for a in (self._agent_registry.list_agents() or [])}
        if not available:
            return []
        return [
            item["agent_id"]
            for item in agents_list
            if item.get("agent_id") not in available
        ]

    def _list_available_agent_ids(self) -> list[str]:
        """返回当前已注册的所有 agent_id 列表。"""
        if self._agent_registry is None:
            return []
        agents = self._agent_registry.list_agents() or []
        return [a.agent_id for a in agents]

    def _build_result_message(
        self,
        sub_results: list[SubAgentResult],
        agents_list: list[dict[str, Any]],
    ) -> str:
        """将各子 Agent 结果拼接为带标签的文本，供主 Agent 综合。"""
        if not sub_results:
            return ""

        n = len(sub_results)
        sections: list[str] = [f"以下是 {n} 个子 Agent 的执行结果：\n"]

        for result, agent_spec in zip(sub_results, agents_list):
            agent_id = result.agent_id or agent_spec.get("agent_id", "")
            task = agent_spec.get("task", getattr(result, "task", ""))
            header = f"[{agent_id}] {task}"

            if result.success:
                body = (result.summary or "（无输出）").strip()
            else:
                error = (getattr(result, "error", "") or result.summary or "未知错误").strip()
                body = f"执行失败: {error}"

            sections.append(f"{header}\n{body}")

        return "\n\n".join(sections)

    def _build_dispatch_run_id(
        self,
        *,
        turn_id: str | None,
        tool_call_id: str | None,
    ) -> str:
        """构造派发运行 ID。"""
        normalized_tool_call = str(tool_call_id or "").strip()
        if normalized_tool_call:
            return f"dispatch:{normalized_tool_call}"
        normalized_turn = str(turn_id or "").strip() or "unknown"
        return f"dispatch:{normalized_turn}"

    async def _push_dispatch_workflow_event(
        self,
        *,
        session: Any,
        turn_id: str | None,
        dispatch_run_id: str,
        phase: str,
        payload: dict[str, Any],
    ) -> None:
        """通过会话事件回调推送 dispatch 工作流事件。"""
        callback = getattr(session, "event_callback", None)
        if callback is None:
            return
        try:
            from nini.agent.events import AgentEvent, EventType

            event = AgentEvent(
                type=EventType.WORKFLOW_STATUS,
                data={"scope": "dispatch_agents", "phase": phase, **payload},
                turn_id=turn_id,
                metadata={
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "agent_id": "dispatch_agents",
                    "agent_name": "dispatch_agents",
                    "attempt": 1,
                    "phase": phase,
                    "turn_id": turn_id,
                },
            )
            if callable(callback):
                maybe_coro = callback(event)
                if hasattr(maybe_coro, "__await__"):
                    await maybe_coro
        except Exception as exc:
            logger.warning("推送 dispatch 工作流事件失败: %s", exc)

    def _record_dispatch_run_events(
        self,
        *,
        session: Any,
        dispatch_run_id: str,
        turn_id: str | None,
        sub_results: list[SubAgentResult],
        agents_list: list[dict[str, Any]],
    ) -> None:
        """将 dispatch 结果写入父会话运行事件文件，便于事后排障。"""
        session_id = str(getattr(session, "id", "") or "").strip()
        if not session_id:
            return

        normalized_turn_id = str(turn_id or "").strip() or None
        parent_run_id = f"root:{normalized_turn_id}" if normalized_turn_id else None

        for result in sub_results:
            run_id = str(getattr(result, "run_id", "") or "").strip()
            if not run_id:
                continue
            session_manager.append_agent_run_event(
                session_id,
                {
                    "type": "subagent_result",
                    "data": {
                        "agent_id": result.agent_id,
                        "task": getattr(result, "task", ""),
                        "success": result.success,
                        "summary": result.summary,
                        "error": getattr(result, "error", ""),
                        "run_id": run_id,
                    },
                    "turn_id": normalized_turn_id,
                    "metadata": {
                        "run_scope": "subagent",
                        "run_id": run_id,
                        "parent_run_id": dispatch_run_id,
                        "agent_id": result.agent_id,
                        "attempt": 1,
                        "turn_id": normalized_turn_id,
                    },
                },
            )

        success_count = sum(1 for r in sub_results if r.success)
        failure_count = len(sub_results) - success_count
        session_manager.append_agent_run_event(
            session_id,
            {
                "type": "dispatch_agents_result",
                "data": {
                    "agent_count": len(sub_results),
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "agents": [item.get("agent_id") for item in agents_list],
                },
                "turn_id": normalized_turn_id,
                "metadata": {
                    "run_scope": "dispatch",
                    "run_id": dispatch_run_id,
                    "parent_run_id": parent_run_id,
                    "agent_id": "dispatch_agents",
                    "attempt": 1,
                    "phase": "completed",
                    "turn_id": normalized_turn_id,
                },
            },
        )
