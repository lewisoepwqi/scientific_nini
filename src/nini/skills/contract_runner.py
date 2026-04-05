"""Skill 契约运行时。

按 SkillContract 的 DAG 定义执行步骤，支持分层并行、条件跳过、输入输出绑定、
review_gate 阻塞以及 retry_policy 失败策略。
"""

from __future__ import annotations

import ast
import asyncio
import logging
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from nini.models.event_schemas import SkillStepEventData, SkillSummaryEventData
from nini.models.skill_contract import ContractResult, SkillContract, SkillStep, StepExecutionRecord

logger = logging.getLogger(__name__)

# review_gate 默认超时（秒）
_REVIEW_GATE_TIMEOUT_SECONDS = 300
_SAFE_BOOL_NAMES = {"True", "False", "None"}
_SAFE_AST_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.Slice,
)


# 事件回调类型：接收事件类型字符串和事件数据
EventCallback = Callable[[str, Any], Coroutine[Any, Any, None]]
StepRecordStatus = Literal["completed", "failed", "skipped"]
StepEventStatus = Literal["started", "completed", "failed", "skipped", "review_required"]
ContractStatus = Literal["completed", "partial", "failed"]


class _ExpressionNamespace(dict[str, Any]):
    """供安全表达式读取的只读字典包装。"""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass(slots=True)
