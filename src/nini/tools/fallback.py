"""技能降级策略模块。

提供可配置的降级规则管理和执行。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

import numpy as np
from scipy import stats

if TYPE_CHECKING:
    from nini.agent.session import Session
    from nini.tools.base import Skill

logger = logging.getLogger(__name__)


@dataclass
class FallbackRule:
    """单个降级规则定义。"""

    fallback_skill: str
    condition: str
    reason: str
    parameter_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class FallbackStrategyConfig:
    """降级策略配置。"""

    skill_name: str
    rules: list[FallbackRule]
    precondition_check: Callable[[str, "Session", dict[str, Any]], dict[str, Any]] | None = None


class FallbackManager:
    """管理技能降级策略。

    使用策略模式实现可配置的降级规则。
    """

    # 默认降级映射配置
    DEFAULT_FALLBACK_MAP: dict[str, list[dict[str, Any]]] = {
        "t_test": [
            {
                "fallback_skill": "mann_whitney",
                "condition": "non_normal",
                "reason": "数据不符合正态性假设，改用非参数检验",
            },
        ],
        "anova": [
            {
                "fallback_skill": "kruskal_wallis",
                "condition": "non_normal_or_variance_hetero",
                "reason": "数据不符合正态性或方差齐性假设，改用非参数检验",
            },
        ],
    }

    def __init__(self):
        self._strategies: dict[str, FallbackStrategyConfig] = {}
        self._precondition_checks: dict[
            str, Callable[["Session", dict[str, Any]], dict[str, Any]]
        ] = {}
        self._load_default_strategies()

    def _load_default_strategies(self) -> None:
        """加载默认降级策略。"""
        for skill_name, rules_data in self.DEFAULT_FALLBACK_MAP.items():
            rules = [FallbackRule(**rule) for rule in rules_data]
            self._strategies[skill_name] = FallbackStrategyConfig(
                skill_name=skill_name,
                rules=rules,
            )

        # 注册默认前提条件检查
        self._precondition_checks["t_test"] = self._check_normality_precondition
        self._precondition_checks["anova"] = self._check_normality_precondition

    def register_strategy(
        self,
        skill_name: str,
        rules: list[FallbackRule],
        precondition_check: Callable[["Session", dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        """注册降级策略。

        Args:
            skill_name: 原始技能名称
            rules: 降级规则列表（按优先级排序）
            precondition_check: 可选的前提条件检查函数
        """
        self._strategies[skill_name] = FallbackStrategyConfig(
            skill_name=skill_name,
            rules=rules,
        )
        if precondition_check:
            self._precondition_checks[skill_name] = precondition_check
        logger.info("注册降级策略: %s", skill_name)

    def unregister_strategy(self, skill_name: str) -> None:
        """注销降级策略。"""
        self._strategies.pop(skill_name, None)
        self._precondition_checks.pop(skill_name, None)

    def get_strategy(self, skill_name: str) -> FallbackStrategyConfig | None:
        """获取技能的降级策略配置。"""
        return self._strategies.get(skill_name)

    def has_fallback(self, skill_name: str) -> bool:
        """检查技能是否有降级策略。"""
        return skill_name in self._strategies and len(self._strategies[skill_name].rules) > 0

    async def should_trigger_fallback(
        self,
        skill_name: str,
        session: "Session",
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """判断是否应该触发降级。

        Args:
            skill_name: 技能名称
            session: 会话对象
            kwargs: 技能参数

        Returns:
            {"trigger": bool, "reason": str}
        """
        # 检查是否有注册的前提条件检查
        check_func = self._precondition_checks.get(skill_name)
        if check_func:
            return check_func(session, kwargs)

        return {"trigger": False, "reason": ""}

    def _check_normality_precondition(
        self,
        session: "Session",
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """检查正态性前提条件（用于 t_test 和 anova）。"""
        trigger = False
        reason = ""

        dataset_name = kwargs.get("dataset_name")
        value_column = kwargs.get("value_column")
        group_column = kwargs.get("group_column")

        if dataset_name and value_column and group_column:
            df = session.datasets.get(dataset_name)
            if df is not None:
                groups = df[group_column].dropna().unique()

                # 检查正态性
                non_normal_groups = []
                for group in groups:
                    group_data = df[df[group_column] == group][value_column].dropna()
                    if len(group_data) >= 3 and len(group_data) <= 5000:
                        try:
                            stat, p = stats.shapiro(group_data)
                            if p < 0.05:
                                non_normal_groups.append(str(group))
                        except Exception:
                            pass

                if non_normal_groups:
                    trigger = True
                    reason = f"以下组不符合正态性假设: {', '.join(non_normal_groups)}"

        return {"trigger": trigger, "reason": reason}

    async def execute_fallback(
        self,
        skill_name: str,
        session: "Session",
        kwargs: dict[str, Any],
        context: dict[str, Any],
        skill_resolver: Callable[[str], "Skill" | None],
        skill_executor: Callable[[str, "Session", dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        """执行降级策略。

        Args:
            skill_name: 原始技能名称
            session: 会话对象
            kwargs: 原始技能参数
            context: 降级上下文（包含 reason 等）
            skill_resolver: 技能解析函数 (name) -> Skill
            skill_executor: 技能执行函数 (name, session, kwargs) -> result

        Returns:
            降级执行结果
        """
        strategy = self._strategies.get(skill_name)
        if not strategy:
            return {
                "success": False,
                "message": f"技能 {skill_name} 没有配置降级策略",
                "original_skill": skill_name,
                "fallback": False,
            }

        for rule in strategy.rules:
            fallback_skill_name = rule.fallback_skill

            # 检查降级技能是否存在
            if skill_resolver(fallback_skill_name) is None:
                logger.warning("降级技能 %s 不存在，跳过", fallback_skill_name)
                continue

            # 参数映射处理
            fallback_kwargs = kwargs.copy()
            if rule.parameter_mapping:
                for src_param, dst_param in rule.parameter_mapping.items():
                    if src_param in fallback_kwargs:
                        fallback_kwargs[dst_param] = fallback_kwargs.pop(src_param)

            # 执行降级技能
            fallback_result = await skill_executor(
                fallback_skill_name,
                session,
                fallback_kwargs,
            )

            if fallback_result.get("success"):
                return {
                    **fallback_result,
                    "original_skill": skill_name,
                    "fallback_skill": fallback_skill_name,
                    "fallback": True,
                    "fallback_reason": rule.reason,
                    "fallback_context": context.get("reason", ""),
                }

        # 所有降级都失败
        return {
            "success": False,
            "message": f"技能 {skill_name} 及其降级策略均失败",
            "original_skill": skill_name,
            "fallback": False,
        }


# 全局降级管理器实例
_fallback_manager: FallbackManager | None = None


def get_fallback_manager() -> FallbackManager:
    """获取全局降级管理器实例（单例模式）。"""
    global _fallback_manager
    if _fallback_manager is None:
        _fallback_manager = FallbackManager()
    return _fallback_manager


def reset_fallback_manager() -> None:
    """重置全局降级管理器（主要用于测试）。"""
    global _fallback_manager
    _fallback_manager = None
