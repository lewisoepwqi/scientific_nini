"""任务路由器 —— 将用户意图映射到目标 Specialist Agent。

提供双轨制路由策略：
- 规则路由（< 5ms）：基于关键词集合匹配，置信度 >= 0.7 时直接返回
- LLM 兜底路由（~500ms）：规则置信度不足时，调用 model_resolver.chat(purpose="planning")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from nini.intent import detect_multi_intent
from nini.intent.multi_intent import _PARALLEL_MARKERS

logger = logging.getLogger(__name__)

# 内置关键词路由规则：(关键词集合, 目标 agent_id)
_BUILTIN_RULES: list[tuple[frozenset[str], str]] = [
    (frozenset({"文献", "论文", "引用", "期刊", "搜索", "检索"}), "literature_search"),
    (frozenset({"精读", "批注", "阅读", "理解"}), "literature_reading"),
    (frozenset({"清洗", "缺失值", "异常值", "预处理", "脏数据"}), "data_cleaner"),
    (frozenset({"统计", "检验", "p值", "显著性", "回归", "方差", "anova"}), "statistician"),
    (frozenset({"图表", "可视化", "画图", "箱线图", "散点图", "柱状图"}), "viz_designer"),
    (frozenset({"写作", "润色", "摘要", "引言", "讨论", "结论"}), "writing_assistant"),
]

# LLM 兜底路由的置信度阈值
_LLM_FALLBACK_THRESHOLD = 0.7

# LLM 路由提示模板
_LLM_ROUTING_PROMPT = """\
你是任务路由器。请分析用户意图并输出路由决策。

可用 Agent：
- literature_search：文献检索、论文搜索、引用获取
- literature_reading：文献精读、批注、深度理解
- data_cleaner：数据清洗、缺失值处理、异常值检测
- statistician：统计检验、回归分析、方差分析、显著性检验
- viz_designer：数据可视化、图表制作
- writing_assistant：科研写作、论文润色、摘要撰写

用户意图：{intent}

请输出 JSON 格式的路由决策（仅输出 JSON，不要解释）：
{{
  "agent_ids": ["agent_id1", "agent_id2"],
  "tasks": ["分配给 agent_id1 的任务描述", "分配给 agent_id2 的任务描述"],
  "confidence": 0.9,
  "parallel": true
}}
"""

_LLM_BATCH_ROUTING_PROMPT = """\
你是任务路由器。请批量分析以下任务并输出路由决策。

可用 Agent（同上）：
literature_search, literature_reading, data_cleaner, statistician, viz_designer, writing_assistant

任务列表：
{tasks_json}

