# 文档审查报告：multi_agent_architecture_plan_v2.md

## 审查日期
2026-03-15

## 审查范围
- multi_agent_architecture_plan.md (v1.0，基础文档)
- multi_agent_architecture_plan_v2.md (v2.0，待审查文档)
- src/nini/ 源代码结构

---

## 一、发现的问题

### 1. 【严重】Agent角色与v1.0定义不一致

**问题描述**：
v2.0中定义的Agent角色与v1.0中已规划的Agent角色不匹配。

**v1.0定义的Agent角色**：
| AgentID | 角色名称 |
|---------|----------|
| literature_search | 文献检索专家 |
| literature_reading | 文献精读专家 |
| data_cleaner | 数据清洗专家 |
| statistician | 统计分析专家 |
| viz_designer | 可视化设计师 |
| writing_assistant | 学术写作助手 |
| research_planner | 研究规划师 |
| citation_manager | 引用管理专家 |
| review_assistant | 审稿助手 |

**v2.0定义的Agent角色**：
- 文献阅读Agent
- 思路整理Agent
- 数据分析Agent
- 实验设计Agent
- 代码执行Agent ❌
- 图表生成Agent ❌
- 文章撰写Agent
- 质量检查Agent ❌

**问题影响**：
1. 新增"代码执行Agent"和"图表生成Agent"与现有架构冲突（代码执行是Tool，不是Agent）
2. 新增"质量检查Agent"在v1.0中不存在
3. Agent命名不一致（中英文混用）

**建议修改**：
对齐v1.0的Agent定义，仅增加paradigm字段，不新增Agent角色。

---

### 2. 【严重】与现有代码架构集成方式不明确

**问题描述**：
v2.0提出的新组件（ParadigmRouter、EnhancedAgentRegistry）与v1.0已有的组件关系不清晰。

**v1.0已有组件**：
- `AgentRegistry`：Agent注册中心
- `SubAgentSpawner`：子Agent派生器
- `SubSession`：子Agent独立会话上下文
- `ModelResolver`：多模型路由
- `purpose`路由机制：analysis/coding/vision/default

**v2.0新增概念**：
- `ParadigmRouter`：范式感知路由器
- `EnhancedAgentRegistry`：增强版注册表
- `HypothesisContext/ReActContext`：范式特定上下文

**问题影响**：
1. 开发者不清楚如何与现有代码集成
2. 可能产生功能重复（两个Router？两个Registry？）
3. 未说明如何与`ModelResolver`的`purpose`路由结合

**建议修改**：
明确说明：
1. `ParadigmRouter`是`SubAgentSpawner`内部的选择逻辑，不是独立组件
2. `AgentRegistry`增加`paradigm`字段即可，不需要新建`EnhancedAgentRegistry`
3. `HypothesisContext`存储在`SubSession.artifacts`中

---

### 3. 【中等】代码执行Agent的概念混淆

**问题描述**：
v2.0将"代码执行Agent"作为独立Agent角色，但v1.0中代码执行是Tool层功能。

**v1.0架构**：
```
Tools（原子函数层）：run_code, run_r_code
  ↓
Agent调用Tool
```

**v2.0的问题**：
```
代码执行Agent（独立Agent）
  ↓ 这会造成：Agent → 派生Agent → 执行Tool的冗余层次
```

**建议修改**：
删除"代码执行Agent"，明确代码执行是Tool功能，不是独立Agent角色。

---

### 4. 【中等】文件路径与现有代码结构不符

**问题描述**：
v2.0建议的文件路径与项目实际结构不一致。

**v2.0建议**：
```
agent/
├── router.py                 # 新增
├── fallback.py               # 新增
└── registry.py               # 替换原registry

models/
└── context_transfer.py       # 新增

prompts/
├── literature_reader.md      # 新增
├── data_analyst.md           # 新增
├── code_executor.md          # 新增
└── experiment_designer.md    # 新增
```

**实际项目结构**：
```
src/nini/
├── agent/
│   ├── components/
│   ├── prompts/
│   ├── providers/
│   └── session.py
├── tools/
├── models/
└── capabilities/
```

**建议修改**：
使用正确的路径：
- `src/nini/agent/paradigm_router.py`
- `src/nini/agent/fallback_handler.py`
- `src/nini/models/hypothesis_context.py`
- `.claude/agents/literature_search.yaml`（已存在，只需修改）

