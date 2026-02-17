"""工作流模板相关技能 —— Agent 可通过工具调用保存、列出和应用工作流模板。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nini.agent.session import Session
from nini.tools.base import Skill, SkillResult
from nini.workflow.extractor import extract_workflow_from_session
from nini.workflow.store import (
    delete_template,
    get_template,
    list_templates,
    save_template,
)

logger = logging.getLogger(__name__)


class SaveWorkflowSkill(Skill):
    """从当前会话提取工具调用序列，保存为可复用的工作流模板。"""

    @property
    def name(self) -> str:
        return "save_workflow"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "将当前会话中的分析步骤保存为工作流模板，以便后续在新数据集上一键复用。"
            "需要提供模板名称。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "工作流模板名称，如「t检验+画图」",
                },
                "description": {
                    "type": "string",
                    "description": "模板描述（可选）",
                    "default": "",
                },
            },
            "required": ["name"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        name = kwargs.get("name", "")
        description = kwargs.get("description", "")

        if not name:
            return SkillResult(success=False, message="请提供工作流模板名称")

        template = extract_workflow_from_session(session, name=name, description=description)

        if not template.steps:
            return SkillResult(success=False, message="当前会话中没有可提取的分析步骤")

        await save_template(template)

        step_names = [s.tool_name for s in template.steps]
        return SkillResult(
            success=True,
            message=(
                f"工作流模板「{name}」已保存，包含 {len(template.steps)} 个步骤："
                f"{' → '.join(step_names)}"
            ),
            data=template.to_dict(),
        )


class ListWorkflowsSkill(Skill):
    """列出所有已保存的工作流模板。"""

    @property
    def name(self) -> str:
        return "list_workflows"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return "列出所有已保存的工作流模板，展示名称、步骤和创建时间。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        templates = await list_templates()

        if not templates:
            return SkillResult(success=True, message="暂无已保存的工作流模板。")

        lines = []
        for t in templates:
            steps = t.get("steps", [])
            step_names = [s.get("tool_name", "?") for s in steps]
            lines.append(f"- **{t['name']}**（{len(steps)} 步）：{' → '.join(step_names)}")

        return SkillResult(
            success=True,
            message=f"已保存 {len(templates)} 个工作流模板：\n\n" + "\n".join(lines),
            data=templates,
        )


class ApplyWorkflowSkill(Skill):
    """对当前数据集执行已保存的工作流模板。"""

    @property
    def name(self) -> str:
        return "apply_workflow"

    @property
    def category(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "对当前加载的数据集执行已保存的工作流模板，"
            "按照模板中记录的步骤依次执行，无需重新输入分析指令。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "description": "要执行的工作流模板 ID",
                },
            },
            "required": ["template_id"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        template_id = kwargs.get("template_id", "")
        if not template_id:
            return SkillResult(success=False, message="请提供工作流模板 ID")

        template = await get_template(template_id)
        if template is None:
            return SkillResult(success=False, message=f"未找到工作流模板: {template_id}")

        # 注意：实际执行在 API 层通过 workflow executor 完成，
        # 这里只返回模板信息让前端/WebSocket 层发起执行
        return SkillResult(
            success=True,
            message=(
                f"工作流模板「{template.name}」已加载，"
                f"包含 {len(template.steps)} 个步骤。请通过 API 执行。"
            ),
            data=template.to_dict(),
        )
