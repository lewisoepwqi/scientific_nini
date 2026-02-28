## Context

根据 Nini 2.0 架构审计报告，项目已实现 85% 的核心愿景。剩余的 15% 主要集中在三个 P1 级别功能：成本透明化（40%）、可解释性增强（70%）、知识检索集成（60%）。

当前状态：
- **后端**: `token_counter.py` 已存在但 API 未暴露；`knowledge/vector_store.py` 已存在但未集成到 Agent；`events.py` 已定义 REASONING 事件
- **前端**: Store 管理状态，组件架构支持扩展，但成本面板和推理时间线尚未实现
- **API**: 需要新增 `/api/cost/*` 和 `/api/knowledge/*` 端点

## Goals / Non-Goals

**Goals:**
1. 完成成本透明化：实时 Token 展示、历史统计、模型成本对比
2. 完成可解释性增强：推理链可视化、分析思路时间线、决策依据展示
3. 完成知识检索集成：混合检索、引用展示、知识库管理界面
4. 确保新增功能测试覆盖率达到 80%+

**Non-Goals:**
- 不修改现有核心 Agent 循环逻辑（仅扩展事件和上下文）
- 不引入新的外部依赖（使用现有技术栈）
- 不实现复杂的定价策略（使用简单线性定价模型）
- 不实现知识库的分布式扩展（保持本地存储）

## Decisions

### Decision 1: Token 统计存储方案
**选择**: 扩展 `SessionData` 模型，将 token 统计存储在会话元数据中

**理由**:
- 与会话生命周期绑定，自然持久化
- 利用现有会话存储机制，无需新建表
- 方便在会话列表中展示历史统计

**替代方案**:
- 独立数据库存表：增加复杂性，需要额外迁移
- 内存缓存：无法持久化，重启后丢失

### Decision 2: 成本计算模型
**选择**: 使用配置文件定义模型定价，计算公式：(input_tokens * input_price + output_tokens * output_price) / 1000

**理由**:
- 简单可维护，易于更新价格
- 支持多模型差异化定价
- 当前不需要复杂的分层定价

**定价示例** (CNY per 1K tokens):
```yaml
models:
  gpt-4o:
    input: 0.03
    output: 0.06
  claude-sonnet:
    input: 0.02
    output: 0.10
  # ... 其他模型
```

### Decision 3: 推理事件增强策略
**选择**: 向后兼容的方式扩展 REASONING 事件，可选字段不破坏现有解析

**理由**:
- 现有事件格式需要保持兼容
- 新增字段（reasoning_type, confidence_score）为可选
- 前端 gracefully degrade，不报错

**事件结构**:
```typescript
interface ReasoningEvent {
  type: 'reasoning';
  content: string;              // 原有字段
  reasoning_type?: 'analysis' | 'decision' | 'planning' | 'reflection';
  confidence_score?: number;    // 0.0 - 1.0
  key_decisions?: string[];
  parent_id?: string;           // 用于链式关联
}
```

### Decision 4: 混合检索排名算法
**选择**: 加权组合：combined_score = 0.7 * vector_score + 0.3 * keyword_score

**理由**:
- 向量检索提供语义理解，权重更高
- 关键词检索确保精确匹配也能被召回
- 权重可配置，便于后续调优

**替代方案**:
- RRF (Reciprocal Rank Fusion): 更复杂，当前不需要
- 纯向量检索：关键词匹配效果差

### Decision 5: 知识引用标注方案
**选择**: 后端在上下文中标注来源，前端解析并渲染引用标记

**理由**:
- 不修改 LLM 输出格式，避免影响模型表现
- 在 prompt 中指示模型使用 [1], [2] 格式引用
- 前端通过正则解析引用标记并链接到来源

**Prompt 模板**:
```
当使用知识库信息时，请在相关语句后添加引用标记，格式为 [1], [2]。
知识来源：
[1] {document_title}: {excerpt}
[2] {document_title}: {excerpt}
```

### Decision 6: 组件集成位置
**选择**:
- CostPanel: ChatPanel 侧边栏，可折叠
- ReasoningTimeline: MessageBubble 内嵌，作为 REASONING 事件的渲染器
- KnowledgePanel: 新增独立面板，通过侧边栏导航访问

**理由**:
- 成本信息需要全局可见，侧边栏合适
- 推理时间线与特定消息关联，内嵌渲染自然
- 知识库管理使用频率较低，独立面板不占用主界面

## Architecture

