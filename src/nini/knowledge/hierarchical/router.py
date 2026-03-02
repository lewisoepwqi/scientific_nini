"""查询意图分类与路由。

支持基于规则的意图分类和智能检索路由。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nini.config import settings


class QueryIntent(Enum):
    """查询意图类型。"""

    CONCEPT = "concept"  # 概念解释（什么是t检验）
    HOW_TO = "how_to"  # 方法指导（如何做t检验）
    REFERENCE = "reference"  # 参数参考（t检验的参数说明）
    CODE = "code"  # 代码示例（t检验的Python代码）
    COMPARISON = "comparison"  # 方法对比（t检验 vs 方差分析）
    TROUBLESHOOT = "troubleshoot"  # 问题排查（t检验结果异常）


@dataclass
class RoutingPlan:
    """检索路由计划。"""

    intent: QueryIntent
    primary_level: str  # L0, L1, L2
    secondary_level: str | None  # 辅助检索层级
    top_k: int
    strategy: str  # bm25, vector, hybrid
    expand_context: bool = True


class QueryIntentClassifier:
    """查询意图分类器。

    基于规则引擎和关键词匹配进行意图分类。
    """

    # 意图匹配规则（按优先级排序）
    PATTERNS: dict[QueryIntent, list[str]] = {
        QueryIntent.CODE: [
            r"代码",
            r"示例",
            r"python",
            r"r语言",
            r"怎么写",
            r"如何实现",
            r"代码示例",
        ],
        QueryIntent.TROUBLESHOOT: [
            r"错误",
            r"异常",
            r"失败",
            r"报错",
            r"不对",
            r"问题",
            r"为什么.*不",
            r"怎么回事",
        ],
        QueryIntent.COMPARISON: [
            r"区别",
            r"对比",
            r"比较",
            r"vs",
            r"versus",
            r"哪个",
            r"还是",
            r"或者",
        ],
        QueryIntent.HOW_TO: [
            r"如何",
            r"怎么",
            r"怎样做",
            r"步骤",
            r"教程",
            r"指南",
            r"怎么做",
            r"怎样",
        ],
        QueryIntent.REFERENCE: [
            r"参数",
            r"返回值",
            r"说明",
            r"选项",
            r"配置",
            r"属性",
            r"字段",
        ],
        QueryIntent.CONCEPT: [
            r"什么是",
            r".*是什么",
            r"解释",
            r"介绍",
            r"概念",
            r"定义",
        ],
    }

    def classify(self, query: str) -> QueryIntent:
        """分类查询意图。

        Args:
            query: 用户查询文本

        Returns:
            QueryIntent: 查询意图类型
        """
        if not query:
            return QueryIntent.CONCEPT

        query_lower = query.lower()

        # 按优先级顺序匹配
        for intent, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent

        # 默认返回概念查询
        return QueryIntent.CONCEPT


class QueryRouter:
    """查询路由器。

    根据查询意图选择最优的检索策略和层级。
    """

    # 意图到路由计划的映射
    ROUTING_MAP: dict[QueryIntent, dict[str, Any]] = {
        QueryIntent.CONCEPT: {
            "primary_level": "L0",
            "secondary_level": "L1",
            "top_k": 3,
            "strategy": "bm25",
        },
        QueryIntent.HOW_TO: {
            "primary_level": "L1",
            "secondary_level": "L2",
            "top_k": 5,
            "strategy": "hybrid",
        },
        QueryIntent.REFERENCE: {
            "primary_level": "L2",
            "secondary_level": None,
            "top_k": 5,
            "strategy": "vector",
        },
        QueryIntent.CODE: {
            "primary_level": "L2",
            "secondary_level": None,
            "top_k": 5,
            "strategy": "vector",
        },
        QueryIntent.COMPARISON: {
            "primary_level": "L1",
            "secondary_level": "L0",
            "top_k": 4,
            "strategy": "hybrid",
        },
        QueryIntent.TROUBLESHOOT: {
            "primary_level": "L1",
            "secondary_level": "L2",
            "top_k": 5,
            "strategy": "hybrid",
        },
    }

    def __init__(self) -> None:
        """初始化路由器。"""
        self.classifier = QueryIntentClassifier()

    def route(self, query: str) -> RoutingPlan:
        """为查询生成路由计划。

        Args:
            query: 用户查询文本

        Returns:
            RoutingPlan: 路由计划
        """
        intent = self.classifier.classify(query)
        config = self.ROUTING_MAP[intent]

        return RoutingPlan(
            intent=intent,
            primary_level=config["primary_level"],
            secondary_level=config["secondary_level"],
            top_k=config["top_k"],
            strategy=config["strategy"],
            expand_context=True,
        )

    def route_with_metadata(self, query: str) -> tuple[RoutingPlan, dict[str, Any]]:
        """为查询生成路由计划，包含元数据。

        Returns:
            (RoutingPlan, metadata) 元组
        """
        plan = self.route(query)

        metadata = {
            "intent": plan.intent.value,
            "intent_name": plan.intent.name,
            "confidence": "high",  # 规则引擎置信度固定为高
            "routing_reason": self._get_routing_reason(plan),
        }

        return plan, metadata

    def _get_routing_reason(self, plan: RoutingPlan) -> str:
        """获取路由决策的原因说明。"""
        reasons = {
            QueryIntent.CONCEPT: "概念查询优先搜索文档级摘要",
            QueryIntent.HOW_TO: "方法查询需要章节级详细说明",
            QueryIntent.REFERENCE: "参考查询精确到段落级内容",
            QueryIntent.CODE: "代码查询精确到段落级代码示例",
            QueryIntent.COMPARISON: "对比查询需要多层级信息",
            QueryIntent.TROUBLESHOOT: "问题排查需要详细说明",
        }
        return reasons.get(plan.intent, "默认路由策略")
