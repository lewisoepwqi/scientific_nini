## Why

根据 Nini 2.0 架构审计报告，项目已实现 85% 的核心愿景，但仍有三个 P1 级别功能需要完善：成本透明化（40%）、可解释性增强（70%）、知识检索集成（60%）。这些功能的缺失影响了用户体验和系统智能程度，需要在本阶段完成以达成 Nini 2.0 100% 愿景目标。

## What Changes

### 成本透明化 (Cost Transparency)
- 前端 Token 消耗展示面板 - 实时显示当前会话的 token 使用量和预估费用
- 会话历史成本统计 - 在会话列表中展示历史会话的累计成本
- 模型成本对比提示 - 在选择模型时展示不同模型的成本差异

### 可解释性增强 (Explainability Enhancement)
- 推理链可视化组件 - 前端 REASONING 事件展示优化，支持折叠/展开和决策点高亮
- 分析思路时间线 - 以时间线形式展示 Agent 的推理过程
- 决策依据提示 - 在关键分析步骤旁显示决策理由

### 知识检索集成 (Knowledge Retrieval)
- 混合检索能力 - 集成向量检索与关键词检索，提升知识库查询效果
- 知识引用展示 - 在 Agent 回复中标注引用的知识来源
- 知识库管理界面 - 前端知识库文档上传与管理功能

### 测试覆盖完善
- 新增功能的单元测试覆盖率达到 80%+
- 端到端测试覆盖主要用户流程
- 集成测试覆盖知识检索和成本统计 API

## Capabilities

### New Capabilities
- `cost-transparency`: Token 消耗追踪与费用预估 UI，包括实时统计、历史汇总、模型成本对比
- `explainability-enhancement`: 推理链可视化与决策点高亮，包括 REASONING 事件展示优化、分析思路时间线
- `knowledge-retrieval`: 向量检索与混合检索集成，包括知识引用展示、知识库管理界面

### Modified Capabilities
- 无（本 change 仅新增 capabilities，不修改现有 spec 需求）

## Impact

### 后端代码
- `src/nini/agent/events.py`: 可能需要扩展 REASONING 事件结构
- `src/nini/knowledge/`: 集成向量检索到知识加载流程
- `src/nini/memory/token_counter.py`: 暴露 token 统计 API

### 前端代码
- `web/src/components/`: 新增 CostPanel、ReasoningTimeline、KnowledgeManager 组件
- `web/src/store.ts`: 扩展 store 以支持 cost tracking 和 knowledge retrieval 状态
- `web/src/panels/`: 新增或修改面板组件

### API 变更
- 新增 `/api/cost/session/{session_id}` - 获取会话成本统计
- 新增 `/api/knowledge/search` - 知识库检索接口
- 新增 `/api/knowledge/documents` - 知识库文档管理

### 测试
- `tests/test_cost_*.py`: 成本统计相关测试
- `tests/test_knowledge_*.py`: 知识检索相关测试
- `tests/e2e/`: 端到端测试扩展

### 依赖
- 无新增外部依赖（使用现有技术栈实现）
