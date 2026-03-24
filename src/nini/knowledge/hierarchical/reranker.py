"""检索结果重排序模块。

支持 Cross-Encoder 重排序和轻量级模型。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from nini.config import settings

logger = logging.getLogger(__name__)


def _force_offline_local_models() -> bool:
    """是否强制仅使用本地离线模型。"""
    return (
        os.environ.get("NINI_FORCE_LOCAL_MODELS") == "1"
        or os.environ.get("HF_HUB_OFFLINE") == "1"
        or os.environ.get("TRANSFORMERS_OFFLINE") == "1"
    )


@dataclass
class RankedResult:
    """重排序后的结果。"""

    id: str
    content: str
    initial_score: float
    rerank_score: float
    source: str
    level: str
    metadata: dict[str, Any]


class CrossEncoderReranker:
    """Cross-Encoder 重排序器。

    使用轻量级 Cross-Encoder 模型对检索结果进行精确重排序。
    """

    def __init__(self, model_name: str | None = None) -> None:
        """初始化重排序器。

        Args:
            model_name: 模型名称，默认使用配置值
        """
        self.model_name = model_name or settings.hierarchical_reranker_model
        self._model: Any = None
        self._available = False

    async def initialize(self) -> bool:
        """异步初始化模型。

        Returns:
            是否成功加载模型
        """
        try:
            # 延迟导入，避免启动时加载
            import importlib

            sentence_transformers = importlib.import_module("sentence_transformers")
            cross_encoder_cls = getattr(sentence_transformers, "CrossEncoder", None)
            if not callable(cross_encoder_cls):
                logger.warning("sentence_transformers 缺少 CrossEncoder，重排序不可用")
                return False

            logger.info(f"加载 Cross-Encoder 模型: {self.model_name}")
            try:
                self._model = cross_encoder_cls(self.model_name, local_files_only=True)
            except Exception:
                if _force_offline_local_models():
                    logger.warning("离线模式下未命中本地重排序模型缓存: %s", self.model_name)
                    return False
                self._model = cross_encoder_cls(self.model_name)
            self._available = True
            logger.info("Cross-Encoder 模型加载成功")
            return True

        except ImportError:
            logger.warning(
                "sentence-transformers 未安装，重排序功能不可用。"
                "安装: pip install sentence-transformers"
            )
            return False

        except Exception as e:
            logger.warning(f"加载 Cross-Encoder 模型失败: {e}")
            return False

    @property
    def is_available(self) -> bool:
        """检查模型是否可用。"""
        return self._available and self._model is not None

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        batch_size: int = 8,
    ) -> list[RankedResult]:
        """重排序候选结果。

        Args:
            query: 查询文本
            candidates: 候选结果列表
            top_n: 返回前 N 个结果
            batch_size: 批处理大小

        Returns:
            重排序后的结果列表
        """
        if not self.is_available or not candidates:
            # 模型不可用，返回原始排序
            return self._fallback_ranking(candidates, top_n)

        try:
            # 构建 query-document 对
            pairs = [(query, c.get("content", "")) for c in candidates]

            # 分批计算分数
            scores = await self._compute_scores_batch(pairs, batch_size)

            # 创建重排序结果
            ranked_results = []
            for i, (candidate, score) in enumerate(zip(candidates, scores)):
                ranked_results.append(
                    RankedResult(
                        id=candidate.get("id", ""),
                        content=candidate.get("content", ""),
                        initial_score=candidate.get("score", 0.0),
                        rerank_score=float(score),
                        source=candidate.get("source", ""),
                        level=candidate.get("level", ""),
                        metadata={
                            **candidate.get("metadata", {}),
                            "rerank_score": float(score),
                        },
                    )
                )

            # 按重排序分数排序
            ranked_results.sort(key=lambda x: x.rerank_score, reverse=True)
            return ranked_results[:top_n]

        except Exception as e:
            logger.warning(f"重排序失败: {e}")
            return self._fallback_ranking(candidates, top_n)

    async def _compute_scores_batch(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int,
    ) -> list[float]:
        """分批计算相关性分数。

        Args:
            pairs: query-document 对列表
            batch_size: 批处理大小

        Returns:
            分数列表
        """
        import asyncio

        scores = []

        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]

            # 在后台线程中执行模型推理
            loop = asyncio.get_event_loop()
            batch_scores = await loop.run_in_executor(None, self._model.predict, batch)
            scores.extend(batch_scores)

        return scores

    def _fallback_ranking(
        self,
        candidates: list[dict[str, Any]],
        top_n: int,
    ) -> list[RankedResult]:
        """模型不可用时的回退排序。

        使用初始分数作为重排序分数。
        """
        results = []
        for c in candidates[:top_n]:
            initial_score = c.get("score", 0.0)
            results.append(
                RankedResult(
                    id=c.get("id", ""),
                    content=c.get("content", ""),
                    initial_score=initial_score,
                    rerank_score=initial_score,  # 使用初始分数
                    source=c.get("source", ""),
                    level=c.get("level", ""),
                    metadata=c.get("metadata", {}),
                )
            )
        return results


class NoOpReranker:
    """空重排序器。

    用于禁用重排序的场景。
    """

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        batch_size: int = 8,
    ) -> list[RankedResult]:
        """直接返回前 N 个候选结果。"""
        results = []
        for c in candidates[:top_n]:
            score = c.get("score", 0.0)
            results.append(
                RankedResult(
                    id=c.get("id", ""),
                    content=c.get("content", ""),
                    initial_score=score,
                    rerank_score=score,
                    source=c.get("source", ""),
                    level=c.get("level", ""),
                    metadata=c.get("metadata", {}),
                )
            )
        return results

    @property
    def is_available(self) -> bool:
        """始终可用。"""
        return True
