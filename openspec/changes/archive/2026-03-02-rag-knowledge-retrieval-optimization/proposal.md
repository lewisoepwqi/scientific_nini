## Why

当前 Nini 知识检索系统采用文档级索引，检索粒度太粗，无法精确定位到具体方法或参数说明。基于 PageIndex 技术调研发现，层次化索引（文档/章节/段落三级）可显著提升检索精准度。在科研数据分析场景中，用户常需要快速定位特定统计方法的使用说明或参数解释，现有实现无法满足这一需求。

## What Changes

- **引入层次化知识索引**：重构知识库索引结构，支持文档级(L0)、章节级(L1)、段落级(L2)三级索引
- **实现查询意图路由**：根据查询类型（概念/方法/参考/代码）自动选择检索层级和策略
- **多路召回与融合**：并行执行 BM25、向量检索，使用 RRF 算法融合结果
- **添加结果重排序**：引入 Cross-Encoder 对 Top-K 结果进行重排序，提升相关性
- **统一检索接口**：整合知识库与长期记忆检索，提供单一入口

## Capabilities

### New Capabilities
- `hierarchical-index`: 层次化知识索引管理，支持 Markdown 文档的结构化解析和三级索引构建
- `query-intent-routing`: 查询意图分类与路由，根据查询类型选择最优检索策略
- `multi-stage-retrieval`: 多阶段检索流程，包含召回、融合、重排序、上下文组装
- `retrieval-reranking`: 检索结果重排序，使用轻量级 Cross-Encoder 提升 Top-K 质量

### Modified Capabilities
- `knowledge-retrieval`: 现有知识检索模块的需求扩展，增加层次化检索和统一接口

## Impact

**受影响代码**：
- `src/nini/knowledge/` 目录下所有模块
- `src/nini/memory/long_term_memory.py` 统一检索接口
- `src/nini/agent/runner.py` 检索调用方式

**依赖变更**：
- 新增可选依赖：`sentence-transformers` (用于 Cross-Encoder 重排序)
- 现有 BM25、向量检索依赖保持不变

**API 变更**：
- 对外提供统一的 `HierarchicalKnowledgeRetriever` 接口
- 保留向后兼容的 `KnowledgeLoader` 接口

**数据兼容性**：
- 现有知识 Markdown 文件无需修改
- 索引格式升级，支持增量重建