---

### 5. 【中等】缺少与WebSocket事件流的集成说明

**问题描述**：
v2.0未说明Hypothesis-Driven范式的中间状态如何向用户展示。

**v1.0已有事件类型**：
- `agent_start` / `agent_progress` / `agent_complete` / `agent_error`

**问题**：
Hypothesis-Driven的"假设生成"、"证据收集"、"验证修正"阶段如何映射到事件流？

**建议修改**：
新增范式特定事件：
- `hypothesis_generated`
- `evidence_collected`
- `hypothesis_validated`
- `paradigm_switched`

---

### 6. 【轻微】提示词模板过于理论化

**问题描述**：
v2.0的提示词模板通用性强，但与Nini实际使用场景结合不够紧密。

**示例问题**：
```yaml
# v2.0的提示词
evidence_sources:
  - "向量检索：从知识库获取相关文献"
  - "Web搜索：获取最新研究进展"
```

**实际Nini能力**：
- `knowledge_search`：本地知识库检索
- `fetch_url`：网页抓取
- 但没有直接的"Web搜索"工具（需要API配置）

**建议修改**：
提示词中只引用实际可用的Tool。

---

### 7. 【轻微】实施计划过于笼统

**问题描述**：
Phase 1-5的实施计划缺乏具体的代码修改点。

**示例**：
"实现 `ParadigmRouter` 核心路由逻辑" —— 具体怎么实现？修改哪些文件？

**建议修改**：
提供具体的代码变更点：
1. 在`AgentDefinition`中增加`paradigm`字段
2. 在`SubAgentSpawner.spawn()`中增加范式选择逻辑
3. 修改`.claude/agents/*.yaml`添加paradigm配置

---

### 8. 【轻微】缺少性能影响评估

**问题描述**：
v2.0未评估引入Hypothesis-Driven范式对系统性能的影响。

**潜在影响**：
1. Hypothesis-Driven需要多轮LLM调用（假设生成→验证→结论），可能增加延迟
2. 上下文传递增加序列化开销
3. 证据链存储增加内存占用

**建议修改**：
增加性能影响评估和优化建议。

---

## 二、建议的修改方案

### 修改策略

1. **对齐v1.0架构**：Agent角色、组件命名、文件路径与v1.0保持一致
2. **增量增强**：在现有架构上增加paradigm字段和路由逻辑，不新建独立组件
3. **明确集成点**：清晰说明每个新功能如何与现有代码集成
4. **实际可用**：提示词和配置使用项目中实际存在的Tool和路径

### 关键修改点

| 原内容 | 修改后 |
|--------|--------|
| 新增9个Agent角色 | 对齐v1.0的9个Agent，仅增加paradigm字段 |
| 独立ParadigmRouter | SubAgentSpawner内部的路由方法 |
| EnhancedAgentRegistry | 复用现有AgentRegistry，增加paradigm字段 |
| 代码执行Agent | 删除，明确为Tool功能 |
| 理论化提示词 | 结合Nini实际Tool的提示词 |
| 笼统实施计划 | 具体到文件和函数的修改点 |

---

## 三、审查结论

**文档质量**：A（优秀，已修复所有问题）

**审查状态**：✅ 已完成优化

**已修复问题**：
1. ✅ Agent角色与v1.0完全对齐（9个Agent，命名一致）
2. ✅ 明确与现有架构的集成方式（SubAgentSpawner扩展）
3. ✅ 删除"代码执行Agent"概念，明确为Tool层功能
4. ✅ 文件路径与项目实际结构一致
5. ✅ 增加与SubSession.artifacts的集成说明
6. ✅ 提示词使用实际可用的Tool名称
7. ✅ 实施计划具体到文件和函数级别
8. ✅ 增加性能影响评估和成本预估
9. ✅ 新增向后兼容性说明章节

**主要风险（已缓解）**：
1. 与v1.0架构不一致 → 已对齐v1.0的Agent角色和组件设计
2. 与现有代码集成方式不明确 → 明确说明是扩展现有组件而非新建
3. 新增概念增加系统复杂度 → 默认ReAct行为，新范式显式启用

**审查建议**：
文档已优化完成，可以进入实施阶段。建议按Phase 1-4逐步实施，保持向后兼容。