请输出 JSON 数组（与输入顺序一致，仅输出 JSON）：
[
  {{"agent_ids": [...], "tasks": [...], "confidence": 0.9, "parallel": true}},
  ...
]
"""


@dataclass
class RoutingDecision:
    """路由决策结果。"""

    agent_ids: list[str]
    tasks: list[str]
    confidence: float
    strategy: str  # "rule" 或 "llm"
    parallel: bool = True


class TaskRouter:
    """任务路由器。

    双轨制路由：规则路由 confidence >= 0.7 直接返回；否则调用 LLM 兜底。
    """

    def __init__(
        self,
        model_resolver: Any = None,
        *,
        enable_llm_fallback: bool = True,
    ) -> None:
        """初始化路由器。

        Args:
            model_resolver: ModelResolver 实例，用于 LLM 兜底路由
            enable_llm_fallback: 是否启用 LLM 兜底路由
        """
        self._resolver = model_resolver
        self._enable_llm_fallback = enable_llm_fallback
        self._rules = list(_BUILTIN_RULES)

    def _rule_route(self, intent: str) -> RoutingDecision:
        """基于关键词的规则路由（< 5ms）。

        置信度 = 命中关键词数 / 规则关键词总数（线性计算，最高 1.0）。
        多规则命中时，每个命中规则对应一个 agent_id，任务均为原始意图。
        """
        intent_lower = intent.lower()
        matched_agents: list[str] = []
        max_confidence = 0.0

        for keywords, agent_id in self._rules:
            hit_count = sum(1 for kw in keywords if kw in intent_lower)
            if hit_count == 0:
                continue
            # 置信度线性计算：1 个命中 = 0.7，全部命中 = 1.0
            # 公式：0.7 + 0.3 * (hit_count - 1) / max(1, len(keywords) - 1)
            n = len(keywords)
            confidence = 0.7 + 0.3 * (hit_count - 1) / max(1, n - 1)
            confidence = min(confidence, 1.0)
            if confidence > max_confidence:
                max_confidence = confidence
            if agent_id not in matched_agents:
                matched_agents.append(agent_id)

        if not matched_agents:
            return RoutingDecision(
                agent_ids=[],
                tasks=[],
                confidence=0.0,
                strategy="rule",
            )

        return RoutingDecision(
            agent_ids=matched_agents,
            tasks=[intent] * len(matched_agents),
            confidence=max_confidence,
            strategy="rule",
        )

    async def _llm_route(self, intent: str, context: dict[str, Any]) -> RoutingDecision:
        """LLM 兜底路由，调用 model_resolver.chat(purpose="planning")。

        解析失败时返回空决策（不抛出异常）。
        """
        if self._resolver is None:
            logger.warning("TaskRouter._llm_route: model_resolver 未配置，跳过 LLM 路由")
            return RoutingDecision(agent_ids=[], tasks=[], confidence=0.0, strategy="llm")

        prompt = _LLM_ROUTING_PROMPT.format(intent=intent)
        messages = [{"role": "user", "content": prompt}]

        try:
            full_response = ""
            async for chunk in self._resolver.chat(messages, [], purpose="planning"):
                if hasattr(chunk, "text") and chunk.text:
                    full_response += chunk.text

            # 提取 JSON
            json_text = _extract_json_block(full_response)
            if not json_text:
                logger.warning("TaskRouter._llm_route: LLM 未返回有效 JSON")
                return RoutingDecision(agent_ids=[], tasks=[], confidence=0.0, strategy="llm")

            data = json.loads(json_text)
            agent_ids = data.get("agent_ids", [])
            tasks = data.get("tasks", [])
            confidence = float(data.get("confidence", 0.8))
            parallel = bool(data.get("parallel", True))

            # 确保 tasks 与 agent_ids 等长
            if len(tasks) < len(agent_ids):
                tasks = tasks + [intent] * (len(agent_ids) - len(tasks))
            elif len(tasks) > len(agent_ids):
                tasks = tasks[: len(agent_ids)]

            return RoutingDecision(
                agent_ids=agent_ids,
                tasks=tasks,
                confidence=confidence,
                strategy="llm",
                parallel=parallel,
            )
        except Exception as exc:
            logger.warning("TaskRouter._llm_route 失败: %s", exc)
            return RoutingDecision(agent_ids=[], tasks=[], confidence=0.0, strategy="llm")

    async def route(
        self,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> RoutingDecision:
        """路由单个意图。

        规则路由 confidence < 0.7 且 enable_llm_fallback=True 时触发 LLM 兜底。

        Args:
            intent: 用户意图字符串
            context: 额外上下文信息（可选）

        Returns:
            RoutingDecision
        """
        context = context or {}

        # 多意图检测：在规则路由之前拆分复合查询
        sub_intents = detect_multi_intent(intent)
        if sub_intents is not None:
            is_parallel = bool(_PARALLEL_MARKERS.search(intent))
            batch = await self.route_batch(sub_intents)
            merged = RoutingDecision(
                agent_ids=[aid for d in batch for aid in d.agent_ids],
                tasks=[t for d in batch for t in d.tasks],
                confidence=min((d.confidence for d in batch), default=0.0),
                strategy="multi_intent",
                parallel=is_parallel,
            )
            return merged

        rule_result = self._rule_route(intent)

        if rule_result.confidence >= _LLM_FALLBACK_THRESHOLD or not self._enable_llm_fallback:
            return rule_result

        # 规则置信度不足，尝试 LLM 兜底
        try:
            llm_result = await self._llm_route(intent, context)
            if llm_result.agent_ids:
                return llm_result
        except Exception as exc:
            logger.warning("TaskRouter.route LLM 兜底失败: %s，降级为规则结果", exc)

        return rule_result

    async def route_batch(
        self,
        tasks: list[str],
    ) -> list[RoutingDecision]:
        """批量路由任务列表，一次 LLM 调用分析所有任务。

        返回顺序与输入一致；空列表输入返回空列表。

        Args:
            tasks: 任务描述列表

        Returns:
            与输入顺序一致的 RoutingDecision 列表
        """
        if not tasks:
            return []

        if self._resolver is None or not self._enable_llm_fallback:
            # 无 LLM 时逐个规则路由
            results = []
            for task in tasks:
                results.append(self._rule_route(task))
            return results

        tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)
        prompt = _LLM_BATCH_ROUTING_PROMPT.format(tasks_json=tasks_json)
        messages = [{"role": "user", "content": prompt}]

        try:
            full_response = ""
            async for chunk in self._resolver.chat(messages, [], purpose="planning"):
                if hasattr(chunk, "text") and chunk.text:
                    full_response += chunk.text

            json_text = _extract_json_block(full_response)
            if not json_text:
                raise ValueError("LLM 未返回有效 JSON")

            data_list = json.loads(json_text)
            if not isinstance(data_list, list):
                raise ValueError(f"期望 JSON 数组，实际: {type(data_list)}")

            results: list[RoutingDecision] = []
            for i, (task, data) in enumerate(zip(tasks, data_list)):
                agent_ids = data.get("agent_ids", [])
                sub_tasks = data.get("tasks", [])
                confidence = float(data.get("confidence", 0.8))
                parallel = bool(data.get("parallel", True))

                if len(sub_tasks) < len(agent_ids):
                    sub_tasks = sub_tasks + [task] * (len(agent_ids) - len(sub_tasks))
                elif len(sub_tasks) > len(agent_ids):
                    sub_tasks = sub_tasks[: len(agent_ids)]

                results.append(
                    RoutingDecision(
                        agent_ids=agent_ids,
                        tasks=sub_tasks,
                        confidence=confidence,
                        strategy="llm",
                        parallel=parallel,
                    )
                )

            # 若 LLM 返回数量不足，补充规则路由
            for task in tasks[len(results) :]:
                results.append(self._rule_route(task))

            return results

        except Exception as exc:
            logger.warning("TaskRouter.route_batch LLM 调用失败: %s，降级为规则路由", exc)
            return [self._rule_route(task) for task in tasks]


def _extract_json_block(text: str) -> str | None:
    """从 LLM 响应中提取 JSON 块。

    优先尝试 ```json ... ``` 代码块，否则直接返回原文。
    """
    if not text:
        return None
    # 尝试提取 markdown code block
    import re

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()

    # 尝试直接找 JSON 数组或对象
    text = text.strip()
    if (text.startswith("{") and text.endswith("}")) or (
        text.startswith("[") and text.endswith("]")
    ):
        return text

    # 尝试找第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return None
