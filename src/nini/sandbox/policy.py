"""沙箱安全策略：AST 静态分析与导入白名单。

## 安全机制（三重防护）

1. **AST 静态分析**（本模块）
   - 白名单导入控制：只允许安全的标准库和科学计算库
   - 禁止函数调用：拦截 eval, exec, __import__ 等危险函数
   - 禁止相对导入：防止访问项目内部模块

2. **受限 builtins**（executor.py）
   - 移除 __import__：强制通过白名单导入
   - 移除 eval/exec/compile：防止动态代码执行
   - 移除 open/input：防止文件系统和用户输入访问
   - 移除 getattr/setattr/delattr：防止对象属性篡改

3. **进程隔离**（executor.py）
   - multiprocessing 子进程：隔离执行环境
   - 资源限制（CPU/内存）：防止资源耗尽
   - 超时终止：防止无限循环

## 白名单设计原则

**Tier 1（完全安全）**：纯计算模块，无 I/O，无副作用
**Tier 2（标准库）**：Python 标准库中的数据处理工具
**Tier 3（科学计算）**：第三方科学计算库（pandas, numpy 等）

## 安全风险评估

**低风险**：
- datetime, collections, itertools, functools：纯数据处理
- math, statistics, random：纯计算
- pandas, numpy：内存操作，无文件系统访问

**中风险**（已拦截）：
- os, sys, subprocess：系统调用
- socket, urllib, requests：网络访问
- pathlib, shutil：文件系统操作

**高风险**（已拦截）：
- eval, exec, compile：动态代码执行
- __import__：绕过白名单
- ctypes, cffi：C 扩展调用
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# 分层白名单：从最安全到受限
# Tier 1: 纯计算/数据处理（完全安全）
_TIER1_SAFE_MODULES = {
    "math",           # 数学函数
    "statistics",     # 统计函数
    "random",         # 随机数生成
    "decimal",        # 精确小数运算
    "fractions",      # 分数运算
    "cmath",          # 复数数学
}

# Tier 2: 标准库工具（安全）
_TIER2_STDLIB_UTILS = {
    "datetime",       # 日期时间处理（★ 数据分析必备）
    "time",           # 时间相关函数
    "calendar",       # 日历操作
    "collections",    # 高级数据结构（deque, Counter, defaultdict 等）
    "itertools",      # 迭代器工具
    "functools",      # 函数式编程工具
    "operator",       # 操作符函数
    "heapq",          # 堆队列
    "bisect",         # 二分查找
    "array",          # 数组
    "copy",           # 深浅拷贝
    "json",           # JSON 处理
    "csv",            # CSV 文件处理
    "re",             # 正则表达式
    "string",         # 字符串常量和工具
    "textwrap",       # 文本包装
    "unicodedata",    # Unicode 数据库
}

# Tier 3: 科学计算栈（安全）
_TIER3_SCIENTIFIC = {
    "pandas",         # 数据框架
    "numpy",          # 数值计算
    "scipy",          # 科学计算
    "statsmodels",    # 统计模型
    "sklearn",        # 机器学习（scikit-learn）
    "matplotlib",     # 绘图
    "plotly",         # 交互式绘图
    "seaborn",        # 统计可视化
}

# 合并所有白名单（共 28 个模块）
ALLOWED_IMPORT_ROOTS: set[str] = (
    _TIER1_SAFE_MODULES
    | _TIER2_STDLIB_UTILS
    | _TIER3_SCIENTIFIC
)

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
