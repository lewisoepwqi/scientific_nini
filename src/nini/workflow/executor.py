"""工作流模板执行引擎 —— 按序调用 SkillRegistry 执行工具，无需 LLM。"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from nini.agent.runner import AgentEvent, EventType
from nini.agent.session import Session
from nini.utils.chart_payload import normalize_chart_payload
from nini.workflow.template import WorkflowTemplate

logger = logging.getLogger(__name__)


async def execute_workflow(
    template: WorkflowTemplate,
    session: Session,
    skill_registry: Any,
    *,
    parameter_overrides: dict[str, Any] | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """按模板步骤依次执行工具调用，产出事件流。

    与 AgentRunner 类似的事件流格式，前端可直接复用相同的消息处理逻辑。
    """
    overrides = parameter_overrides or {}
    total = len(template.steps)

    yield AgentEvent(
        type=EventType.TEXT,
        data=f"正在执行工作流「{template.name}」（共 {total} 个步骤）...\n\n",
    )

    for idx, step in enumerate(template.steps, 1):
        # 合并参数覆盖
        args = {**step.arguments, **overrides}

        yield AgentEvent(
            type=EventType.TOOL_CALL,
            data={"name": step.tool_name, "arguments": str(args)},
            tool_call_id=f"wf-{template.id}-{idx}",
            tool_name=step.tool_name,
        )

        # 执行工具
        try:
            result = await skill_registry.execute(step.tool_name, session=session, **args)
        except Exception as e:
            logger.error("工作流步骤 %d/%d 执行失败: %s", idx, total, e)
            result = {"success": False, "error": str(e)}

        # 推送结果
        has_error = isinstance(result, dict) and result.get("error")
        status = "error" if has_error else "success"

        yield AgentEvent(
            type=EventType.TOOL_RESULT,
            data={
                "result": result,
                "status": status,
                "message": (
                    result.get("error") if has_error else result.get("message", "步骤执行完成")
                ),
            },
            tool_call_id=f"wf-{template.id}-{idx}",
            tool_name=step.tool_name,
        )

        # 推送产物事件
        if isinstance(result, dict):
            if result.get("has_chart"):
                raw_chart_data = result.get("chart_data")
                normalized_chart_data = normalize_chart_payload(raw_chart_data)
                yield AgentEvent(
                    type=EventType.CHART,
                    data=normalized_chart_data if normalized_chart_data else raw_chart_data,
                )
            if result.get("has_dataframe"):
                yield AgentEvent(
                    type=EventType.DATA,
                    data=result.get("dataframe_preview"),
                )
            if result.get("artifacts"):
                for artifact in result["artifacts"]:
                    yield AgentEvent(
                        type=EventType.ARTIFACT,
                        data=artifact,
                    )

        if has_error:
            yield AgentEvent(
                type=EventType.TEXT,
                data=f"\n步骤 {idx}/{total} 执行失败，工作流已中止。",
            )
            yield AgentEvent(type=EventType.DONE)
            return

    yield AgentEvent(
        type=EventType.TEXT,
        data=f"\n工作流「{template.name}」全部 {total} 个步骤执行完成。",
    )
    yield AgentEvent(type=EventType.DONE)
