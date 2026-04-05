"""结果融合引擎 —— 将多个子 Agent 结果融合为一段结构化文本。

支持四种融合策略：
- concatenate：直接拼接（零 LLM 调用）
- summarize：LLM 生成整合摘要（purpose="analysis"，超时 60s 降级为 concatenate）
- consensus：LLM 共识提取 + 冲突标注
- hierarchical：分批 summarize 后再汇总（>4 个结果时）

strategy="auto" 时自动分档：
  0 个结果 → concatenate（返回空内容）
  1 个结果 → concatenate（直接返回，零 LLM 调用）
  2-4 个结果 → summarize
  >4 个结果 → hierarchical
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_SUMMARIZE_TIMEOUT_SECONDS = 60
_HIERARCHICAL_BATCH_SIZE = 4

_SUMMARIZE_PROMPT_TEMPLATE = """\
以下是多个 AI Agent 的执行结果，请综合整理成一份连贯的分析摘要：

{results_text}

请输出整合后的结论，保留重要细节，去除重复内容。
"""

_CONSENSUS_PROMPT_TEMPLATE = """\
以下是多个 AI Agent 针对同一问题的分析结果：

{results_text}

请：
1. 提取各 Agent 的共同结论
2. 标注相互矛盾的结论（如有）
3. 输出综合摘要

