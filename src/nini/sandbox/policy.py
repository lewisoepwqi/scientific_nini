"""沙箱安全策略：AST 静态分析与导入分级控制。"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Iterable

# 分层白名单：从最安全到受限
# Tier 1: 纯计算/数据处理（完全安全）
_TIER1_SAFE_MODULES = {
    "math",  # 数学函数
    "statistics",  # 统计函数
    "random",  # 随机数生成
    "decimal",  # 精确小数运算
    "fractions",  # 分数运算
    "cmath",  # 复数数学
}

# Tier 2: 标准库工具（安全）
_TIER2_STDLIB_UTILS = {
    "datetime",  # 日期时间处理（★ 数据分析必备）
    "time",  # 时间相关函数
    "calendar",  # 日历操作
    "collections",  # 高级数据结构（deque, Counter, defaultdict 等）
    "itertools",  # 迭代器工具
    "functools",  # 函数式编程工具
    "operator",  # 操作符函数
    "heapq",  # 堆队列
    "bisect",  # 二分查找
    "array",  # 数组
    "copy",  # 深浅拷贝
    "json",  # JSON 处理
    "csv",  # CSV 文件处理
    "re",  # 正则表达式
    "string",  # 字符串常量和工具
    "textwrap",  # 文本包装
    "unicodedata",  # Unicode 数据库
    "warnings",  # 警告过滤器（纯工具，无副作用）
}

# Tier 3: 科学计算栈（自动允许）
_TIER3_SCIENTIFIC = {
    "pandas",  # 数据框架
    "numpy",  # 数值计算
    "scipy",  # 科学计算
    "statsmodels",  # 统计模型
    "sklearn",  # 机器学习（scikit-learn）
    "matplotlib",  # 绘图
    "plotly",  # 交互式绘图
    "seaborn",  # 统计可视化
}

# Tier 4: 低风险扩展包（需用户审批）
REVIEWABLE_IMPORT_ROOTS: set[str] = {
    "plotnine",  # 语法糖绘图层，偏可视化
    "sympy",  # 符号计算，纯内存计算为主
}

# Tier 5: 高风险模块（始终硬拒绝）
HARD_DENY_IMPORT_ROOTS: set[str] = {
    "asyncio",
    "builtins",
    "ctypes",
    "fcntl",
    "http",
    "httpx",
    "importlib",
    "inspect",
    "io",
    "multiprocessing",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shlex",
    "shutil",
    "signal",
    "socket",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "urllib",
}

# 合并自动允许白名单
ALLOWED_IMPORT_ROOTS: set[str] = _TIER1_SAFE_MODULES | _TIER2_STDLIB_UTILS | _TIER3_SCIENTIFIC

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
    "breakpoint",
}


@dataclass
class PolicyViolation:
    """策略违规信息。"""

    message: str
    lineno: int | None = None
    module: str | None = None
    root: str | None = None
    risk_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"message": self.message}
        if self.lineno is not None:
            payload["lineno"] = self.lineno
        if self.module:
            payload["module"] = self.module
        if self.root:
            payload["root"] = self.root
        if self.risk_level:
            payload["risk_level"] = self.risk_level
        return payload


class SandboxPolicyError(ValueError):
    """策略校验失败。"""


class SandboxReviewRequired(Exception):
    """导入命中低风险扩展包，需要用户审批。"""

    def __init__(
        self,
        packages: Iterable[str],
        *,
        violations: Iterable[PolicyViolation] | None = None,
    ) -> None:
        normalized_packages = sorted(
            {str(pkg or "").strip() for pkg in packages if str(pkg or "").strip()}
        )
        self.packages = normalized_packages
        self.violations = list(violations or [])
        package_text = ", ".join(self.packages) if self.packages else "<unknown>"
        super().__init__(f"导入扩展包需要用户审批: {package_text}")

    def to_payload(self) -> dict[str, Any]:
        violations = self.violations or [
            PolicyViolation(
                message=f"导入扩展包 '{pkg}' 需要用户审批",
                module=pkg,
                root=pkg,
                risk_level="reviewable",
            )
            for pkg in self.packages
        ]
        return {
            "packages": list(self.packages),
            "violations": [item.to_dict() for item in violations],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SandboxReviewRequired":
        raw_violations = payload.get("violations")
        violations: list[PolicyViolation] = []
        if isinstance(raw_violations, list):
            for item in raw_violations:
                if not isinstance(item, dict):
                    continue
                violations.append(
                    PolicyViolation(
                        message=str(item.get("message") or "导入扩展包需要用户审批"),
                        lineno=item.get("lineno") if isinstance(item.get("lineno"), int) else None,
                        module=str(item.get("module") or "").strip() or None,
                        root=str(item.get("root") or "").strip() or None,
                        risk_level=str(item.get("risk_level") or "").strip() or None,
                    )
                )
        return cls(payload.get("packages", []), violations=violations)


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def normalize_reviewable_import_roots(raw: Iterable[str] | None) -> set[str]:
    """规范化额外允许的 reviewable 根模块。"""
    normalized: set[str] = set()
    if raw is None:
        return normalized
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        root = _root_module(text)
        if root in REVIEWABLE_IMPORT_ROOTS:
            normalized.add(root)
    return normalized


def get_allowed_import_roots(extra_allowed_imports: Iterable[str] | None = None) -> set[str]:
    """返回本次执行允许导入的根模块集合。"""
    return ALLOWED_IMPORT_ROOTS | normalize_reviewable_import_roots(extra_allowed_imports)


def _reviewable_violation(module_name: str, *, lineno: int | None = None) -> PolicyViolation:
    root = _root_module(module_name)
    return PolicyViolation(
        message=f"导入扩展包 '{module_name}' 需要用户审批",
        lineno=lineno,
        module=module_name,
        root=root,
        risk_level="reviewable",
    )


def validate_import(
    root: str,
    module_name: str,
    *,
    lineno: int | None = None,
    extra_allowed_imports: Iterable[str] | None = None,
) -> None:
    """校验单个导入请求，必要时抛出审批或策略异常。"""
    allowed_roots = get_allowed_import_roots(extra_allowed_imports)
    if root in allowed_roots:
        return
    if root in REVIEWABLE_IMPORT_ROOTS:
        raise SandboxReviewRequired(
            [root], violations=[_reviewable_violation(module_name, lineno=lineno)]
        )
    if root in HARD_DENY_IMPORT_ROOTS:
        raise SandboxPolicyError(f"不允许导入模块: {module_name}（高风险模块）")
    raise SandboxPolicyError(f"不允许导入模块: {module_name}")


def validate_code(code: str, *, extra_allowed_imports: Iterable[str] | None = None) -> None:
    """对用户代码做 AST 静态安全检查。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SandboxPolicyError(f"代码语法错误: {exc}") from exc

    violations: list[PolicyViolation] = []
    reviewable_violations: dict[str, PolicyViolation] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                root = _root_module(module_name)
                try:
                    validate_import(
                        root,
                        module_name,
                        lineno=getattr(node, "lineno", None),
                        extra_allowed_imports=extra_allowed_imports,
                    )
                except SandboxReviewRequired as exc:
                    for violation in exc.violations:
                        reviewable_violations[violation.root or _root_module(module_name)] = (
                            violation
                        )
                except SandboxPolicyError as exc:
                    violations.append(
                        PolicyViolation(
                            message=str(exc),
                            lineno=getattr(node, "lineno", None),
                            module=module_name,
                            root=root,
                            risk_level="hard_deny" if root in HARD_DENY_IMPORT_ROOTS else "deny",
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
                continue

            module = node.module or ""
            root = _root_module(module) if module else ""
            if not root:
                violations.append(
                    PolicyViolation(
                        message=f"不允许导入模块: {module or '<empty>'}",
                        lineno=getattr(node, "lineno", None),
                        module=module or "<empty>",
                        risk_level="deny",
                    )
                )
                continue
            try:
                validate_import(
                    root,
                    module,
                    lineno=getattr(node, "lineno", None),
                    extra_allowed_imports=extra_allowed_imports,
                )
            except SandboxReviewRequired as exc:
                for violation in exc.violations:
                    reviewable_violations[violation.root or root] = violation
            except SandboxPolicyError as exc:
                violations.append(
                    PolicyViolation(
                        message=str(exc),
                        lineno=getattr(node, "lineno", None),
                        module=module,
                        root=root,
                        risk_level="hard_deny" if root in HARD_DENY_IMPORT_ROOTS else "deny",
                    )
                )

        # 禁止访问危险的双下划线属性（防止沙箱逃逸）
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                _ALLOWED_DUNDERS = {"__name__", "__doc__", "__len__", "__class__"}
                if node.attr not in _ALLOWED_DUNDERS:
                    violations.append(
                        PolicyViolation(
                            message=f"不允许访问双下划线属性: {node.attr}",
                            lineno=getattr(node, "lineno", None),
                        )
                    )

        if isinstance(node, ast.Call):
            # 禁止直接调用危险函数
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
                violations.append(
                    PolicyViolation(
                        message=f"不允许调用函数: {node.func.id}",
                        lineno=getattr(node, "lineno", None),
                    )
                )
            # 禁止通过属性调用危险函数（如 os.system()）
            # 排除常见安全的属性方法（如 re.compile、df.eval）
            _ATTR_CALL_SKIP = {"compile", "eval"}
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in BANNED_CALLS
                and node.func.attr not in _ATTR_CALL_SKIP
            ):
                violations.append(
                    PolicyViolation(
                        message=f"不允许调用函数: {node.func.attr}",
                        lineno=getattr(node, "lineno", None),
                    )
                )

    if violations:
        first = violations[0]
        where = f" (第 {first.lineno} 行)" if first.lineno else ""
        raise SandboxPolicyError(f"{first.message}{where}")

    if reviewable_violations:
        ordered = sorted(reviewable_violations.values(), key=lambda item: item.root or "")
        raise SandboxReviewRequired(
            [item.root or "" for item in ordered],
            violations=ordered,
        )
