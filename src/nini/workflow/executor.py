"""工作流执行引擎 —— 支持旧模板顺序执行与 YAML 声明式执行。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml

from nini.agent.runner import AgentEvent, EventType
from nini.agent.session import Session
from nini.utils.chart_payload import normalize_chart_payload
from nini.workflow.template import WorkflowStep, WorkflowTemplate
from nini.workflow.validator import safe_resolve_reference, validate_yaml_workflow

logger = logging.getLogger(__name__)

_FULL_REF_PATTERN = re.compile(r"^\$\{([^{}]+)\}$")
_INLINE_REF_PATTERN = re.compile(r"\$\{([^{}]+)\}")
_CONDITION_PATTERN = re.compile(r"^\s*(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")


def load_yaml_workflow(yaml_text: str) -> WorkflowTemplate:
    """从 YAML 字符串加载并校验工作流模板。"""
    data = yaml.safe_load(yaml_text) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML 顶层结构必须是对象（mapping）")

    validation = validate_yaml_workflow(data)
    if validation.errors:
        raise ValueError("YAML 工作流校验失败: " + "; ".join(validation.errors))

    return WorkflowTemplate.from_dict(data)


def load_yaml_workflow_file(path: str | Path) -> WorkflowTemplate:
    """从 YAML 文件加载并校验工作流模板。"""
    yaml_path = Path(path)
    content = yaml_path.read_text(encoding="utf-8")
    return load_yaml_workflow(content)


def _is_declarative_template(template: WorkflowTemplate) -> bool:
    return bool(template.steps) and all(bool(step.id.strip()) for step in template.steps)


def _build_parameter_context(
    parameters: dict[str, Any] | list[dict[str, Any]],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(parameters, dict):
        return {**parameters, **overrides}

    if isinstance(parameters, list):
        values: dict[str, Any] = {}
        for item in parameters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            if "default" in item:
                values[name] = item.get("default")
        values.update(overrides)
        return values

    return dict(overrides)


def _parse_literal(token: str) -> Any:
    value = token.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"none", "null"}:
        return None

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _resolve_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        full_match = _FULL_REF_PATTERN.match(value.strip())
        if full_match:
            return safe_resolve_reference(full_match.group(1), context)

        def _replace_ref(match: re.Match[str]) -> str:
            resolved = safe_resolve_reference(match.group(1), context)
            return "" if resolved is None else str(resolved)

        return _INLINE_REF_PATTERN.sub(_replace_ref, value)

    if isinstance(value, dict):
        return {k: _resolve_template_value(v, context) for k, v in value.items()}

    if isinstance(value, list):
        return [_resolve_template_value(item, context) for item in value]

    return value


def _resolve_condition_operand(token: str, context: dict[str, Any]) -> Any:
    token = token.strip()
    full_match = _FULL_REF_PATTERN.match(token)
    if full_match:
        return safe_resolve_reference(full_match.group(1), context)
    if "${" in token and "}" in token:
        return _resolve_template_value(token, context)
    return _parse_literal(token)


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    if not condition or not condition.strip():
        return True

    cond = condition.strip()
    full_match = _FULL_REF_PATTERN.match(cond)
    if full_match:
        return bool(safe_resolve_reference(full_match.group(1), context))

    match = _CONDITION_PATTERN.match(cond)
    if not match:
        raise ValueError(f"不支持的条件表达式：{condition}")

    left_token, operator, right_token = match.groups()
    left = _resolve_condition_operand(left_token, context)
    right = _resolve_condition_operand(right_token, context)

    try:
        if operator == "==":
            return left == right
        if operator == "!=":
            return left != right
        if operator == ">":
            return bool(left > right)
        if operator == ">=":
            return bool(left >= right)
        if operator == "<":
            return bool(left < right)
        if operator == "<=":
            return bool(left <= right)
    except TypeError:
        left_str = str(left)
        right_str = str(right)
        if operator == "==":
            return left_str == right_str
        if operator == "!=":
            return left_str != right_str
        if operator == ">":
            return left_str > right_str
        if operator == ">=":
            return left_str >= right_str
        if operator == "<":
            return left_str < right_str
        if operator == "<=":
            return left_str <= right_str

    return False


def _to_result_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "to_dict") and callable(result.to_dict):
        return result.to_dict()
    if result is None:
        return {"success": False, "message": "步骤未返回结果"}
    return {"success": True, "data": result, "message": "步骤执行完成"}


def _build_validation_payload(template: WorkflowTemplate) -> dict[str, Any]:
    return {
        "version": template.version,
        "kind": template.kind,
        "metadata": template.metadata
        or {
            "name": template.name,
            "id": template.id,
            "description": template.description,
        },
        "parameters": template.parameters,
        "steps": [
            {
                "id": step.id,
                "skill": step.executable_name,
                "description": step.description,
                "parameters": step.executable_arguments,
                "depends_on": step.depends_on,
                "condition": step.condition,
                "outputs": step.outputs,
            }
            for step in template.steps
        ],
    }


async def execute_workflow(
    template: WorkflowTemplate,
    session: Session,
    skill_registry: Any,
    *,
    parameter_overrides: dict[str, Any] | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """按模板步骤执行工具调用，产出事件流。"""
    overrides = parameter_overrides or {}
    total = len(template.steps)
    is_declarative = _is_declarative_template(template)

    if is_declarative:
        validation = validate_yaml_workflow(_build_validation_payload(template))
        if validation.errors:
            yield AgentEvent(
                type=EventType.TEXT,
                data="工作流模板校验失败：\n- " + "\n- ".join(validation.errors),
            )
            yield AgentEvent(type=EventType.DONE)
            return

    yield AgentEvent(
        type=EventType.TEXT,
        data=f"正在执行工作流「{template.name}」（共 {total} 个步骤）...\n\n",
    )

    context: dict[str, Any] = {
        "params": _build_parameter_context(template.parameters, overrides),
        "outputs": {},
        "session": {
            "id": session.id,
            "title": session.title,
            "dataset_names": list(session.datasets.keys()),
        },
    }

    if is_declarative:
        pending_steps: list[WorkflowStep] = list(template.steps)
        completed_ids: set[str] = set()
        run_index = 0

        while pending_steps:
            progressed = False
            for step in list(pending_steps):
                deps = [dep for dep in step.depends_on if dep]
                if any(dep not in completed_ids for dep in deps):
                    continue

                run_index += 1
                progressed = True
                pending_steps.remove(step)

                if step.condition:
                    try:
                        should_run = _evaluate_condition(step.condition, context)
                    except Exception as e:
                        yield AgentEvent(
                            type=EventType.TEXT,
                            data=f"\n步骤 {step.id} 条件表达式解析失败：{e}",
                        )
                        yield AgentEvent(type=EventType.DONE)
                        return

                    if not should_run:
                        completed_ids.add(step.id)
                        context["outputs"][step.id] = {"success": True, "skipped": True}
                        yield AgentEvent(
                            type=EventType.TOOL_RESULT,
                            data={
                                "result": {"skipped": True},
                                "status": "skipped",
                                "message": "条件不满足，步骤已跳过",
                            },
                            tool_call_id=f"wf-{template.id}-{run_index}",
                            tool_name=step.executable_name,
                        )
                        continue

                try:
                    resolved_args = _resolve_template_value(step.executable_arguments, context)
                except Exception as e:
                    yield AgentEvent(
                        type=EventType.TEXT,
                        data=f"\n步骤 {step.id} 参数引用解析失败：{e}",
                    )
                    yield AgentEvent(type=EventType.DONE)
                    return
                if not isinstance(resolved_args, dict):
                    yield AgentEvent(
                        type=EventType.TEXT,
                        data=f"\n步骤 {step.id} 参数解析失败：parameters 必须解析为对象。",
                    )
                    yield AgentEvent(type=EventType.DONE)
                    return

                yield AgentEvent(
                    type=EventType.TOOL_CALL,
                    data={"name": step.executable_name, "arguments": str(resolved_args)},
                    tool_call_id=f"wf-{template.id}-{run_index}",
                    tool_name=step.executable_name,
                )

                try:
                    raw_result = await skill_registry.execute(
                        step.executable_name,
                        session=session,
                        **resolved_args,
                    )
                    result = _to_result_dict(raw_result)
                except Exception as e:
                    logger.error("工作流步骤 %s 执行失败: %s", step.id, e)
                    result = {"success": False, "error": str(e)}

                context["outputs"][step.id] = result
                completed_ids.add(step.id)

                has_error = bool(result.get("error")) or result.get("success") is False
                status = "error" if has_error else "success"
                message = result.get("error") if has_error else result.get("message", "步骤执行完成")

                yield AgentEvent(
                    type=EventType.TOOL_RESULT,
                    data={"result": result, "status": status, "message": message},
                    tool_call_id=f"wf-{template.id}-{run_index}",
                    tool_name=step.executable_name,
                )
                for event in _build_artifact_events(result):
                    yield event

                if has_error:
                    yield AgentEvent(
                        type=EventType.TEXT,
                        data=f"\n步骤 {step.id} 执行失败，工作流已中止。",
                    )
                    yield AgentEvent(type=EventType.DONE)
                    return

            if not progressed:
                unresolved = ", ".join(step.id for step in pending_steps)
                yield AgentEvent(
                    type=EventType.TEXT,
                    data=f"\n工作流无法继续执行，存在未满足依赖的步骤：{unresolved}",
                )
                yield AgentEvent(type=EventType.DONE)
                return

    else:
        # 兼容旧模板：按序执行，参数采用“步骤参数 + 全局覆盖”策略
        for idx, step in enumerate(template.steps, 1):
            args = {**step.executable_arguments, **overrides}

            yield AgentEvent(
                type=EventType.TOOL_CALL,
                data={"name": step.executable_name, "arguments": str(args)},
                tool_call_id=f"wf-{template.id}-{idx}",
                tool_name=step.executable_name,
            )

            try:
                raw_result = await skill_registry.execute(
                    step.executable_name, session=session, **args
                )
                result = _to_result_dict(raw_result)
            except Exception as e:
                logger.error("工作流步骤 %d/%d 执行失败: %s", idx, total, e)
                result = {"success": False, "error": str(e)}

            has_error = bool(result.get("error")) or result.get("success") is False
            status = "error" if has_error else "success"
            message = result.get("error") if has_error else result.get("message", "步骤执行完成")

            yield AgentEvent(
                type=EventType.TOOL_RESULT,
                data={"result": result, "status": status, "message": message},
                tool_call_id=f"wf-{template.id}-{idx}",
                tool_name=step.executable_name,
            )
            for event in _build_artifact_events(result):
                yield event

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


def _build_artifact_events(result: dict[str, Any]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    if result.get("has_chart"):
        raw_chart_data = result.get("chart_data")
        normalized_chart_data = normalize_chart_payload(raw_chart_data)
        events.append(
            AgentEvent(
                type=EventType.CHART,
                data=normalized_chart_data if normalized_chart_data else raw_chart_data,
            )
        )
    if result.get("has_dataframe"):
        events.append(
            AgentEvent(
                type=EventType.DATA,
                data=result.get("dataframe_preview"),
            )
        )
    if result.get("artifacts"):
        for artifact in result["artifacts"]:
            events.append(
                AgentEvent(
                    type=EventType.ARTIFACT,
                    data=artifact,
                )
            )
    return events