请直接输出摘要，格式为纯文本。
"""


@dataclass(frozen=True)
class FusionResult:
    """融合结果数据类（不可变）。

    frozen=True 保证融合结果在传递和消费过程中不被修改。
    """

    content: str
    strategy: str
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


class ResultFusionEngine:
    """结果融合引擎。

    负责将多个 SubAgentResult 按策略融合为 FusionResult。
    """

    def __init__(self, model_resolver: Any = None) -> None:
        """初始化融合引擎。

        Args:
            model_resolver: ModelResolver 实例，用于 summarize/consensus 策略
        """
        self._resolver = model_resolver

    def _concatenate(self, results: list[Any]) -> FusionResult:
        """拼接策略：直接拼接各 SubAgentResult.summary，换行分隔，不调用 LLM。"""
        parts = [r.summary for r in results if r.summary]
        content = "\n\n".join(parts)
        sources = [r.agent_id for r in results]
        return FusionResult(content=content, strategy="concatenate", sources=sources)

    async def _summarize(self, results: list[Any]) -> FusionResult:
        """摘要策略：调用 LLM 生成整合摘要，超时 60s 降级为 concatenate。"""
        sources = [r.agent_id for r in results]
        conflicts = self._detect_conflicts(results)

        if self._resolver is None:
            logger.warning(
                "ResultFusionEngine._summarize: model_resolver 未配置，降级为 concatenate"
            )
            fallback = self._concatenate(results)
            fallback.conflicts = conflicts
            return fallback

        results_text = _format_results_for_llm(results)
        prompt = _SUMMARIZE_PROMPT_TEMPLATE.format(results_text=results_text)
        messages = [{"role": "user", "content": prompt}]

        try:
            content = await asyncio.wait_for(
                self._call_llm_for_summary(messages),
                timeout=_SUMMARIZE_TIMEOUT_SECONDS,
            )
            return FusionResult(
                content=content,
                strategy="summarize",
                conflicts=conflicts,
                sources=sources,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "ResultFusionEngine._summarize: LLM 调用超时（%ds），降级为 concatenate",
                _SUMMARIZE_TIMEOUT_SECONDS,
            )
            fallback = self._concatenate(results)
            # FusionResult 是 frozen，需构造新对象注入 conflicts
            return FusionResult(
                content=fallback.content,
                strategy=fallback.strategy,
                conflicts=conflicts,
                sources=fallback.sources,
            )
        except Exception as exc:
            logger.warning(
                "ResultFusionEngine._summarize: LLM 调用失败: %s，降级为 concatenate", exc
            )
            fallback = self._concatenate(results)
            return FusionResult(
                content=fallback.content,
                strategy=fallback.strategy,
                conflicts=conflicts,
                sources=fallback.sources,
            )

    async def _consensus(self, results: list[Any]) -> FusionResult:
        """共识策略：LLM 共识提取 + 冲突标注。"""
        sources = [r.agent_id for r in results]
        conflicts = self._detect_conflicts(results)

        if self._resolver is None:
            logger.warning(
                "ResultFusionEngine._consensus: model_resolver 未配置，降级为 concatenate"
            )
            fallback = self._concatenate(results)
            fallback.conflicts = conflicts
            return fallback

        results_text = _format_results_for_llm(results)
        prompt = _CONSENSUS_PROMPT_TEMPLATE.format(results_text=results_text)
        messages = [{"role": "user", "content": prompt}]

        try:
            content = await asyncio.wait_for(
                self._call_llm_for_summary(messages),
                timeout=_SUMMARIZE_TIMEOUT_SECONDS,
            )
            return FusionResult(
                content=content,
                strategy="consensus",
                conflicts=conflicts,
                sources=sources,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "ResultFusionEngine._consensus: LLM 调用失败: %s，降级为 concatenate", exc
            )
            fallback = self._concatenate(results)
            fallback.conflicts = conflicts
            return fallback

    async def _hierarchical(self, results: list[Any]) -> FusionResult:
        """分层策略：分批 summarize 后再汇总。

        每批最多 _HIERARCHICAL_BATCH_SIZE（4）个结果，批次间递归汇总。
        """
        sources = [r.agent_id for r in results]

        # 分批处理
        batches = [
            results[i : i + _HIERARCHICAL_BATCH_SIZE]
            for i in range(0, len(results), _HIERARCHICAL_BATCH_SIZE)
        ]

        # 每批先 summarize
        batch_results: list[FusionResult] = []
        for batch in batches:
            batch_fusion = await self._summarize(batch)
            batch_results.append(batch_fusion)

        # 将批次结果转换为伪 SubAgentResult，再汇总
        if len(batch_results) <= 1:
            result = (
                batch_results[0]
                if batch_results
                else FusionResult(content="", strategy="hierarchical")
            )
            result.sources = sources
            result.strategy = "hierarchical"
            return result

        # 批次间再做一次 summarize
        pseudo_results = [_FusionResultAdapter(r) for r in batch_results]
        final = await self._summarize(pseudo_results)
        final.strategy = "hierarchical"
        final.sources = sources
        return final

    def _detect_conflicts(self, results: list[Any]) -> list[dict[str, Any]]:
        """冲突检测（仅标注，不阻断融合流程）。

        对结果中的数值结论做简单比对，标注到 FusionResult.conflicts。
        """
        if len(results) < 2:
            return []

        conflicts: list[dict[str, Any]] = []
        summaries = [(r.agent_id, r.summary) for r in results if r.summary]

        # 简单数值冲突检测：提取摘要中的数字，方差超阈值则标注
        import re

        numeric_pattern = re.compile(r"\b(\d+(?:\.\d+)?)\b")
        number_sets: list[tuple[str, list[float]]] = []
        for agent_id, summary in summaries:
            nums = [float(m) for m in numeric_pattern.findall(summary) if float(m) > 0]
            if nums:
                number_sets.append((agent_id, nums))

        if len(number_sets) >= 2:
            # 检查各 Agent 主要数字的差异（仅取最大值比较）
            max_values = [(aid, max(nums)) for aid, nums in number_sets]
            if len(max_values) >= 2:
                vals = [v for _, v in max_values]
                if vals[0] > 0 and abs(max(vals) - min(vals)) / max(vals) > 0.5:
                    conflicts.append(
                        {
                            "type": "numeric_discrepancy",
                            "agents": [aid for aid, _ in max_values],
                            "description": f"Agent 间数值结论存在显著差异：{max_values}",
                        }
                    )

        return conflicts

    async def _call_llm_for_summary(self, messages: list[dict[str, Any]]) -> str:
        """调用 LLM 生成摘要文本。"""
        full_response = ""
        async for chunk in self._resolver.chat(messages, [], purpose="analysis"):
            if hasattr(chunk, "text") and chunk.text:
                full_response += chunk.text
        return full_response.strip()

    async def fuse(
        self,
        results: list[Any],
        strategy: str = "auto",
    ) -> FusionResult:
        """融合多个 SubAgentResult。

        strategy="auto" 时自动分档：
          0 → concatenate（空内容）
          1 → concatenate（直接返回，零 LLM 调用）
          2-4 → summarize
          >4 → hierarchical

        不支持的策略名降级为 concatenate 并记录 WARNING。

        Args:
            results: SubAgentResult 列表
            strategy: 融合策略名称，"auto"/"concatenate"/"summarize"/"consensus"/"hierarchical"

        Returns:
            FusionResult
        """
        _VALID_STRATEGIES = {"concatenate", "summarize", "consensus", "hierarchical", "auto"}

        if strategy not in _VALID_STRATEGIES:
            logger.warning(
                "ResultFusionEngine.fuse: 不支持的策略 '%s'，降级为 concatenate", strategy
            )
            strategy = "concatenate"

        if strategy == "auto":
            n = len(results)
            if n == 0:
                return FusionResult(content="", strategy="concatenate")
            elif n == 1:
                return self._concatenate(results)
            elif n <= 4:
                strategy = "summarize"
            else:
                strategy = "hierarchical"

        if strategy == "concatenate":
            return self._concatenate(results)
        elif strategy == "summarize":
            return await self._summarize(results)
        elif strategy == "consensus":
            return await self._consensus(results)
        elif strategy == "hierarchical":
            return await self._hierarchical(results)
        else:
            # 兜底（逻辑上不会到达）
            return self._concatenate(results)


class _FusionResultAdapter:
    """将 FusionResult 适配为 SubAgentResult 接口，供分层汇总时使用。"""

    def __init__(self, fusion_result: FusionResult) -> None:
        self.agent_id = f"batch_fusion_{fusion_result.strategy}"
        self.success = True
        self.summary = fusion_result.content


def _format_results_for_llm(results: list[Any]) -> str:
    """将结果列表格式化为 LLM 可读的文本。"""
    parts: list[str] = []
    for i, r in enumerate(results, 1):
        agent_id = getattr(r, "agent_id", f"agent_{i}")
        summary = getattr(r, "summary", "") or ""
        parts.append(f"【Agent {i}: {agent_id}】\n{summary}")
    return "\n\n".join(parts)
