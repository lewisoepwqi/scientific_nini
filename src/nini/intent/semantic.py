"""意图语义分析 —— 基于 Embedding 的检索增强。

提供基于向量相似度的意图匹配，与规则版融合使用。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入 embedding 依赖
try:
    import numpy as np
    from numpy.typing import NDArray
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore
    NDArray = Any


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if not NUMPY_AVAILABLE:
        # 纯 Python 实现（较慢，但无依赖）
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    # NumPy 实现（更快）
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


@dataclass
class EmbeddingConfig:
    """Embedding 配置。"""
    model: str = "text-embedding-3-small"
    vector_dim: int = 1536  # OpenAI text-embedding-3-small
    cache_dir: Path | None = None
    
    def __post_init__(self):
        if self.cache_dir is None:
            from nini.config import settings
            self.cache_dir = settings.data_dir / "intent_embeddings"


class SimpleEmbeddingProvider:
    """简单 Embedding 提供器。
    
    优先使用 OpenAI API，回退到本地模型或简单词袋模型。
    """
    
    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()
        self._client: Any = None
        self._local_model: Any = None
        self._available: bool | None = None
    
    @property
    def is_available(self) -> bool:
        """检查 embedding 服务是否可用。"""
        if self._available is not None:
            return self._available
        
        # 尝试 OpenAI
        if self._get_openai_client():
            self._available = True
            return True
        
        # 尝试本地模型
        if self._get_local_model():
            self._available = True
            return True
        
        self._available = False
        return False
    
    def _get_openai_client(self) -> Any | None:
        """获取 OpenAI 客户端。"""
        if self._client:
            return self._client
        
        from nini.config import settings
        if not settings.openai_api_key:
            return None
        
        try:
            import openai
            self._client = openai.OpenAI(api_key=settings.openai_api_key)
            return self._client
        except Exception as exc:
            logger.debug("OpenAI 客户端初始化失败: %s", exc)
            return None
    
    def _get_local_model(self) -> Any | None:
        """获取本地 embedding 模型。"""
        if self._local_model:
            return self._local_model
        
        try:
            # 尝试使用 sentence-transformers
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("本地 embedding 模型加载成功")
            return self._local_model
        except ImportError:
            logger.debug("sentence-transformers 未安装，跳过本地模型")
        except Exception as exc:
            logger.debug("本地模型加载失败: %s", exc)
        
        return None
    
    def embed(self, text: str) -> list[float] | None:
        """获取文本的 embedding 向量。
        
        Args:
            text: 输入文本
            
        Returns:
            embedding 向量，失败返回 None
        """
        # 尝试 OpenAI
        client = self._get_openai_client()
        if client:
            try:
                resp = client.embeddings.create(
                    model=self.config.model,
                    input=text[:8000],  # 限制长度
                )
                return resp.data[0].embedding
            except Exception as exc:
                logger.debug("OpenAI embedding 失败: %s", exc)
        
        # 尝试本地模型
        local_model = self._get_local_model()
        if local_model:
            try:
                embedding = local_model.encode(text)
                return embedding.tolist()
            except Exception as exc:
                logger.debug("本地 embedding 失败: %s", exc)
        
        return None
    
    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """批量获取 embedding。"""
        # 尝试 OpenAI（支持批量）
        client = self._get_openai_client()
        if client:
            try:
                trimmed = [t[:8000] for t in texts]
                resp = client.embeddings.create(
                    model=self.config.model,
                    input=trimmed,
                )
                # 按索引排序
                embeddings = [None] * len(texts)
                for item in resp.data:
                    embeddings[item.index] = item.embedding
                return embeddings
            except Exception as exc:
                logger.debug("OpenAI 批量 embedding 失败: %s", exc)
        
        # 回退到逐个处理
        return [self.embed(t) for t in texts]


class SemanticIntentMatcher:
    """语义意图匹配器。
    
    使用向量相似度计算查询与 capability/skill 的语义匹配分数。
    支持 embedding 缓存以提高性能。
    """
    
    def __init__(self, provider: SimpleEmbeddingProvider | None = None) -> None:
        self.provider = provider or SimpleEmbeddingProvider()
        self._cache: dict[str, list[float]] = {}
        self._cache_file: Path | None = None
        self._load_cache()
    
    def _load_cache(self) -> None:
        """加载 embedding 缓存。"""
        cache_dir = self.provider.config.cache_dir
        if cache_dir is None:
            return
        
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = cache_dir / "embeddings.json"
        
        if self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text(encoding="utf-8"))
                # 验证向量维度
                for key, vec in data.items():
                    if isinstance(vec, list) and len(vec) > 0:
                        self._cache[key] = vec
                logger.debug("加载 embedding 缓存: %d 条", len(self._cache))
            except Exception as exc:
                logger.debug("加载缓存失败: %s", exc)
    
    def _save_cache(self) -> None:
        """保存 embedding 缓存。"""
        if self._cache_file is None:
            return
        
        try:
            self._cache_file.write_text(
                json.dumps(self._cache, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as exc:
            logger.debug("保存缓存失败: %s", exc)
    
    def _make_cache_key(self, text: str, prefix: str = "") -> str:
        """生成缓存键。"""
        content = f"{prefix}:{text}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_embedding(self, text: str, cache_prefix: str = "") -> list[float] | None:
        """获取文本的 embedding（带缓存）。"""
        cache_key = self._make_cache_key(text, cache_prefix)
        
        # 检查缓存
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # 计算 embedding
        embedding = self.provider.embed(text)
        if embedding:
            self._cache[cache_key] = embedding
            self._save_cache()
        
        return embedding
    
    def match_capabilities(
        self,
        query: str,
        capabilities: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """语义匹配 capability。
        
        Args:
            query: 用户查询
            capabilities: capability 列表
            top_k: 返回前 k 个
            
        Returns:
            (capability_name, similarity_score) 列表
        """
        if not self.provider.is_available:
            return []
        
        query_emb = self.get_embedding(query, "query")
        if query_emb is None:
            return []
        
        scores: list[tuple[str, float]] = []
        
        for cap in capabilities:
            name = str(cap.get("name", ""))
            display = str(cap.get("display_name", ""))
            desc = str(cap.get("description", ""))
            
            # 构建 capability 的文本表示
            cap_text = f"{display or name}: {desc}"
            cap_emb = self.get_embedding(cap_text, f"cap:{name}")
            
            if cap_emb:
                sim = cosine_similarity(query_emb, cap_emb)
                scores.append((name, sim))
        
        # 排序并返回前 k
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def match_skills(
        self,
        query: str,
        skills: list[dict[str, Any]],
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """语义匹配 skill。
        
        Args:
            query: 用户查询
            skills: skill 列表
            top_k: 返回前 k 个
            
        Returns:
            (skill_name, similarity_score) 列表
        """
        if not self.provider.is_available:
            return []
        
        query_emb = self.get_embedding(query, "query")
        if query_emb is None:
            return []
        
        scores: list[tuple[str, float]] = []
        
        for skill in skills:
            name = str(skill.get("name", ""))
            desc = str(skill.get("description", ""))
            aliases = skill.get("aliases", [])
            
            # 构建 skill 的文本表示
            alias_text = ", ".join(aliases) if isinstance(aliases, list) else ""
            skill_text = f"{name} {alias_text}: {desc}"
            skill_emb = self.get_embedding(skill_text, f"skill:{name}")
            
            if skill_emb:
                sim = cosine_similarity(query_emb, skill_emb)
                scores.append((name, sim))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def normalize_similarity_score(similarity: float, method: str = "sigmoid") -> float:
    """将余弦相似度归一化为 0-10 的分数。
    
    Args:
        similarity: 余弦相似度 [-1, 1]
        method: 归一化方法
        
    Returns:
        归一化分数 [0, 10]
    """
    # 将 [-1, 1] 映射到 [0, 1]
    normalized = (similarity + 1) / 2
    
    if method == "linear":
        return normalized * 10
    elif method == "sigmoid":
        # 使用 sigmoid 增强区分度
        import math
        # 将 0.5 映射到 5，让 0.7 接近 8，0.9 接近 10
        sigmoid = 1 / (1 + math.exp(-10 * (normalized - 0.5)))
        return sigmoid * 10
    else:
        return normalized * 10
