# Nini 2.0 新特性指南

本文档介绍 Nini 2.0 版本引入的三大核心新特性：成本透明化、可解释性增强和知识检索。

## 1. 成本透明化

### 功能概述

成本透明化功能帮助用户追踪和分析 AI 模型的使用成本，包括 Token 消耗统计、成本计算和模型使用分析。

### 主要功能

#### 1.1 Token 使用统计
- 按会话统计输入/输出 Token 数量
- 按模型细分使用情况
- 支持多模型成本对比

#### 1.2 成本计算
- 自动计算 USD 和 CNY 两种货币成本
- 基于实时汇率转换
- 支持自定义模型定价配置

#### 1.3 成本预警
- 昂贵模型选择时显示警告
- 会话列表显示成本统计
- 聚合成本摘要展示

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/cost/session/{id}` | GET | 获取指定会话的成本统计 |
| `/api/cost/sessions` | GET | 获取所有会话成本列表 |
| `/api/cost/pricing` | GET | 获取模型定价配置 |

### 前端组件

- **CostPanel**: 侧边栏成本显示面板
- **CostChart**: Token 使用趋势图表
- **ModelSelector**: 扩展显示模型定价层级

### 配置说明

模型定价配置位于 `src/nini/config/pricing.yaml`：

```yaml
models:
  "gpt-4o":
    input_price: 0.0025    # USD per 1K tokens
    output_price: 0.01     # USD per 1K tokens
    currency: "USD"
    tier: "premium"

pricing:
  usd_to_cny_rate: 7.2     # 汇率配置
```

## 2. 可解释性增强

### 功能概述

可解释性增强功能让 Agent 的决策过程更加透明，用户可以查看 AI 的分析思路、决策理由和置信度评估。

### 主要功能

#### 2.1 推理过程展示
- 显示 Agent 的分析步骤
- 展示决策理由和依据
- 高亮关键决策点

#### 2.2 推理链追踪
- 多步骤推理的链式展示
- 父子关系追踪
- 时间线视图

#### 2.3 推理类型分类
- **analysis**: 分析类型
- **decision**: 决策类型
- **planning**: 规划类型
- **reflection**: 反思类型

#### 2.4 置信度评分
- 自动计算推理置信度
- 低置信度时显示提示
- 多维度评估

### 前端组件

- **ReasoningPanel**: 推理过程展示面板（可折叠）
- **ReasoningTimeline**: 推理时间线视图
- **DecisionTag**: 决策标签高亮

### 使用示例

```python
from nini.agent.events import create_reasoning_event

# 创建推理事件
event = create_reasoning_event(
    step="method_selection",
    thought="选择 ANOVA 进行多组比较",
    rationale="数据包含3个分组，适合使用方差分析",
    reasoning_type="decision",
    confidence=0.9,
    alternatives=["t-test", "Kruskal-Wallis"]
)
```

### 复制与导出

- **复制分析思路**: 一键复制推理内容到剪贴板
- **导出到报告**: 将推理过程保存到会话报告

## 3. 知识检索

### 功能概述

知识检索功能提供 RAG（检索增强生成）能力，结合向量检索和关键词匹配，自动将相关知识注入到 Agent 上下文中。

### 主要功能

#### 3.1 混合检索
- 向量语义检索 + 关键词匹配
- 加权融合排序
- 智能结果去重

#### 3.2 领域增强
- 基于研究画像的领域偏好
- 动态 relevance score 调整
- 个性化排序

#### 3.3 上下文注入
- 自动知识注入到系统提示词
- Token 限制管理（默认 2000 tokens）
- 引用标记生成

#### 3.4 知识库管理
- 文档上传/删除
- 索引状态监控
- 支持多种文件格式

### API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/knowledge/search` | POST | 知识库搜索 |
| `/api/knowledge/documents` | GET | 获取文档列表 |
| `/api/knowledge/documents` | POST | 上传文档 |
| `/api/knowledge/documents/{id}` | DELETE | 删除文档 |
| `/api/knowledge/context` | POST | 获取知识上下文 |

### 前端组件

- **KnowledgePanel**: 知识库管理面板
- **DocumentList**: 文档列表展示
- **CitationMarker**: 引用标记渲染
- **CitationPanel**: 引用详情面板

### 使用示例

```python
from nini.knowledge.hybrid_retriever import get_hybrid_retriever

# 获取检索器
retriever = await get_hybrid_retriever()

# 执行搜索
result = await retriever.search(
    query="统计分析方法",
    top_k=5,
    domain="biology"
)

# 处理结果
for doc in result.results:
    print(f"{doc.title}: {doc.relevance_score}")
```

### 上下文注入示例

```python
from nini.knowledge.context_injector import inject_knowledge_to_prompt

# 注入知识到提示词
enhanced_prompt, context = await inject_knowledge_to_prompt(
    query="用户问题",
    system_prompt="原始系统提示",
    domain="biology",  # 领域偏好
    research_profile={"research_domains": ["genomics"]}
)
```

## 4. 配置参考

### 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `NINI_ENABLE_COST_TRACKING` | `true` | 启用成本追踪 |
| `NINI_ENABLE_REASONING` | `true` | 启用推理展示 |
| `NINI_ENABLE_KNOWLEDGE` | `true` | 启用知识检索 |
| `NINI_KNOWLEDGE_MAX_TOKENS` | `2000` | 知识上下文最大 tokens |
| `NINI_KNOWLEDGE_TOP_K` | `5` | 默认检索结果数量 |

### 目录结构

```
data/
├── sessions/           # 会话数据
├── knowledge/          # 知识库文件
│   └── vector_store/   # 向量索引存储
└── profiles/           # 研究画像
```

## 5. 故障排除

### 成本追踪不工作
- 检查 `pricing.yaml` 配置是否正确
- 确认 `token_counter.py` 正常工作
- 查看日志中的错误信息

### 知识检索无结果
- 确认 llama-index 已安装
- 检查知识目录是否有文件
- 查看向量索引构建日志

### 推理不显示
- 确认 Agent 事件正确发送
- 检查前端组件是否正确渲染
- 验证 reasoning_type 字段

## 6. 最佳实践

1. **成本优化**: 定期审查模型使用情况，选择性价比合适的模型
2. **知识管理**: 保持知识库更新，删除过期文档
3. **推理分析**: 关注低置信度的决策，考虑人工复核
4. **领域配置**: 配置准确的研究领域以获得更好的知识检索效果
