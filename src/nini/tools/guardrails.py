"""工具调用安全守卫（Guardrails）框架。

提供可插拔的工具调用拦截机制，在 ToolRegistry.execute() 调用 Tool.execute() 之前
对工具调用进行安全评估，阻止危险操作。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuardrailAction(Enum):
    """Guardrail 决策枚举。"""

    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_CONFIRMATION = "require_confirmation"


@dataclass
class GuardrailDecision:
    """Guardrail 评估结果，包含决策类型和原因说明。"""

    decision: GuardrailAction
    reason: str = field(default="")


class ToolGuardrail(ABC):
    """工具调用守卫抽象基类。

    子类通过实现 evaluate() 方法定义具体的拦截规则。
    """

    @abstractmethod
    def evaluate(self, tool_name: str, kwargs: dict[str, Any]) -> GuardrailDecision:
        """评估工具调用是否允许执行。

        Args:
            tool_name: 工具名称
            kwargs: 工具调用参数

        Returns:
            GuardrailDecision 实例，包含 ALLOW / BLOCK / REQUIRE_CONFIRMATION 决策
        """
        ...


# 禁止访问的系统路径模式（扩展覆盖 /proc/、/dev/、/root/、Windows 系统路径）
_SYSTEM_PATH_PATTERN = re.compile(
    r"("
    r"/etc/|/sys/|~/\.ssh/|"
    r"/proc/|/dev/|/root/|"
    r"[A-Za-z]:\\Windows\\|[A-Za-z]:\\System32|"
    r"[A-Za-z]:\\ProgramData\\"
    r")"
)

# 标记原始数据集的名称关键词
_RAW_DATASET_KEYWORDS = ("_raw", "_original", "original")


class DangerousPatternGuardrail(ToolGuardrail):
    """检测并拦截针对科研数据的破坏性操作。

    拦截规则：
    1. clean_data + inplace=True + dataset 名含 _raw/_original/original → BLOCK
    2. organize_workspace + delete_all=True 或 pattern="*" → BLOCK
    3. 任意工具参数字符串含系统路径（/etc/、/sys/、~/.ssh/）→ BLOCK
    """

    def evaluate(self, tool_name: str, kwargs: dict[str, Any]) -> GuardrailDecision:
        # 规则 1：禁止对原始数据集执行 inplace 覆写
        if tool_name == "clean_data":
            if kwargs.get("inplace") is True:
                dataset_name = str(kwargs.get("dataset_name", "") or kwargs.get("name", "") or "")
                if any(kw in dataset_name for kw in _RAW_DATASET_KEYWORDS):
                    return GuardrailDecision(
                        decision=GuardrailAction.BLOCK,
                        reason=(
                            f"禁止对原始数据集 '{dataset_name}' 执行 inplace 修改，"
                            "请先复制数据集再进行清洗操作"
                        ),
                    )

        # 规则 2：禁止批量删除工作区
        if tool_name == "organize_workspace":
            if kwargs.get("delete_all") is True:
                return GuardrailDecision(
                    decision=GuardrailAction.BLOCK,
                    reason="禁止使用 delete_all=True 批量删除工作区文件",
                )
            if kwargs.get("pattern") == "*":
                return GuardrailDecision(
                    decision=GuardrailAction.BLOCK,
                    reason="禁止使用通配符 pattern='*' 批量删除工作区文件",
                )

        # 规则 3：禁止参数中含有危险系统路径
        for value in kwargs.values():
            if isinstance(value, str) and _SYSTEM_PATH_PATTERN.search(value):
                return GuardrailDecision(
                    decision=GuardrailAction.BLOCK,
                    reason=f"参数包含禁止访问的系统路径: '{value}'",
                )

        # 规则 4：路径遍历检测（含 .. 组件的路径型字符串）
        for value in kwargs.values():
            if not isinstance(value, str):
                continue
            # 仅检测看起来像路径的字符串（含 / 或 \）
            if "/" not in value and "\\" not in value:
                continue
            # 检测路径遍历：包含 .. 组件
            if ".." in value.split("/") or ".." in value.split("\\"):
                return GuardrailDecision(
                    decision=GuardrailAction.BLOCK,
                    reason=f"参数包含路径遍历: '{value}'",
                )

        return GuardrailDecision(decision=GuardrailAction.ALLOW)
