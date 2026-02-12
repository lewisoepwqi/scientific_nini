"""沙箱安全策略：AST 静态分析与导入白名单。"""

from __future__ import annotations

import ast
from dataclasses import dataclass

ALLOWED_IMPORT_ROOTS: set[str] = {
    "math",
    "statistics",
    "json",
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "sklearn",
    "matplotlib",
    "plotly",
    "seaborn",
}

BANNED_CALLS: set[str] = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "type",
    "breakpoint",
}


@dataclass
class PolicyViolation:
    """策略违规信息。"""

    message: str
    lineno: int | None = None


class SandboxPolicyError(ValueError):
    """策略校验失败。"""


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def validate_code(code: str) -> None:
    """对用户代码做 AST 静态安全检查。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SandboxPolicyError(f"代码语法错误: {exc}") from exc

    violations: list[PolicyViolation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_module(alias.name)
                if root not in ALLOWED_IMPORT_ROOTS:
                    violations.append(
                        PolicyViolation(
                            message=f"不允许导入模块: {alias.name}",
                            lineno=getattr(node, "lineno", None),
                        )
                    )

        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                violations.append(
                    PolicyViolation(
                        message="不允许相对导入",
                        lineno=getattr(node, "lineno", None),
                    )
                )
            module = node.module or ""
            root = _root_module(module) if module else ""
            if not root or root not in ALLOWED_IMPORT_ROOTS:
                violations.append(
                    PolicyViolation(
                        message=f"不允许导入模块: {module or '<empty>'}",
                        lineno=getattr(node, "lineno", None),
                    )
                )

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in BANNED_CALLS:
                violations.append(
                    PolicyViolation(
                        message=f"不允许调用函数: {node.func.id}",
                        lineno=getattr(node, "lineno", None),
                    )
                )

    if violations:
        first = violations[0]
        where = f" (第 {first.lineno} 行)" if first.lineno else ""
        raise SandboxPolicyError(f"{first.message}{where}")
