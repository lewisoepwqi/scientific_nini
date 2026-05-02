"""编排工作流引擎 —— 基于 YAML DAG 定义的顺序/并行 Agent 执行。

第一期只支持 depends_on（顺序依赖），不做条件分支。
DAG 拓扑排序后按层次并行执行：同层步骤并行，不同层严格顺序。

YAML 定义示例::

    name: full_analysis
    steps:
      - id: clean
        agent: data_cleaner
        task: "清洗数据集 {dataset_id}"
      - id: stat
        agent: statistician
        task: "对清洗结果做统计检验"
        depends_on: [clean]
      - id: viz
        agent: viz_designer
        task: "基于统计结果生成图表"
        depends_on: [stat]
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowStep:
    """工作流单步定义（不可变）。"""

    step_id: str
    agent_id: str
    task_template: str
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=str(data.get("id", "")),
            agent_id=str(data.get("agent", "")),
            task_template=str(data.get("task", "")),
            depends_on=tuple(data.get("depends_on", [])),
        )


@dataclass(frozen=True)
class WorkflowDef:
    """工作流定义（不可变）。"""

    name: str
    steps: tuple[WorkflowStep, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDef":
        steps = tuple(WorkflowStep.from_dict(s) for s in data.get("steps", []))
        return cls(name=str(data.get("name", "unnamed")), steps=steps)

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "WorkflowDef":
        import yaml

        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            raise ValueError("工作流 YAML 必须为 dict 格式")
        return cls.from_dict(data)


@dataclass
class WorkflowStepResult:
    """单步执行结果。"""

    step_id: str
    agent_id: str
    success: bool
    summary: str = ""
    error: str = ""
    stop_reason: str = ""
    execution_time_ms: int = 0


@dataclass
class WorkflowResult:
    """工作流整体执行结果。"""

    workflow_name: str
    success: bool
    step_results: list[WorkflowStepResult] = field(default_factory=list)
    error: str = ""

    @property
    def failed_steps(self) -> list[WorkflowStepResult]:
        return [r for r in self.step_results if not r.success]

    @property
    def succeeded_steps(self) -> list[WorkflowStepResult]:
        return [r for r in self.step_results if r.success]


def _topological_layers(steps: tuple[WorkflowStep, ...]) -> list[list[WorkflowStep]]:
    """将 DAG 步骤按拓扑排序分层，每层内步骤可并行执行。

    Raises:
        ValueError: 存在循环依赖或引用未知步骤时
    """
    step_map = {s.step_id: s for s in steps}
    in_degree: dict[str, int] = {s.step_id: 0 for s in steps}

    for step in steps:
        for dep in step.depends_on:
            if dep not in step_map:
                raise ValueError(f"步骤 '{step.step_id}' 引用了未知依赖 '{dep}'")
            in_degree[step.step_id] = in_degree.get(step.step_id, 0) + 1

    layers: list[list[WorkflowStep]] = []
    remaining = set(step_map.keys())

    while remaining:
        # 当前层：所有依赖已完成（in_degree == 0）的步骤
        current_layer = [step_map[sid] for sid in remaining if in_degree[sid] == 0]
        if not current_layer:
            raise ValueError(f"工作流存在循环依赖，剩余步骤: {remaining}")

        layers.append(current_layer)
        completed = {s.step_id for s in current_layer}
        remaining -= completed

        # 减少后续步骤的 in_degree
        for step in steps:
            if step.step_id in remaining:
                for dep in step.depends_on:
                    if dep in completed:
                        in_degree[step.step_id] -= 1

    return layers


class WorkflowExecutor:
    """工作流执行引擎。

    将 WorkflowDef 的 DAG 步骤按拓扑层次执行：同层并行，跨层顺序。
    """

    def __init__(self, spawner: Any) -> None:
        """初始化执行引擎。

        Args:
            spawner: SubAgentSpawner 实例，用于执行各步骤的 Agent
        """
        self._spawner = spawner

    async def execute(
        self,
        workflow: WorkflowDef,
        session: Any,
        *,
        context: str = "",
        parent_turn_id: str | None = None,
    ) -> WorkflowResult:
        """按 DAG 拓扑顺序执行工作流。

        Args:
            workflow: 工作流定义
            session: 父会话
            context: 背景信息（追加到各步骤任务描述末尾）
            parent_turn_id: 父轮次 ID

        Returns:
            WorkflowResult，包含所有步骤执行结果
        """
        try:
            layers = _topological_layers(workflow.steps)
        except ValueError as exc:
            return WorkflowResult(
                workflow_name=workflow.name,
                success=False,
                error=str(exc),
            )

        logger.info(
            "WorkflowExecutor: 开始执行工作流 '%s'，共 %d 层 %d 步",
            workflow.name,
            len(layers),
            len(workflow.steps),
        )

        all_results: list[WorkflowStepResult] = []
        completed_summaries: dict[str, str] = {}  # step_id → summary，供后续步骤引用

        for layer_idx, layer in enumerate(layers):
            logger.info(
                "WorkflowExecutor: 执行第 %d/%d 层，%d 个步骤并行: %s",
                layer_idx + 1,
                len(layers),
                len(layer),
                [s.step_id for s in layer],
            )

            async def _run_step(step: WorkflowStep) -> WorkflowStepResult:
                # 注入前置步骤摘要到任务描述
                task = step.task_template
                if step.depends_on:
                    dep_summaries = "\n".join(
                        f"[{dep}]: {completed_summaries.get(dep, '（无摘要）')}"
                        for dep in step.depends_on
                        if dep in completed_summaries
                    )
                    if dep_summaries:
                        task = f"{task}\n\n前置步骤结果：\n{dep_summaries}"
                if context:
                    task = f"{task}\n\n背景信息：{context}"

                import time

                start = time.monotonic()
                result = await self._spawner.spawn_with_retry(
                    step.agent_id,
                    task,
                    session,
                    parent_turn_id=parent_turn_id,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return WorkflowStepResult(
                    step_id=step.step_id,
                    agent_id=step.agent_id,
                    success=result.success,
                    summary=result.summary,
                    error=result.error,
                    stop_reason=result.stop_reason,
                    execution_time_ms=elapsed_ms,
                )

            # 同层并行
            layer_results = await asyncio.gather(
                *(_run_step(step) for step in layer),
                return_exceptions=False,
            )

            for step, step_result in zip(layer, layer_results):
                all_results.append(step_result)
                if step_result.success:
                    completed_summaries[step.step_id] = step_result.summary

            # 如有步骤失败，终止后续层执行
            failed = [r for r in layer_results if not r.success]
            if failed:
                failed_ids = [r.step_id for r in failed]
                logger.warning(
                    "WorkflowExecutor: 第 %d 层存在失败步骤 %s，终止后续执行",
                    layer_idx + 1,
                    failed_ids,
                )
                return WorkflowResult(
                    workflow_name=workflow.name,
                    success=False,
                    step_results=all_results,
                    error=f"步骤 {failed_ids} 执行失败",
                )

        logger.info("WorkflowExecutor: 工作流 '%s' 全部步骤执行成功", workflow.name)
        return WorkflowResult(
            workflow_name=workflow.name,
            success=True,
            step_results=all_results,
        )
