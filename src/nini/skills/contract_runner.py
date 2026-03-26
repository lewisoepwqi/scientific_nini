"""Skill 契约运行时——按 steps DAG 顺序执行步骤，支持 review_gate 阻塞和 retry_policy。

V1 限线性 DAG（无并行分支），review_gate 通过 asyncio.Event 等待用户确认。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from nini.models.event_schemas import SkillStepEventData
from nini.models.skill_contract import ContractResult, SkillContract, SkillStep, StepExecutionRecord

logger = logging.getLogger(__name__)

# review_gate 默认超时（秒）
_REVIEW_GATE_TIMEOUT_SECONDS = 300


# 事件回调类型：接收事件类型字符串和事件数据
EventCallback = Callable[[str, Any], Coroutine[Any, Any, None]]


class ContractRunner:
    """按 SkillContract 定义的 DAG 逐步执行 Skill 步骤。

    用法::

        runner = ContractRunner(contract, skill_name="experiment-design", callback=cb)
        result = await runner.run(session, inputs={})

    review_gate 确认：在外部异步任务中调用 ``runner.approve_review(step_id)``。
    """

    def __init__(
        self,
        contract: SkillContract,
        skill_name: str,
        callback: EventCallback,
        review_gate_timeout: float = _REVIEW_GATE_TIMEOUT_SECONDS,
    ) -> None:
        self._contract = contract
        self._skill_name = skill_name
        self._callback = callback
        self._review_gate_timeout = review_gate_timeout
        # step_id -> asyncio.Event，用于 review_gate 确认
        self._review_events: dict[str, asyncio.Event] = {}
        # step_id -> True=确认继续 False=拒绝/超时
        self._review_decisions: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def run(self, session: Any, inputs: dict[str, Any] | None = None) -> ContractResult:
        """按拓扑顺序执行契约中所有步骤，返回执行结果汇总。"""
        start_total = time.monotonic()
        inputs = inputs or {}
        ordered = self._topological_sort(self._contract.steps)
        step_records: list[StepExecutionRecord] = []
        # 记录已跳过步骤，其下游步骤也应跳过
        skipped_ids: set[str] = set()
        aborted = False
        abort_error: str | None = None

        for step in ordered:
            if aborted:
                # 整体 abort 后剩余步骤均记录为 skipped
                step_records.append(
                    StepExecutionRecord(step_id=step.id, status="skipped", error_message="契约已终止")
                )
                continue

            # 若前置步骤被 skip，则当前步骤也跳过
            if any(dep in skipped_ids for dep in step.depends_on):
                skipped_ids.add(step.id)
                await self._emit(
                    step, "skipped", output_summary="前置步骤已跳过，本步骤自动跳过"
                )
                step_records.append(StepExecutionRecord(step_id=step.id, status="skipped"))
                continue

            record = await self._execute_step(step, session, inputs, skipped_ids)
            step_records.append(record)

            if record.status == "skipped":
                skipped_ids.add(step.id)
            elif record.status == "failed" and step.retry_policy == "abort":
                aborted = True
                abort_error = record.error_message

        total_ms = int((time.monotonic() - start_total) * 1000)

        # 汇总状态
        if aborted:
            overall_status = "failed"
        elif any(r.status == "failed" for r in step_records):
            overall_status = "failed"
        elif any(r.status == "skipped" for r in step_records):
            overall_status = "partial"
        else:
            overall_status = "completed"

        return ContractResult(
            status=overall_status,
            step_records=step_records,
            total_ms=total_ms,
            error_message=abort_error,
            evidence_chain=self._snapshot_evidence_chain(session),
        )

    def approve_review(self, step_id: str) -> None:
        """外部确认通过 review_gate（继续执行）。"""
        self._review_decisions[step_id] = True
        event = self._review_events.get(step_id)
        if event:
            event.set()

    def reject_review(self, step_id: str) -> None:
        """外部拒绝 review_gate（按 retry_policy 处理）。"""
        self._review_decisions[step_id] = False
        event = self._review_events.get(step_id)
        if event:
            event.set()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _topological_sort(self, steps: list[SkillStep]) -> list[SkillStep]:
        """对步骤列表进行拓扑排序（Kahn 算法）。

        SkillContract 的 model_validator 已确保无循环依赖，此处直接执行。
        """
        id_to_step = {step.id: step for step in steps}
        # 入度统计
        in_degree: dict[str, int] = {step.id: 0 for step in steps}
        for step in steps:
            for dep in step.depends_on:
                in_degree[step.id] = in_degree.get(step.id, 0) + 1

        # 重新计算：in_degree[X] = X 的 depends_on 数量（即依赖项数量）
        in_degree = {step.id: len(step.depends_on) for step in steps}

        # 无前置依赖的步骤先入队
        queue: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
        # 保持声明顺序的稳定性
        queue.sort(key=lambda sid: [s.id for s in steps].index(sid))
        sorted_steps: list[SkillStep] = []

        # 构建依赖反向图（谁依赖了 X -> X 的后继列表）
        successors: dict[str, list[str]] = {step.id: [] for step in steps}
        for step in steps:
            for dep in step.depends_on:
                successors[dep].append(step.id)

        while queue:
            current_id = queue.pop(0)
            sorted_steps.append(id_to_step[current_id])
            for succ_id in successors[current_id]:
                in_degree[succ_id] -= 1
                if in_degree[succ_id] == 0:
                    queue.append(succ_id)

        return sorted_steps

    async def _execute_step(
        self,
        step: SkillStep,
        session: Any,
        inputs: dict[str, Any],
        skipped_ids: set[str],
    ) -> StepExecutionRecord:
        """执行单个步骤，处理 review_gate 和 retry_policy。"""
        # review_gate 检查：先阻塞等待用户确认
        if step.review_gate:
            confirmed = await self._wait_for_review(step)
            if not confirmed:
                # 用户拒绝或超时，按 retry_policy 处理（视为失败）
                await self._emit(step, "skipped", output_summary="review_gate 未通过，步骤跳过")
                return StepExecutionRecord(
                    step_id=step.id,
                    status="skipped",
                    error_message="review_gate 超时或用户拒绝",
                )

        # 执行步骤（发射 started 事件）
        await self._emit(step, "started")
        start_ms = time.monotonic()

        try:
            step_output = await self._run_step_logic(step, session, inputs)
            self._collect_step_evidence(step, session, step_output)
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            await self._emit(step, "completed", duration_ms=duration_ms)
            return StepExecutionRecord(
                step_id=step.id, status="completed", duration_ms=duration_ms
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            error_msg = str(exc)
            logger.warning("步骤 '%s' 执行失败: %s", step.id, error_msg)

            if step.retry_policy == "retry":
                # 重试一次
                logger.info("步骤 '%s' 重试中...", step.id)
                try:
                    step_output = await self._run_step_logic(step, session, inputs)
                    self._collect_step_evidence(step, session, step_output)
                    duration_ms = int((time.monotonic() - start_ms) * 1000)
                    await self._emit(step, "completed", duration_ms=duration_ms)
                    return StepExecutionRecord(
                        step_id=step.id, status="completed", duration_ms=duration_ms
                    )
                except Exception as retry_exc:
                    error_msg = str(retry_exc)
                    # 重试失败，降级为 skip
                    logger.warning("步骤 '%s' 重试仍失败，降级为 skip: %s", step.id, error_msg)

            if step.retry_policy == "abort":
                await self._emit(step, "failed", error_message=error_msg, duration_ms=duration_ms)
                return StepExecutionRecord(
                    step_id=step.id,
                    status="failed",
                    duration_ms=duration_ms,
                    error_message=error_msg,
                )
            else:
                # skip（包含 retry 降级后的 skip）
                await self._emit(
                    step,
                    "skipped",
                    error_message=error_msg,
                    output_summary="步骤失败，已跳过",
                    duration_ms=duration_ms,
                )
                return StepExecutionRecord(
                    step_id=step.id,
                    status="skipped",
                    duration_ms=duration_ms,
                    error_message=error_msg,
                )

    async def _run_step_logic(
        self, step: SkillStep, session: Any, inputs: dict[str, Any]
    ) -> Any:
        """执行步骤的实际逻辑（V1 占位实现，由子类或注入函数覆盖）。

        V1 中步骤的实际执行（调用 tool_hint 或 LLM 推理）由上层 AgentRunner
        通过继承或注入 step_executor 提供；此处仅作框架占位，不抛异常则视为成功。
        """
        # V1 占位：如有注入的执行器则调用，否则直接返回（步骤视为成功）
        executor = getattr(self, "_step_executor", None)
        if executor is not None:
            return await executor(step, session, inputs)
        return None

    def _snapshot_evidence_chain(self, session: Any) -> Any:
        """返回当前会话上的证据链快照。"""
        if not self._contract.evidence_required or session is None:
            return None
        collector = getattr(session, "evidence_collector", None)
        if collector is None:
            return None
        return collector.chain.model_copy(deep=True)

    def _collect_step_evidence(self, step: SkillStep, session: Any, step_output: Any) -> None:
        """在需要时根据步骤输出自动追加证据节点。"""
        if not self._contract.evidence_required or session is None:
            return

        collector = getattr(session, "evidence_collector", None)
        if collector is None:
            return

        payload = step_output if isinstance(step_output, dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        try:
            node_type = self._infer_evidence_node_type(step, payload, data, metadata)
            parent_ids = self._resolve_parent_ids(collector, payload, data, metadata)
            dataset_name = self._pick_string(payload, data, metadata, keys=("dataset_name", "dataset"))

            if node_type == "data":
                label = dataset_name or step.name
                collector.add_data_node(
                    label,
                    source_ref=self._pick_string(payload, data, metadata, keys=("source_ref", "path")),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            if dataset_name and not parent_ids and node_type in {"analysis", "chart", "conclusion"}:
                matching_data_nodes = collector.find_nodes(dataset_name, node_type="data")
                data_node = matching_data_nodes[-1] if matching_data_nodes else collector.add_data_node(
                    dataset_name
                )
                parent_ids = [data_node.id]

            if node_type == "chart":
                chart_label = self._pick_string(
                    payload,
                    data,
                    metadata,
                    keys=("chart_path", "artifact_path", "path", "chart_title"),
                ) or step.name
                collector.add_chart_node(
                    chart_label,
                    parent_ids=parent_ids or collector.latest_node_ids("analysis", "data"),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            if node_type == "conclusion":
                claim = self._pick_string(
                    payload,
                    data,
                    metadata,
                    keys=("claim", "conclusion", "summary", "message"),
                ) or step.description
                collector.add_conclusion_node(
                    claim,
                    parent_ids=parent_ids
                    or collector.latest_node_ids("analysis", "chart", "data", "result"),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            params = self._pick_mapping(payload, data, metadata, keys=("params", "arguments", "inputs"))
            result_ref = self._pick_string(
                payload,
                data,
                metadata,
                keys=("result_ref", "source_ref", "resource_id"),
            )
            collector.add_analysis_node(
                step.tool_hint or step.name,
                params=params,
                result_ref=result_ref,
                parent_ids=parent_ids or collector.latest_node_ids("analysis", "data", "chart"),
                label=self._pick_string(
                    payload,
                    data,
                    metadata,
                    keys=("label", "summary", "message"),
                )
                or step.name,
                metadata=self._build_evidence_metadata(step, payload, data, metadata),
            )
        except Exception as exc:
            logger.warning("步骤 '%s' 证据收集失败: %s", step.id, exc)

    def _infer_evidence_node_type(
        self,
        step: SkillStep,
        payload: dict[str, Any],
        data: dict[str, Any],
        metadata: dict[str, Any],
    ) -> str:
        explicit_type = self._pick_string(
            payload,
            data,
            metadata,
            keys=("evidence_node_type", "node_type", "resource_type"),
        )
        if explicit_type in {"data", "analysis", "result", "chart", "conclusion"}:
            return explicit_type

        tool_hint = (step.tool_hint or "").lower()
        if any(
            self._pick_string(payload, data, metadata, keys=(key,))
            for key in ("claim", "conclusion", "claim_summary")
        ):
            return "conclusion"
        if payload.get("has_chart") or any(
            token in tool_hint for token in ("chart", "plot", "visual", "graph")
        ):
            return "chart"
        if any(token in tool_hint for token in ("dataset", "load", "data_catalog")):
            return "data"
        return "analysis"

    def _resolve_parent_ids(
        self,
        collector: Any,
        payload: dict[str, Any],
        data: dict[str, Any],
        metadata: dict[str, Any],
    ) -> list[str]:
        raw_parent_ids = None
        for source in (payload, data, metadata):
            candidate = source.get("parent_ids")
            if isinstance(candidate, list):
                raw_parent_ids = candidate
                break
        if raw_parent_ids is None:
            return []
        return [
            str(parent_id)
            for parent_id in raw_parent_ids
            if isinstance(parent_id, str) and parent_id in {node.id for node in collector.chain.nodes}
        ]

    def _build_evidence_metadata(
        self,
        step: SkillStep,
        payload: dict[str, Any],
        data: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_metadata: dict[str, Any] = {
            "step_id": step.id,
            "step_name": step.name,
        }
        if step.tool_hint:
            evidence_metadata["tool_hint"] = step.tool_hint
        params = self._pick_mapping(payload, data, metadata, keys=("params", "arguments", "inputs"))
        if params:
            evidence_metadata["params"] = params
        for source in (metadata, data, payload):
            for key in ("resource_type", "result_ref", "chart_path", "dataset_name"):
                value = source.get(key)
                if value is not None:
                    evidence_metadata.setdefault(key, value)
        return evidence_metadata

    @staticmethod
    def _pick_string(
        *sources: dict[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        for source in sources:
            for key in keys:
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _pick_mapping(
        *sources: dict[str, Any],
        keys: tuple[str, ...],
    ) -> dict[str, Any]:
        for source in sources:
            for key in keys:
                value = source.get(key)
                if isinstance(value, dict):
                    return value
        return {}

    async def _wait_for_review(self, step: SkillStep) -> bool:
        """阻塞等待用户确认 review_gate，超时返回 False。"""
        event = asyncio.Event()
        self._review_events[step.id] = event

        # 发射 review_required 事件通知前端
        await self._emit(step, "review_required")

        try:
            await asyncio.wait_for(event.wait(), timeout=self._review_gate_timeout)
        except asyncio.TimeoutError:
            logger.warning("步骤 '%s' 的 review_gate 等待超时", step.id)
            return False
        finally:
            self._review_events.pop(step.id, None)

        return self._review_decisions.get(step.id, False)

    async def _emit(
        self,
        step: SkillStep,
        status: str,
        *,
        error_message: str | None = None,
        output_summary: str = "",
        duration_ms: int | None = None,
    ) -> None:
        """通过 callback 发射 skill_step 事件。"""
        event_data = SkillStepEventData(
            skill_name=self._skill_name,
            skill_version=self._contract.version,
            step_id=step.id,
            step_name=step.name,
            status=status,
            trust_level=step.trust_level.value,
            error_message=error_message,
            output_summary=output_summary,
            duration_ms=duration_ms,
        )
        try:
            await self._callback("skill_step", event_data)
        except Exception as cb_exc:
            logger.warning("skill_step 事件发射失败: %s", cb_exc)
