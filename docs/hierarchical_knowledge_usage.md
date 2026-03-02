# 层次化知识检索使用指南

## 概述

Nini 现在支持基于 PageIndex 思想的层次化知识检索，提供三级索引（文档/章节/段落）和智能查询路由。

## 启用方式

在 `.env` 文件中添加：

```bash
NINI_ENABLE_HIERARCHICAL_INDEX=true
```

## 使用方法

### 基础检索

```python
from nini.knowledge.hierarchical import create_knowledge_adapter

# 创建适配器（自动初始化）
adapter = await create_knowledge_adapter()

# 使用兼容接口检索
knowledge = await adapter.select("什么是t检验")
print(knowledge)
```

### 高级检索

```python
from nini.knowledge.hierarchical import UnifiedRetriever

# 创建统一检索器
retriever = UnifiedRetriever()
await retriever.initialize()

# 执行检索
result = await retriever.search("如何做方差分析", top_k=5)

print(result.content)  # 组装后的上下文
print(result.hits)     # 命中详情
print(result.routing_info)  # 路由信息
```

## 配置选项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_hierarchical_index` | `false` | 启用层次化索引 |
| `hierarchical_reranker_model` | `BAAI/bge-reranker-base` | Cross-Encoder 模型 |
| `hierarchical_cache_ttl` | `300` | 缓存 TTL（秒） |
| `hierarchical_chunk_size` | `256` | 段落分块大小 |
| `hierarchical_chunk_overlap` | `32` | 分块重叠大小 |
| `hierarchical_rrf_k` | `60` | RRF 融合参数 |

## 查询意图类型

系统会自动根据查询内容分类并路由到最优索引层级：

| 意图类型 | 示例查询 | 检索层级 |
|----------|----------|----------|
| concept | "什么是t检验" | L0 (文档级) |
| how-to | "如何做t检验" | L1 (章节级) |
| reference | "t检验的参数" | L2 (段落级) |
| code | "相关性分析代码" | L2 (段落级) |
| comparison | "t检验 vs 方差分析" | L0 + L1 |
| troubleshoot | "结果报错" | L1 + L2 |

## 架构说明

```
用户查询
    ↓
查询意图分类 (QueryIntentClassifier)
    ↓
查询路由 (QueryRouter) → 选择检索层级
    ↓
多路检索 (UnifiedRetriever)
    ├── L0 文档级索引
    ├── L1 章节级索引
    ├── L2 段落级索引
    └── 长期记忆 (可选)
    ↓
RRF 融合
    ↓
Cross-Encoder 重排序 (可选)
    ↓
上下文组装
    ↓
返回结果
```

## 性能优化

1. **索引缓存**: 索引构建后会持久化到磁盘，重启时自动加载
2. **查询缓存**: 相同查询结果会缓存 300 秒
3. **增量更新**: 只更新变更的文件，无需全量重建
4. **延迟初始化**: Cross-Encoder 模型按需加载

## 故障排查

### 索引构建失败

检查知识目录权限：
```bash
ls -la data/knowledge/
```

### 检索结果为空

1. 确认知识文件格式正确（Markdown）
2. 检查索引是否构建：`data/hierarchical_index/` 目录是否存在
3. 查看日志：`~/.nini/logs/nini.log`

### 内存占用过高

调整分块大小：
```bash
NINI_HIERARCHICAL_CHUNK_SIZE=512
```

## 迁移指南

从传统检索迁移：

1. 无需修改现有知识 Markdown 文件
2. 添加配置启用新功能
3. 代码层面完全兼容，无需修改调用代码

回退到传统检索：

```bash
NINI_ENABLE_HIERARCHICAL_INDEX=false
```
