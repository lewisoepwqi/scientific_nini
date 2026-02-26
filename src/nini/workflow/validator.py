"""YAML 声明式工作流安全校验。"""

from __future__ import annotations

import re
from typing import Any

import yaml

from nini.workflow.template import ValidationResult

ALLOWED_NAMESPACES = {"params", "outputs", "session"}
ALLOWED_TOOLS = {
    "run_code",
    "run_r_code",
    "create_chart",
    "load_dataset",
    "data_summary",
    "data_quality",
    "t_test",
    "anova",
    "correlation",
    "regression",
    "mann_whitney",
    "kruskal_wallis",
    "multiple_comparison_correction",
    "task_write",
    "generate_report",
    "export_report",
}
DANGEROUS_PATTERNS = {"os.system", "subprocess", "__import__", "eval", "exec"}
MAX_STEPS = 20

_REF_PATTERN = re.compile(r"\$\{([^{}]+)\}")
_IDENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _normalize_template_input(template: dict[str, Any] | str) -> tuple[dict[str, Any], list[str]]:
    if isinstance(template, dict):
        return template, []

    if not isinstance(template, str):
        return {}, ["模板必须是 dict 或 YAML 字符串"]

    try:
        data = yaml.safe_load(template) or {}
    except yaml.YAMLError as e:
        return {}, [f"YAML 解析失败: {e}"]

    if not isinstance(data, dict):
        return {}, ["YAML 顶层结构必须是对象（mapping）"]
    return data, []


def _validate_reference_expression(expr: str) -> str | None:
    normalized = expr.strip()
    if "." not in normalized:
        return f"非法引用格式：{expr}，必须包含命名空间 (params/outputs/session)"

    namespace, remain = normalized.split(".", 1)
    if namespace not in ALLOWED_NAMESPACES:
        return f"非法命名空间：{namespace}，仅允许 {ALLOWED_NAMESPACES}"

    parts = remain.split(".")
    if not parts or any(not p for p in parts):
        return f"非法引用路径：{expr}"

    for part in parts:
        if not _IDENT_PATTERN.match(part):
            return f"非法引用路径片段：{part}"

    return None


def safe_resolve_reference(expr: str, context: dict[str, Any]) -> Any:
    """安全解析模板变量引用。"""
    normalized = expr.strip()
    if normalized.startswith("${") and normalized.endswith("}"):
        normalized = normalized[2:-1].strip()

    ref_error = _validate_reference_expression(normalized)
    if ref_error:
        raise ValueError(ref_error)

    namespace, remain = normalized.split(".", 1)
    value: Any = context.get(namespace)

    for part in remain.split("."):
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"无法解析路径：{normalized}")
            value = value[part]
        else:
            raise ValueError(f"无法解析路径：{normalized}")
    return value


def detect_cycle(steps: list[dict[str, Any]]) -> bool:
    """检测步骤依赖是否有环（DAG 环检测）。"""
    graph: dict[str, list[str]] = {}
    for step in steps:
        sid = str(step.get("id", ""))
        if not sid:
            continue
        deps = step.get("depends_on", [])
        graph[sid] = [str(dep) for dep in deps] if isinstance(deps, list) else []

    visited: set[str] = set()
    rec_stack: set[str] = set()

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited and dfs(node):
            return True
    return False


def _scan_dangerous_patterns(value: Any, step_id: str, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        lower = value.lower()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in lower:
                errors.append(f"危险参数模式：{pattern} 在 {step_id}.{path}")
        for ref_expr in _REF_PATTERN.findall(value):
            ref_error = _validate_reference_expression(ref_expr)
            if ref_error:
                errors.append(f"{step_id}.{path}: {ref_error}")
        return

    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            _scan_dangerous_patterns(item, step_id, next_path, errors)
        return

    if isinstance(value, list):
        for idx, item in enumerate(value):
            _scan_dangerous_patterns(item, step_id, f"{path}[{idx}]", errors)


def validate_yaml_workflow(template_dict: dict[str, Any] | str) -> ValidationResult:
    """验证 YAML 工作流模板合法性。"""
    normalized, parse_errors = _normalize_template_input(template_dict)
    if parse_errors:
        return ValidationResult(errors=parse_errors, warnings=[])

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Schema 验证
    if normalized.get("kind") != "WorkflowTemplate":
        errors.append("非法模板：kind 必须为 'WorkflowTemplate'")

    # 2. 步骤数量检查
    steps = normalized.get("steps", [])
    if not isinstance(steps, list):
        errors.append("非法模板：steps 必须是列表")
        return ValidationResult(errors=errors, warnings=warnings)

    if len(steps) > MAX_STEPS:
        errors.append(f"步骤数量超限：最多 {MAX_STEPS} 步，当前 {len(steps)} 步")

    seen_ids: set[str] = set()
    step_ids: set[str] = set()

    # 3. 技能白名单检查 + 字段检查
    for idx, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            errors.append(f"步骤 {idx} 必须是对象")
            continue

        step_id = str(step.get("id", "")).strip()
        if not step_id:
            errors.append(f"步骤 {idx} 缺少 id")
            step_id = f"step_{idx}"
        elif step_id in seen_ids:
            errors.append(f"步骤 id 重复：{step_id}")
        seen_ids.add(step_id)
        step_ids.add(step_id)

        skill = str(step.get("skill", "")).strip()
        if skill not in ALLOWED_TOOLS:
            errors.append(f"非法技能：{skill}，仅允许 {ALLOWED_TOOLS}")

        raw_deps = step.get("depends_on", [])
        if raw_deps is None:
            raw_deps = []
        if not isinstance(raw_deps, list):
            errors.append(f"{step_id}.depends_on 必须是列表")

        params = step.get("parameters", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errors.append(f"{step_id}.parameters 必须是对象")
        else:
            _scan_dangerous_patterns(params, step_id, "parameters", errors)

        condition = step.get("condition")
        if isinstance(condition, str) and condition.strip():
            _scan_dangerous_patterns(condition, step_id, "condition", errors)

        outputs = step.get("outputs")
        if outputs is not None:
            _scan_dangerous_patterns(outputs, step_id, "outputs", errors)

    # 4. 依赖引用合法性
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id", "")).strip() or "unknown_step"
        raw_deps = step.get("depends_on", [])
        if not isinstance(raw_deps, list):
            continue
        for dep in raw_deps:
            dep_name = str(dep)
            if dep_name not in step_ids:
                errors.append(f"{step_id}.depends_on 引用了不存在的步骤：{dep_name}")

    # 5. 循环依赖检测
    if detect_cycle([s for s in steps if isinstance(s, dict)]):
        errors.append("循环依赖检测：步骤依赖存在环")

    return ValidationResult(errors=errors, warnings=warnings)