### 成本透明化架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (React)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ CostPanel   │  │ CostChart   │  │ ModelCostIndicator  │  │
│  │ (侧边栏)     │  │ (折线图)     │  │ (模型选择器提示)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ /api/cost/* │  │ TokenCounter│  │ ModelPricingConfig  │  │
│  │   Routes    │  │   Service   │  │      (YAML)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 可解释性增强架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (React)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ ReasoningPanel  │  │ ReasoningTimeline│  │ DecisionTag │  │
│  │ (可折叠面板)     │  │ (时间线组件)     │  │ (决策高亮)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                        │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ ReasoningEvent  │  │ Agent Callback  │                   │
│  │   (扩展结构)     │  │   (事件推送)     │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 知识检索集成架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (React)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ KnowledgePanel  │  │ CitationMarker  │  │ DocumentList│  │
│  │ (知识库管理)     │  │ (引用标记)       │  │ (文档列表)   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ /api/knowledge/*│  │ HybridRetriever │  │ Knowledge   │  │
│  │     Routes      │  │ (混合检索)       │  │  Context    │  │
│  └─────────────────┘  └─────────────────┘  │  Injector   │  │
│                                            └─────────────┘  │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ VectorStore     │  │ KeywordIndex    │                   │
│  │ (已有)          │  │ (TF-IDF/简单匹配) │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

## Data Models

### TokenUsage (新增)
```python
class TokenUsage(BaseModel):
    session_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_cny: float
    model_breakdown: dict[str, ModelTokenUsage]
    created_at: datetime
    updated_at: datetime

class ModelTokenUsage(BaseModel):
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_cny: float
```

### ReasoningEvent (扩展)
```python
class ReasoningEventData(BaseModel):
    type: Literal["reasoning"]
    content: str
    reasoning_type: Optional[Literal["analysis", "decision", "planning", "reflection"]]
    confidence_score: Optional[float]  # 0.0 - 1.0
    key_decisions: Optional[list[str]]
    parent_id: Optional[str]
    timestamp: datetime
```

### KnowledgeSearchResult (新增)
```python
class KnowledgeSearchResult(BaseModel):
    query: str
    results: list[KnowledgeDocument]
    total_count: int
    search_method: Literal["vector", "keyword", "hybrid"]

class KnowledgeDocument(BaseModel):
    id: str
    title: str
    content: str
    excerpt: str
    relevance_score: float
    source_method: Literal["vector", "keyword"]
    metadata: dict
```

## API Endpoints

### Cost Transparency
```
GET  /api/cost/session/{session_id}     # 获取会话 Token 统计
GET  /api/cost/sessions                 # 获取所有会话成本列表
GET  /api/cost/pricing                  # 获取模型定价配置
```

### Knowledge Retrieval
```
POST   /api/knowledge/search            # 搜索知识库
GET    /api/knowledge/documents         # 获取文档列表
POST   /api/knowledge/documents         # 上传文档
DELETE /api/knowledge/documents/{id}    # 删除文档
```

## Risks / Trade-offs

**[风险] 成本估算不准确** → **缓解**: 使用近似定价，在 UI 中明确标注"预估费用"

**[风险] 知识检索增加延迟** → **缓解**: 异步检索、缓存热门查询、设置超时 fallback

**[风险] 推理事件过多影响性能** → **缓解**: 前端虚拟滚动、限制显示数量、可配置过滤

**[风险] Token 统计遗漏** → **缓解**: 在 AgentRunner 的统一回调点统计，确保所有 LLM 调用都被记录

**[权衡] 知识库规模限制** → 当前设计假设知识库规模 < 1000 文档，使用本地向量存储。如需扩展，需要迁移到专用向量数据库。

## Migration Plan

### 部署步骤
1. 后端部署：新增 API 端点，扩展事件结构（向后兼容）
2. 数据库：无需迁移（使用现有会话存储）
3. 前端部署：新增组件，渐进式启用功能
4. 配置更新：添加 `model_pricing.yaml` 配置文件

### 回滚策略
- 后端：新旧 API 共存，可通过配置开关回滚
- 前端：功能开关控制，可独立禁用各模块
- 数据：不修改现有数据结构，无回滚风险

## Open Questions

1. **模型定价更新频率**：是否需要支持动态定价更新？建议初始版本使用配置文件，后续可扩展为 API 拉取。

2. **知识库权限模型**：当前设计假设单用户知识库，是否需要支持多用户/共享知识库？建议 Phase 1 保持简单。

3. **推理事件存储**：是否需要持久化推理事件供后续分析？建议仅在前端展示，不持久化以减少存储压力。

4. **成本警告阈值**："显著更高成本"的阈值如何定义？建议配置化，默认 2x 基准模型价格。