class _StepOutcome:
    """单步执行的内部结果。"""

    record: StepExecutionRecord
    step_output: Any = None
    should_abort: bool = False


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
        self._last_step_outputs: dict[str, Any] = {}
        self._last_output_aliases: dict[str, Any] = {}
        # step_id -> asyncio.Event，用于 review_gate 确认
        self._review_events: dict[str, asyncio.Event] = {}
        # step_id -> True=确认继续 False=拒绝/超时
        self._review_decisions: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def run(self, session: Any, inputs: dict[str, Any] | None = None) -> ContractResult:
        """按 DAG 分层执行契约中所有步骤，返回执行结果汇总。"""
        start_total = time.monotonic()
        inputs = inputs or {}
        layers = self._topological_sort(self._contract.steps)
        step_records: list[StepExecutionRecord] = []
        step_status: dict[str, StepRecordStatus] = {}
        step_outputs: dict[str, Any] = {}
        output_aliases: dict[str, Any] = {}
        aborted = False
        abort_error: str | None = None

        for layer_index, layer in enumerate(layers):
            if aborted:
                for step in layer:
                    step_records.append(
                        StepExecutionRecord(
                            step_id=step.id,
                            status="skipped",
                            duration_ms=None,
                            error_message="契约已终止",
                        )
                    )
                continue

            raw_outcomes = await asyncio.gather(
                *(
                    self._execute_step(
                        step,
                        session,
                        inputs,
                        step_status,
                        step_outputs,
                        output_aliases,
                        layer_index,
                    )
                    for step in layer
                ),
                return_exceptions=True,
            )

            for step, raw_outcome in zip(layer, raw_outcomes, strict=True):
                if isinstance(raw_outcome, BaseException):
                    logger.error(
                        "步骤 '%s' 出现未捕获异常",
                        step.id,
                        exc_info=(type(raw_outcome), raw_outcome, raw_outcome.__traceback__),
                    )
                    outcome = await self._build_failure_outcome(
                        step,
                        str(raw_outcome),
                        duration_ms=None,
                        layer=layer_index,
                    )
                else:
                    outcome = cast(_StepOutcome, raw_outcome)

                step_records.append(outcome.record)
                step_status[step.id] = outcome.record.status
                if outcome.record.status == "completed":
                    self._store_step_output(step, outcome.step_output, step_outputs, output_aliases)
                if outcome.should_abort and not aborted:
                    aborted = True
                    abort_error = outcome.record.error_message

        total_ms = int((time.monotonic() - start_total) * 1000)
        self._last_step_outputs = dict(step_outputs)
        self._last_output_aliases = dict(output_aliases)

        # 汇总状态
        if aborted:
            overall_status: ContractStatus = "failed"
        elif any(r.status == "failed" for r in step_records):
            overall_status = "failed"
        elif any(r.status == "skipped" for r in step_records):
            overall_status = "partial"
        else:
            overall_status = "completed"

        await self._emit_summary(step_records, total_ms, overall_status, step_outputs)

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

    def get_step_output(self, step_id: str) -> Any:
        """获取最近一次运行中指定步骤的输出。"""
        return self._last_step_outputs.get(step_id)

    def get_output_alias(self, name: str) -> Any:
        """获取最近一次运行中 output_key 对应的输出。"""
        return self._last_output_aliases.get(name)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _topological_sort(self, steps: list[SkillStep]) -> list[list[SkillStep]]:
        """对步骤列表进行分层拓扑排序（Kahn 算法）。

        SkillContract 的 model_validator 已确保无循环依赖，此处直接执行。
        """
        id_to_step = {step.id: step for step in steps}
        in_degree = {step.id: len(step.depends_on) for step in steps}
        declaration_order = {step.id: index for index, step in enumerate(steps)}

        queue: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
        queue.sort(key=lambda sid: declaration_order[sid])
        layered_steps: list[list[SkillStep]] = []

        successors: dict[str, list[str]] = {step.id: [] for step in steps}
        for step in steps:
            for dep in step.depends_on:
                successors[dep].append(step.id)

        while queue:
            current_layer_ids = list(queue)
            queue = []
            layered_steps.append([id_to_step[step_id] for step_id in current_layer_ids])

            next_queue: list[str] = []
            for current_id in current_layer_ids:
                for succ_id in successors[current_id]:
                    in_degree[succ_id] -= 1
                    if in_degree[succ_id] == 0:
                        next_queue.append(succ_id)

            next_queue.sort(key=lambda sid: declaration_order[sid])
            queue = next_queue

        return layered_steps

    async def _execute_step(
        self,
        step: SkillStep,
        session: Any,
        inputs: dict[str, Any],
        step_status: Mapping[str, StepRecordStatus],
        step_outputs: Mapping[str, Any],
        output_aliases: Mapping[str, Any],
        layer: int,
    ) -> _StepOutcome:
        """执行单个步骤，处理条件、review_gate 与 retry_policy。"""
        dependency_reason = self._dependency_skip_reason(step, step_status)
        if dependency_reason is not None:
            await self._emit(step, "skipped", output_summary=dependency_reason, layer=layer)
            return _StepOutcome(
                record=StepExecutionRecord(
                    step_id=step.id,
                    status="skipped",
                    duration_ms=None,
                    error_message=None,
                ),
            )

        try:
            should_run = await self._prepare_condition(step, inputs, step_outputs, output_aliases)
        except Exception as exc:
            if step.retry_policy == "retry":
                logger.info("步骤 '%s' 条件评估失败，重试中...", step.id)
                try:
                    should_run = await self._prepare_condition(
                        step, inputs, step_outputs, output_aliases
                    )
                except Exception as retry_exc:
                    logger.warning("步骤 '%s' 条件评估重试仍失败: %s", step.id, retry_exc)
                    return await self._build_failure_outcome(
                        step,
                        str(retry_exc),
                        duration_ms=None,
                        layer=layer,
                    )
            else:
                logger.warning("步骤 '%s' 条件评估失败: %s", step.id, exc)
                return await self._build_failure_outcome(
                    step,
                    str(exc),
                    duration_ms=None,
                    layer=layer,
                )

        if not should_run:
            await self._emit(
                step, "skipped", output_summary="condition 评估为 False，步骤跳过", layer=layer
            )
            return _StepOutcome(
                record=StepExecutionRecord(
                    step_id=step.id,
                    status="skipped",
                    duration_ms=None,
                    error_message=None,
                ),
            )

        if step.review_gate:
            confirmed = await self._wait_for_review(step, layer)
            if not confirmed:
                await self._emit(
                    step, "skipped", output_summary="review_gate 未通过，步骤跳过", layer=layer
                )
                return _StepOutcome(
                    record=StepExecutionRecord(
                        step_id=step.id,
                        status="skipped",
                        duration_ms=None,
                        error_message="review_gate 超时或用户拒绝",
                    ),
                )

        try:
            step_inputs = self._resolve_step_inputs(step, inputs, step_outputs, output_aliases)
        except Exception as exc:
            if step.retry_policy == "retry":
                logger.info("步骤 '%s' 输入绑定失败，重试中...", step.id)
                try:
                    step_inputs = self._resolve_step_inputs(
                        step, inputs, step_outputs, output_aliases
                    )
                except Exception as retry_exc:
                    logger.warning("步骤 '%s' 输入绑定重试仍失败: %s", step.id, retry_exc)
                    return await self._build_failure_outcome(
                        step,
                        str(retry_exc),
                        duration_ms=None,
                        layer=layer,
                    )
            else:
                logger.warning("步骤 '%s' 输入绑定失败: %s", step.id, exc)
                return await self._build_failure_outcome(
                    step,
                    str(exc),
                    duration_ms=None,
                    layer=layer,
                )

        await self._emit(step, "started", layer=layer)
        start_ms = time.monotonic()

        try:
            step_output = await self._run_step_logic(step, session, step_inputs)
            self._collect_step_evidence(step, session, step_output)
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            await self._emit(
                step,
                "completed",
                duration_ms=duration_ms,
                layer=layer,
                output_level=self._extract_output_level(step_output),
            )
            return _StepOutcome(
                record=StepExecutionRecord(
                    step_id=step.id,
                    status="completed",
                    duration_ms=duration_ms,
                    error_message=None,
                ),
                step_output=step_output,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_ms) * 1000)
            error_msg = str(exc)
            logger.warning("步骤 '%s' 执行失败: %s", step.id, error_msg)

            if step.retry_policy == "retry":
                logger.info("步骤 '%s' 重试中...", step.id)
                try:
                    step_output = await self._run_step_logic(step, session, step_inputs)
                    self._collect_step_evidence(step, session, step_output)
                    duration_ms = int((time.monotonic() - start_ms) * 1000)
                    await self._emit(
                        step,
                        "completed",
                        duration_ms=duration_ms,
                        layer=layer,
                        output_level=self._extract_output_level(step_output),
                    )
                    return _StepOutcome(
                        record=StepExecutionRecord(
                            step_id=step.id,
                            status="completed",
                            duration_ms=duration_ms,
                            error_message=None,
                        ),
                        step_output=step_output,
                    )
                except Exception as retry_exc:
                    error_msg = str(retry_exc)
                    logger.warning("步骤 '%s' 重试仍失败，降级为 skip: %s", step.id, error_msg)

            return await self._build_failure_outcome(
                step,
                error_msg,
                duration_ms=duration_ms,
                layer=layer,
            )

    def _dependency_skip_reason(
        self,
        step: SkillStep,
        step_status: Mapping[str, StepRecordStatus],
    ) -> str | None:
        """如果前置步骤未成功完成，返回跳过原因。"""
        blocked_deps = [
            f"{dep}={step_status.get(dep, 'unknown')}"
            for dep in step.depends_on
            if step_status.get(dep) != "completed"
        ]
        if not blocked_deps:
            return None
        return f"前置步骤未成功完成：{', '.join(blocked_deps)}"

    async def _prepare_condition(
        self,
        step: SkillStep,
        inputs: Mapping[str, Any],
        step_outputs: Mapping[str, Any],
        output_aliases: Mapping[str, Any],
    ) -> bool:
        """评估步骤条件；未配置条件时默认执行。"""
        if not step.condition:
            return True
        context = self._build_expression_context(inputs, step_outputs, output_aliases)
        return self._evaluate_condition(step.condition, context)

    def _resolve_step_inputs(
        self,
        step: SkillStep,
        inputs: Mapping[str, Any],
        step_outputs: Mapping[str, Any],
        output_aliases: Mapping[str, Any],
    ) -> dict[str, Any]:
        """解析步骤输入绑定，返回传给执行器的输入。"""
        resolved_inputs = dict(inputs)
        for param_name, reference in step.input_from.items():
            resolved_inputs[param_name] = self._resolve_reference(
                reference,
                inputs,
                step_outputs,
                output_aliases,
            )
        resolved_inputs["_contract_step_outputs"] = dict(step_outputs)
        resolved_inputs["_contract_output_aliases"] = dict(output_aliases)
        return resolved_inputs

    def _resolve_reference(
        self,
        reference: str,
        inputs: Mapping[str, Any],
        step_outputs: Mapping[str, Any],
        output_aliases: Mapping[str, Any],
    ) -> Any:
        """按 `a.b.c` 形式解析共享上下文引用。"""
        parts = [part for part in reference.split(".") if part]
        if not parts:
            raise ValueError("input_from 引用不能为空")

        root_key = parts[0]
        if root_key == "inputs":
            current: Any = inputs
        elif root_key in step_outputs:
            current = step_outputs[root_key]
        elif root_key in output_aliases:
            current = output_aliases[root_key]
        else:
            raise KeyError(f"找不到引用 '{reference}' 的根节点 '{root_key}'")

        for part in parts[1:]:
            if isinstance(current, Mapping):
                if part not in current:
                    raise KeyError(f"引用 '{reference}' 中缺少键 '{part}'")
                current = current[part]
                continue
            if isinstance(current, list):
                if not part.isdigit():
                    raise KeyError(f"引用 '{reference}' 中列表索引 '{part}' 非法")
                index = int(part)
                try:
                    current = current[index]
                except IndexError as exc:
                    raise KeyError(f"引用 '{reference}' 的索引 '{part}' 越界") from exc
                continue
            if hasattr(current, part):
                current = getattr(current, part)
                continue
            raise KeyError(f"引用 '{reference}' 无法解析段 '{part}'")
        return current

    def _store_step_output(
        self,
        step: SkillStep,
        step_output: Any,
        step_outputs: dict[str, Any],
        output_aliases: dict[str, Any],
    ) -> None:
        """将步骤输出写入共享上下文。"""
        step_outputs[step.id] = step_output
        if step.output_key:
            output_aliases[step.output_key] = step_output

    def _build_expression_context(
        self,
        inputs: Mapping[str, Any],
        step_outputs: Mapping[str, Any],
        output_aliases: Mapping[str, Any],
    ) -> dict[str, Any]:
        """构造条件表达式可访问的白名单上下文。"""
        context: dict[str, Any] = {"inputs": self._to_expression_value(dict(inputs))}
        for name, value in step_outputs.items():
            context[name] = self._to_expression_value(value)
        for name, value in output_aliases.items():
            context[name] = self._to_expression_value(value)
        return context

    def _evaluate_condition(self, expression: str, context: Mapping[str, Any]) -> bool:
        """安全评估条件表达式。"""
        parsed = ast.parse(expression, mode="eval")
        for node in ast.walk(parsed):
            if not isinstance(node, _SAFE_AST_NODES):
                raise ValueError(f"condition 包含不允许的语法：{type(node).__name__}")
            if isinstance(node, ast.Call):
                raise ValueError("condition 不允许函数调用")
            if (
                isinstance(node, ast.Name)
                and node.id not in context
                and node.id not in _SAFE_BOOL_NAMES
            ):
                raise ValueError(f"condition 引用了未声明变量 '{node.id}'")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("condition 不允许访问双下划线属性")
        return bool(
            eval(compile(parsed, "<skill-condition>", "eval"), {"__builtins__": {}}, dict(context))
        )

    @classmethod
    def _to_expression_value(cls, value: Any) -> Any:
        """将上下文值转换为安全表达式可访问的只读对象。"""
        if isinstance(value, Mapping):
            return _ExpressionNamespace(
                {str(key): cls._to_expression_value(item) for key, item in value.items()}
            )
        if isinstance(value, list):
            return [cls._to_expression_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._to_expression_value(item) for item in value)
        return value

    async def _build_failure_outcome(
        self,
        step: SkillStep,
        error_message: str,
        *,
        duration_ms: int | None,
        layer: int,
    ) -> _StepOutcome:
        """按 retry_policy 生成失败结果并发射事件。"""
        if step.retry_policy == "abort":
            await self._emit(
                step,
                "failed",
                error_message=error_message,
                duration_ms=duration_ms,
                layer=layer,
            )
            return _StepOutcome(
                record=StepExecutionRecord(
                    step_id=step.id,
                    status="failed",
                    duration_ms=duration_ms,
                    error_message=error_message,
                ),
                should_abort=True,
            )

        await self._emit(
            step,
            "skipped",
            error_message=error_message,
            output_summary="步骤失败，已跳过",
            duration_ms=duration_ms,
            layer=layer,
        )
        return _StepOutcome(
            record=StepExecutionRecord(
                step_id=step.id,
                status="skipped",
                duration_ms=duration_ms,
                error_message=error_message,
            ),
        )

    async def _run_step_logic(self, step: SkillStep, session: Any, inputs: dict[str, Any]) -> Any:
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

        payload: dict[str, Any] = step_output if isinstance(step_output, dict) else {}
        raw_data = payload.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        raw_metadata = payload.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}

        try:
            node_type = self._infer_evidence_node_type(step, payload, data, metadata)
            parent_ids = self._resolve_parent_ids(collector, payload, data, metadata)
            dataset_name = self._pick_string(
                payload, data, metadata, keys=("dataset_name", "dataset")
            )

            if node_type == "data":
                label = dataset_name or step.name
                collector.add_data_node(
                    label,
                    source_ref=self._pick_string(
                        payload, data, metadata, keys=("source_ref", "path")
                    ),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            if dataset_name and not parent_ids and node_type in {"analysis", "chart", "conclusion"}:
                matching_data_nodes = collector.find_nodes(dataset_name, node_type="data")
                data_node = (
                    matching_data_nodes[-1]
                    if matching_data_nodes
                    else collector.add_data_node(dataset_name)
                )
                parent_ids = [data_node.id]

            if node_type == "chart":
                chart_label = (
                    self._pick_string(
                        payload,
                        data,
                        metadata,
                        keys=("chart_path", "artifact_path", "path", "chart_title"),
                    )
                    or step.name
                )
                collector.add_chart_node(
                    chart_label,
                    parent_ids=parent_ids or collector.latest_node_ids("analysis", "data"),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            if node_type == "conclusion":
                claim = (
                    self._pick_string(
                        payload,
                        data,
                        metadata,
                        keys=("claim", "conclusion", "summary", "message"),
                    )
                    or step.description
                )
                collector.add_conclusion_node(
                    claim,
                    parent_ids=parent_ids
                    or collector.latest_node_ids("analysis", "chart", "data", "result"),
                    metadata=self._build_evidence_metadata(step, payload, data, metadata),
                )
                return

            params = self._pick_mapping(
                payload, data, metadata, keys=("params", "arguments", "inputs")
            )
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
            if isinstance(parent_id, str)
            and parent_id in {node.id for node in collector.chain.nodes}
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

    async def _wait_for_review(self, step: SkillStep, layer: int) -> bool:
        """阻塞等待用户确认 review_gate，超时返回 False。"""
        event = asyncio.Event()
        self._review_events[step.id] = event

        # 发射 review_required 事件通知前端
        await self._emit(step, "review_required", layer=layer)

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
        status: StepEventStatus,
        *,
        error_message: str | None = None,
        output_summary: str = "",
        duration_ms: int | None = None,
        layer: int | None = None,
        output_level: str | None = None,
    ) -> None:
        """通过 callback 发射 skill_step 事件。"""
        event_data = SkillStepEventData(
            skill_name=self._skill_name,
            skill_version=self._contract.version,
            step_id=step.id,
            step_name=step.name,
            status=status,
            layer=layer,
            trust_level=step.trust_level.value,
            output_level=output_level,
            input_summary="",
            error_message=error_message,
            output_summary=output_summary,
            duration_ms=duration_ms,
        )
        try:
            await self._callback("skill_step", event_data)
        except Exception as cb_exc:
            logger.warning("skill_step 事件发射失败: %s", cb_exc)

    async def _emit_summary(
        self,
        step_records: list[StepExecutionRecord],
        total_ms: int,
        overall_status: ContractStatus,
        step_outputs: Mapping[str, Any],
    ) -> None:
        """通过 callback 发射 skill_summary 事件。"""
        event_data = SkillSummaryEventData(
            skill_name=self._skill_name,
            total_steps=len(step_records),
            completed_steps=sum(1 for record in step_records if record.status == "completed"),
            skipped_steps=sum(1 for record in step_records if record.status == "skipped"),
            failed_steps=sum(1 for record in step_records if record.status == "failed"),
            total_duration_ms=total_ms,
            overall_status=overall_status,
            trust_ceiling=self._contract.trust_ceiling.value,
            output_level=self._collect_summary_output_level(step_outputs.values()),
        )
        try:
            await self._callback("skill_summary", event_data)
        except Exception as cb_exc:
            logger.warning("skill_summary 事件发射失败: %s", cb_exc)

    @staticmethod
    def _extract_output_level(step_output: Any) -> str | None:
        """尽量从步骤输出中提取 output_level。"""
        if not isinstance(step_output, Mapping):
            return None

        for source in (
            step_output,
            step_output.get("data") if isinstance(step_output.get("data"), Mapping) else None,
            (
                step_output.get("metadata")
                if isinstance(step_output.get("metadata"), Mapping)
                else None
            ),
        ):
            if not isinstance(source, Mapping):
                continue
            raw_level = source.get("output_level")
            if isinstance(raw_level, str) and raw_level.strip():
                return raw_level.strip().lower()
            raw_value = getattr(raw_level, "value", None)
            if isinstance(raw_value, str):
                return raw_value.strip().lower()
        return None

    def _collect_summary_output_level(self, step_outputs: Any) -> str | None:
        """汇总所有步骤输出中的最高 output_level。"""
        level_rank = {"o1": 1, "o2": 2, "o3": 3, "o4": 4}
        best_level: str | None = None
        best_rank = 0

        for step_output in step_outputs:
            level = self._extract_output_level(step_output)
            if level is None:
                continue
            rank = level_rank.get(level, 0)
            if rank > best_rank:
                best_rank = rank
                best_level = level

        return best_level
