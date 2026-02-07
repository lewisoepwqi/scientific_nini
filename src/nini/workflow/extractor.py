"""从会话历史中提取工具调用序列，生成工作流模板。"""

from __future__ import annotations

import json
import logging
from typing import Any

from nini.agent.session import Session
from nini.workflow.template import WorkflowStep, WorkflowTemplate

logger = logging.getLogger(__name__)

# 非分析类工具，不纳入工作流模板
_EXCLUDED_TOOLS = {"save_workflow", "list_workflows", "apply_workflow"}


def extract_workflow_from_session(
    session: Session,
    *,
    name: str = "",
    description: str = "",
) -> WorkflowTemplate:
    """从会话消息历史中提取工具调用序列。

    遍历会话中所有 assistant 消息的 tool_calls，
    按执行顺序提取为 WorkflowStep 列表。
    """
    steps: list[WorkflowStep] = []

    for msg in session.messages:
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            if not tool_name or tool_name in _EXCLUDED_TOOLS:
                continue

            try:
                arguments = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                arguments = {}

            steps.append(
                WorkflowStep(
                    tool_name=tool_name,
                    arguments=arguments,
                    description=f"调用 {tool_name}",
                )
            )

    if not steps:
        logger.warning("会话 %s 中未找到可提取的工具调用", session.id)

    return WorkflowTemplate(
        name=name or f"工作流-{session.id[:6]}",
        description=description,
        steps=steps,
        source_session_id=session.id,
    )
