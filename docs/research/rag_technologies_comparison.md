# 先进 RAG 技术方案对比分析报告

> 调研日期：2026-03-02
> 调研目标：对比分析 GraphRAG、RAPTOR、Self-RAG、混合检索策略与 PageIndex 的技术特点

## 目录

1. [技术方案概览](#1-技术方案概览)
2. [各技术方案核心原理](#2-各技术方案核心原理)
   - 2.1 [GraphRAG](#21-graphrag)
   - 2.2 [RAPTOR](#22-raptor)
   - 2.3 [Self-RAG](#23-self-rag)
   - 2.4 [混合检索策略](#24-混合检索策略)
   - 2.5 [PageIndex](#25-pageindex)
3. [优缺点对比表格](#3-优缺点对比表格)
4. [适用场景分析](#4-适用场景分析)
5. [对 nini 项目的借鉴意义](#5-对-nini-项目的借鉴意义)
6. [参考资源](#6-参考资源)

---

## 1. 技术方案概览

| 技术方案 | 核心思想 | 发布时间 | 主要贡献者 |
|---------|---------|---------|-----------|
| **GraphRAG** | 知识图谱 + 向量检索融合 | 2024年7月 | Microsoft Research |
| **RAPTOR** | 递归摘要构建树状索引 | 2024年(ICLR) | Stanford University |
| **Self-RAG** | 模型自主决定何时检索 | 2024年(ICLR) | Asai et al. |
| **混合检索** | BM25 + 向量 + 重排序 | 持续演进 | 业界标准实践 |
| **PageIndex** | 无向量树形推理检索 | 2024年 | VectifyAI |

---

## 2. 各技术方案核心原理

### 2.1 GraphRAG

#### 核心思想

GraphRAG 将传统 RAG 的"文本向量片段"升级为"实体-关系-属性三元组"的知识图谱表示，通过图遍历实现多跳推理和跨文档关联。

#### 技术架构

```
┌─────────────────────────────────────────┐
│           非结构化文本输入               │
├─────────────────────────────────────────┤
│  1. 知识图谱构建（LLM驱动实体关系抽取）   │
│     - 实体识别（节点）                   │
│     - 关系抽取（边）                     │
│     - 属性提取                           │
├─────────────────────────────────────────┤
│  2. 社区检测与分层摘要                   │
│     - 快速标签传播算法                   │
│     - 多层次社区结构                     │
│     - 社区摘要生成                       │
├─────────────────────────────────────────┤
│  3. 混合检索与生成                       │
│     - 向量搜索定位相关节点               │
│     - 图遍历扩展关联信息                 │
│     - 社区摘要提供全局上下文             │
└─────────────────────────────────────────┘
```

#### 关键创新点

1. **知识图谱构建**：使用 LLM 自动从非结构化文本中提取实体、关系和属性
2. **社区检测**：通过 Leiden 等算法识别知识图谱中的社区结构
3. **分层摘要**：为每个社区生成多层次的语义摘要
4. **混合检索**：结合向量相似度和图遍历的检索方式

#### 优势与局限

| 优势 | 局限 |
|-----|-----|
| 支持复杂多跳推理 | 索引构建成本高（时间+计算资源） |
| 跨文档信息关联 | 需要高质量的关系抽取 |
| 可解释性强（可追溯关系路径） | 对小型文档集效果不明显 |
| 全局理解能力（社区摘要） | 图存储和查询复杂度较高 |

---

### 2.2 RAPTOR

#### 核心思想

RAPTOR（Recursive Abstractive Processing for Tree-Organized Retrieval）通过递归摘要构建树状索引结构，使检索系统能够同时获取细粒度细节和高层语义主题。

#### 技术架构

```
文档文本
    ↓
分块（~100 tokens，叶节点）
    ↓
嵌入 + GMM 聚类
    ↓
LLM 摘要生成（父节点）
    ↓
递归直至根节点
```

#### 树构建流程

| 步骤 | 说明 |
|------|-----|
| 1. 分块 | 文档切分为约 100 tokens 的文本块（叶节点） |
| 2. 嵌入 | 使用 SBERT 生成文本块向量表示 |
| 3. 聚类 | 使用 GMM（高斯混合模型）进行软聚类 |
| 4. 摘要 | LLM 为每个聚类生成摘要 |
| 5. 递归 | 对摘要重复上述过程，直至形成单根节点 |

#### 检索策略

1. **树遍历（Tree Traversal）**：从根节点逐层向下导航
2. **折叠树（Collapsed Tree）**：扁平化树结构，跨所有层次检索（效果更好）

#### 优势与局限

| 优势 | 局限 |
|-----|-----|
| 多层次抽象（细节+主题） | 内存和计算资源消耗大 |
| 软聚类允许跨层次关联 | 递归摘要成本高（token 消耗） |
| 擅长长文档和多跳问答 | 树深度和分支数需要调参 |
| 20% 绝对准确率提升（QuALITY 基准） | 对短文档 overhead 过大 |

---

### 2.3 Self-RAG

#### 核心思想

Self-RAG 通过引入特殊的**反思令牌（reflection tokens）**，让 LLM 在生成过程中动态决定何时检索、如何评估检索结果质量，实现自适应检索。

#### 反思令牌体系

| 令牌类型 | 用途 |
|---------|-----|
| `[Retrieve]` | 决定是否检索（yes/no/continue） |
| `[ISREL]` | 评估检索段落的相关性 |
| `[ISSUP]` | 评估生成内容的 factual 支持度 |
| `[ISUSE]` | 评估生成内容的整体效用 |

#### 工作流程

```
用户查询
    ↓
生成 [Retrieve] 令牌
    ↓
    ├─ 无需检索 → 直接生成
    └─ 需要检索 → 检索相关段落
                    ↓
              生成内容 + [ISREL] 评估
                    ↓
              生成内容 + [ISSUP] 评估
                    ↓
              生成内容 + [ISUSE] 评估
                    ↓
              自适应推理输出
```

#### 优势与局限

| 优势 | 局限 |
|-----|-----|
| 按需检索，避免不必要开销 | 需要专门训练或微调模型 |
| 任务自适应（事实性任务检索多，创意任务检索少） | 反思令牌增加生成复杂度 |
| 端到端训练，统一框架 | 训练数据构建成本高 |
| 可控的检索频率（阈值调节） | 延迟可能增加（迭代生成） |

---

### 2.4 混合检索策略

#### 核心思想

结合稀疏检索（BM25）和稠密检索（向量相似度）的优势，通过融合算法和重排序提升检索质量。

#### 三层架构

```
┌─────────────────────────────────────────┐
│  第一层：多路召回 (Multi-Source Retrieval) │
│  ├── BM25 (Sparse) - 关键词/精确匹配      │
│  └── Dense Vector (KNN) - 语义相似度      │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│  第二层：融合排序 (Fusion)               │
│  └── RRF (Reciprocal Rank Fusion)       │
│      基于排名而非绝对分数融合结果          │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│  第三层：重排序 (Reranking)              │
│  └── Cross-Encoder / BGE-Reranker       │
│      精准打分，提升 Top-K 准确率          │
└─────────────────────────────────────────┘
```

#### 关键组件

**BM25（稀疏检索）**
- 基于概率模型的词频-逆文档频率算法
- 优势：精确匹配、速度快（~50ms）、对关键词/数字敏感
- 局限：无法理解语义相似性

**向量检索（稠密检索）**
- 使用 BGE-M3、OpenAI embedding 等模型
- 优势：语义理解、跨语言、同义词召回
- 局限：对精确匹配效果差

**RRF 融合算法**
```
RRF(d) = Σ(1 / (k + r_i(d)))
```
其中 r_i(d) 是文档 d 在第 i 个列表中的排名，k 为常数（通常 60）

**重排序（Reranking）**
- 使用 Cross-Encoder（如 BGE-Reranker）进行精细打分
- 在 Bi-Encoder 召回的 Top-K 结果上进行精确排序
- Top-1 准确率可提升 20%+

#### 优势与局限

| 优势 | 局限 |
|-----|-----|
| 兼顾精确匹配和语义理解 | 系统复杂度增加 |
| 模块化设计，组件可替换 | 需要维护多个索引 |
| 业界验证的成熟方案 | 融合参数需要调优 |
| 延迟可接受（~100-200ms） | 重排序增加计算开销 |

---

### 2.5 PageIndex

#### 核心思想

PageIndex 是一种**无向量、无分块**的推理型 RAG 框架，通过构建树形文档索引，让 LLM 像人类专家一样"导航"文档结构进行检索。

#### 技术架构

```json
{
  "title": "章节标题",
  "node_id": "唯一标识",
  "start_index": 起始页码,
  "end_index": 结束页码,
  "summary": "节点级语义摘要",
  "nodes": [子节点列表]
}
```

#### 检索机制：基于推理的树搜索

```
用户查询
    ↓
LLM 分析顶层摘要 → 选择最相关分支
    ↓
逐层向下推理筛选 → 定位具体节点
    ↓
加载目标段落 → 生成答案
```

#### 核心特点

1. **保留文档结构**：尊重原始文档的章节层次，而非强制分块
2. **节点级摘要**：每个节点包含语义摘要，支持快速筛选
3. **页面精确映射**：支持精确定位到具体页面范围
4. **推理路径可追溯**：可展示 LLM 的检索决策过程

#### 优势与局限

| 优势 | 局限 |
|-----|-----|
| 无需向量数据库，存储成本低 | 查询延迟较高（0.5-3秒） |
| FinanceBench 准确率 98.7% | 仅适用于结构化文档 |
| 答案溯源准确率高 | 对无章节标记的文档效果差 |
| 多跳问答召回率提升 15-25% | 单次查询成本较高（~$0.02） |

---

## 3. 优缺点对比表格

### 3.1 核心技术对比

| 维度 | GraphRAG | RAPTOR | Self-RAG | 混合检索 | PageIndex |
|-----|----------|--------|----------|---------|-----------|
| **核心数据结构** | 知识图谱 | 树状索引 | 反思令牌 | 向量+倒排索引 | 树形文档结构 |
| **检索方式** | 图遍历+向量 | 树遍历/折叠 | 自适应触发 | 相似度+关键词 | 推理导航 |
| **是否需要向量** | 是 | 是 | 可选 | 是 | 否 |
| **索引构建成本** | 高 | 中 | 低 | 低 | 中 |
| **查询延迟** | 中 | 中 | 可变 | 低 | 高 |
| **可解释性** | 高（关系路径） | 中（树路径） | 高（反思令牌） | 低 | 高（推理路径） |
| **多跳推理** | 强 | 中 | 中 | 弱 | 中 |

### 3.2 性能对比

| 指标 | GraphRAG | RAPTOR | Self-RAG | 混合检索 | PageIndex |
|-----|----------|--------|----------|---------|-----------|
| **准确率提升** | 显著（全局问题） | +20%（QuALITY） | 任务自适应 | +10-15% | +13.5%（溯源） |
| **召回率** | 高（跨文档） | 高（多层次） | 中 | 高 | 高（结构化） |
| **计算开销** | 高 | 高 | 中 | 低 | 中 |
| **存储开销** | 高（图存储） | 中 | 低 | 中 | 低（JSON） |

### 3.3 工程实现对比

| 维度 | GraphRAG | RAPTOR | Self-RAG | 混合检索 | PageIndex |
|-----|----------|--------|----------|---------|-----------|
| **开源实现** | 是（微软） | 是（斯坦福） | 是 | 多（LlamaIndex等） | 是（VectifyAI） |
| **部署复杂度** | 高 | 中 | 中 | 低 | 低 |
| **依赖组件** | 图数据库+向量库 | 向量库+LLM | 需训练/微调 | 向量库+搜索引擎 | 仅需 LLM |
| **领域适应性** | 通用 | 通用 | 通用 | 通用 | 结构化文档 |

---

## 4. 适用场景分析

### 4.1 场景匹配矩阵

| 应用场景 | 推荐方案 | 理由 |
|---------|---------|-----|
| **企业知识库（复杂文档）** | GraphRAG | 跨文档关联、组织架构理解 |
| **长文档问答（论文/报告）** | RAPTOR | 多层次抽象、长上下文处理 |
| **实时问答系统** | 混合检索 | 低延迟、高吞吐 |
| **资源受限环境** | PageIndex | 无需向量数据库 |
| **创意写作/开放域** | Self-RAG | 自适应检索，避免过度检索 |
| **法律/金融文档** | PageIndex | 结构化文档、精确溯源 |
| **多跳推理问答** | GraphRAG | 关系遍历、复杂推理 |
| **通用 RAG 应用** | 混合检索 | 平衡性能与成本 |

### 4.2 各方案最佳适用场景

#### GraphRAG 最佳场景
- 企业组织架构查询
- 法律文件中的案例关联
- 医疗诊断的症状-疾病-药物推理
- 金融风控中的企业关联分析
- 学术研究中的引用网络分析

#### RAPTOR 最佳场景
- 长篇技术文档理解
- 多章节报告的综合性问答
- 需要同时关注细节和全局的问题
- 叙事性长文本（小说、传记）分析

#### Self-RAG 最佳场景
- 混合类型任务（事实性+创意性）
- 需要精细控制检索频率的场景
- 对延迟不敏感但要求高准确率的任务
- 需要可解释检索决策的场景

#### 混合检索最佳场景
- 通用搜索引擎
- 实时客服系统
- 需要平衡成本和性能的生产环境
- 已有 BM25 或向量检索基础设施的迁移

#### PageIndex 最佳场景
- 财务报告分析
- 监管文件合规检查
- 技术手册查询
- 教科书/标准文档问答
- 需要精确页面溯源的场景

---

## 5. 对 nini 项目的借鉴意义

### 5.1 nini 项目特点分析

根据 CLAUDE.md 中的描述，nini 是一个**本地优先的科研数据分析 AI Agent**，具有以下特点：

1. **本地优先**：数据不上云，注重隐私
2. **科研数据分析**：涉及统计、作图、代码执行
3. **多技能工具**：统计、可视化、数据清洗、报告生成
4. **会话管理**：支持多轮对话、工作区管理
5. **知识库**：当前使用 RAG 向量检索

### 5.2 技术借鉴建议

#### 短期优化（1-2 个月）

**1. 引入混合检索策略**

当前 nini 的知识库检索可以升级为混合检索：

```python
# 建议架构
class HybridKnowledgeRetriever:
    def __init__(self):
        self.vector_store = VectorStore()      # 现有向量检索
        self.bm25_index = BM25Index()          # 新增 BM25
        self.reranker = BGEReranker()          # 新增重排序

    async def retrieve(self, query, top_k=10):
        # 多路召回
        vector_results = await self.vector_store.search(query, top_k=20)
        bm25_results = self.bm25_index.search(query, top_k=20)

        # RRF 融合
        fused = rrf_fusion(vector_results, bm25_results)

        # 重排序
        reranked = await self.reranker.rerank(query, fused[:top_k])
        return reranked
```

**收益**：
- 提升关键词查询（如函数名、统计术语）的召回率
- 保持语义检索能力
- 实现成本低，可复用现有向量存储

**2. 本地 BM25 实现**

考虑到 nini 是本地优先，可以引入轻量级 BM25：

```python
# src/nini/knowledge/local_bm25.py
from rank_bm25 import BM25Okapi
import json
from pathlib import Path

class LocalBM25Index:
    """本地 BM25 索引，无需外部服务"""

    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.bm25 = None
        self.documents = []

    def build(self, documents: list[str]):
        """从文档构建索引"""
        tokenized = [doc.lower().split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized)
        self.documents = documents
        self.save()

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """执行 BM25 检索"""
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[-top_k:][::-1]
        return [
            {"content": self.documents[i], "score": scores[i]}
            for i in top_indices if scores[i] > 0
        ]
```

#### 中期改进（3-6 个月）

**3. 引入 Self-RAG 思想**

nini 的 Agent 循环可以借鉴 Self-RAG 的自适应检索：

```python
# src/nini/agent/runner.py 改进建议
class AdaptiveAgentRunner:
    async def should_retrieve(self, query: str, context: dict) -> bool:
        """
        判断是否需要检索知识库
        借鉴 Self-RAG 的 [Retrieve] 令牌思想
        """
        # 简单启发式规则（初期）
        if self.is_code_related(query):
            return True  # 代码相关查询需要检索文档
        if self.is_statistical_query(query):
            return True  # 统计问题需要检索方法说明

        # 复杂判断：使用 LLM 评估
        decision = await self.llm.chat([
            {"role": "system", "content": "判断以下查询是否需要检索外部知识库"},
            {"role": "user", "content": f"查询: {query}\n已有上下文: {context}"}
        ])
        return "需要检索" in decision
```

**收益**：
- 减少不必要的检索调用
- 提升响应速度
- 降低 API 成本

**4. 针对科研场景的 RAPTOR 简化版**

科研数据分析常涉及长文档（论文、报告），可以引入简化版 RAPTOR：

```python
# src/nini/knowledge/hierarchical_index.py
class HierarchicalDocumentIndex:
    """
    简化版层次化文档索引
    针对科研论文、数据报告等结构化文档
    """

    def build_tree(self, document: str) -> DocumentNode:
        """
        基于文档结构（章节标题）构建树
        比 RAPTOR 的 GMM 聚类更简单高效
        """
        # 1. 识别章节结构（使用正则或 LLM）
        sections = self.extract_sections(document)

        # 2. 为每个章节生成摘要
        for section in sections:
            section.summary = self.summarize(section.content)

        # 3. 构建树结构
        return self.build_tree_from_sections(sections)
```

#### 长期规划（6 个月以上）

**5. GraphRAG 用于科研知识关联**

科研数据分析中，概念、方法、数据集之间存在复杂关联，可以探索 GraphRAG：

```python
# 潜在应用场景
class ResearchKnowledgeGraph:
    """
    科研知识图谱
    连接：数据集-统计方法-可视化类型-应用领域
    """

    def build_from_sessions(self, sessions: list[Session]):
        """从历史会话构建知识图谱"""
        for session in sessions:
            # 提取实体：数据集名称、统计方法、图表类型
            entities = self.extract_entities(session)
            # 建立关系：使用了、生成了、应用于
            self.add_relations(entities)
```

**6. PageIndex 用于文档解析**

nini 用户常上传研究报告、数据文档，可以借鉴 PageIndex 的文档结构解析：

```python
# src/nini/knowledge/document_parser.py
class StructuredDocumentParser:
    """
    结构化文档解析器
    保留文档原始结构，支持精确引用
    """

    def parse(self, file_path: Path) -> DocumentTree:
        """解析 PDF/Word 文档为树结构"""
        # 提取目录结构
        toc = self.extract_toc(file_path)

        # 构建节点树
        tree = DocumentTree()
        for entry in toc:
            node = DocumentNode(
                title=entry.title,
                page_range=entry.pages,
                level=entry.level
            )
            tree.add_node(node)

        return tree
```

### 5.3 实施路线图

```
Phase 1 (即刻): 混合检索
├── 引入 rank-bm25 库
├── 实现 RRF 融合算法
└── 集成到现有知识库检索

Phase 2 (1-2月): 自适应检索
├── 实现查询意图分类
├── 根据意图决定是否检索
└── 性能评估与调优

Phase 3 (3-6月): 层次化索引
├── 文档结构解析
├── 章节级摘要生成
└── 树形检索实现

Phase 4 (长期): 知识图谱
├── 科研概念抽取
├── 关系建模
└── GraphRAG 集成
```

### 5.4 预期收益

| 改进项 | 预期收益 | 优先级 |
|-------|---------|-------|
| 混合检索 | 检索准确率 +10-15% | 高 |
| 自适应检索 | API 成本 -20-30% | 高 |
| 层次化索引 | 长文档理解 +20% | 中 |
| 知识图谱 | 跨文档推理能力 | 低 |

---

## 6. 参考资源

### GraphRAG
- [Microsoft GraphRAG GitHub](https://github.com/microsoft/graphrag)
- [Microsoft Research Project Page](https://www.microsoft.com/en-us/research/project/graphrag/)
- [GraphRAG 技术解析 - 人人都是产品经理](https://www.woshipm.com/ai/6085439.html)

### RAPTOR
- [RAPTOR Paper (ICLR 2024)](https://chatpaper.com/chatpaper/paper/5959)
- [RAPTOR GitHub](https://github.com/parthsarthi03/raptor)
- [RAG Techniques - GraphRAG and RAPTOR](https://deepwiki.com/NirDiamant/RAG_Techniques/6.1-graphrag-and-raptor)

### Self-RAG
- [Self-RAG Paper (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/file/25f7be9694d7b32d5cc670927b8091e1-Paper-Conference.pdf)
- [IBM Self-RAG Tutorial](https://www.ibm.com/think/tutorials/build-self-rag-agent-langgraph-granite)
- [Adaptive Retrieval Blog Series](https://blog.reachsumit.com/posts/2025/10/learning-to-retrieve/)

### 混合检索
- [Weaviate Hybrid Search Explained](https://weaviate.io/blog/hybrid-search-explained)
- [Hybrid Retrieval Guide](https://mbrenndoerfer.com/writing/hybrid-retrieval-combining-sparse-dense-methods-effective-information-retrieval)
- [RAG 落地指南 - 掘金](https://juejin.cn/post/7594680314712834098)

### PageIndex
- [PageIndex GitHub](https://github.com/VectifyAI/PageIndex)
- [PageIndex 官方文档](https://docs.pageindex.ai/)
- [PageIndex 技术介绍](https://pageindex.ai/blog/pageindex-intro)
- [无向量 RAG 技术解析](https://post.smzdm.com/p/azzgeoqr)

---

*报告完成时间：2026-03-02*
