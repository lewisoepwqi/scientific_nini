# 多Agent协作：上下文、工作区与产出物管理 调研分析报告

> 调研日期：2026-04-07 | 目标：为 Nini 后续多Agent架构迭代提供决策依据

---

## 目录

1. [调研范围与方法](#一调研范围与方法)
2. [Kimi Agent集群架构](#二kimi-agent集群架构)
3. [Claude Code Sub-Agent与Agent Teams](#三claude-code-sub-agent与agent-teams)
4. [行业通用架构模式](#四行业通用架构模式)
5. [Nini当前架构基线](#五nini当前架构基线)
6. [横向对比与关键洞察](#六横向对比与关键洞察)
7. [对Nini的启示与建议](#七对nini的启示与建议)
8. [参考资料](#八参考资料)

---

## 一、调研范围与方法

### 1.1 调研对象

| 对象 | 调研深度 | 数据来源 |
|------|----------|----------|
| Kimi K2/K2.5 Agent Swarm | 深度 | arXiv论文、官方博客、技术分析 |
| Claude Code Sub-Agent/Teams | 深度 | 官方文档、工程博客、社区 |
| LangGraph/CrewAI/AutoGen/OpenAI Agents SDK | 中度 | 官方文档、技术博客 |
| Magentic-One / Google ADK / A2A | 中度 | 论文、官方文档 |
| Nini 当前架构 | 深度 | 源码分析 |

### 1.2 调研维度

- **上下文管理**：共享 vs 隔离、压缩策略、跨Agent信息流转
- **工作区管理**：文件系统隔离、运行时隔离、冲突解决
- **产出物管理**：追踪、版本化、结果聚合
- **通信模式**：编排方式、消息传递、协调机制
- **训练与评估**：Agent编排能力的获取方式

---

## 二、Kimi Agent集群架构

### 2.1 基础模型

Kimi K2 是 1.04T 参数的 MoE 模型（384专家/8激活，32B活跃参数），采用 Multi-Head Latent Attention 和 MuonClip 优化器。K2.5 在此基础上增加了视觉Agent能力（MoonViT-3D）。

### 2.2 Agent Swarm 架构

K2.5 引入的**自导向并行Agent编排框架**：

```
┌─────────────────────────────────────────────────┐
│              Orchestrator（编排器）                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │create_   │  │assign_   │  │结果汇总   │       │
│  │subagent  │  │task      │  │与融合     │       │
│  └────┬─────┘  └────┬─────┘  └────▲──────┘      │
│       │              │              │             │
│  ┌────▼─────┐  ┌────▼─────┐  ┌────┴─────┐       │
│  │SubAgent 1│  │SubAgent 2│  │SubAgent N│       │
│  │独立上下文 │  │独立上下文 │  │独立上下文 │       │
│  │独立工作记 │  │独立工作记 │  │独立工作记 │       │
│  │忆        │  │忆        │  │忆        │       │
│  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────┘
```

**关键参数**：
- 最多 100 个子Agent并行
- 单任务可协调 1500+ 次工具调用
- 延迟降低最高 4.5x

### 2.3 上下文管理：主动式上下文分片（Context Sharding）

Kimi 的核心创新——**语义隔离 + 选择性路由**：

| 特性 | Kimi Agent Swarm | 传统方法 |
|------|-----------------|----------|
| 策略 | 主动式（proactive） | 被动式（reactive） |
| 机制 | 语义隔离，每个子Agent独立工作记忆 | 上下文溢出时截断 |
| 路由 | 仅任务相关输出回传编排器 | 全量信息在上下文中堆积 |
| 效果 | 从根本上减少单Agent上下文负担 | 只能缓解，无法根治 |

**信息流转模式**：
```
编排器 → create_subagent(名称, 系统提示) → 子Agent独立执行
编排器 → assign_task(子Agent, 任务描述) → 子Agent维护独立上下文
编排器 ← 仅结构化结果摘要 ← 子Agent完成后的关键输出
```

**关键原则**：子Agent的中间推理过程**不会**污染主Agent的上下文。

### 2.4 PARL（并行Agent强化学习）训练

PARL 是 Agent Swarm 编排能力的训练方法：

**解耦架构**：
- 编排器：通过RL学习最优调度策略（可训练）
- 子Agent：从固定策略检查点实例化（冻结，不参与训练）

**三组分奖励函数**：
```
r_PARL(x,y) = λ1 * r_parallel + λ2 * r_finish + r_perf(x,y)
```

| 奖励组分 | 作用 | 训练阶段变化 |
|----------|------|------------|
| `r_parallel`（实例化奖励） | 防止退化为串行执行 | λ1 退火至零 |
| `r_finish`（完成率奖励） | 防止虚假并行（创建但不执行） | λ2 退火至零 |
| `r_perf`（任务绩效奖励） | 最终输出质量 | 始终存在 |

**CriticalSteps指标**：`Σ(S_main(t) + max_i S_sub,i(t))`，衡量并行执行效率。

### 2.5 Agentic训练流水线

- **数据合成**：3000+ GitHub真实工具 + ~20,000 合成工具
- **Self-critique评分**：模型自评输出质量
- **Toggle训练**：交替"预算限制"（训练效率）和"标准扩展"（训练质量）阶段

### 2.6 Kimi CLI 与工具生态

**四大核心系统**：

| 系统 | 功能 |
|------|------|
| Agent System | YAML配置Agent，包括prompt、工具列表、子Agent定义 |
| KimiSoul Engine | 检查点 + 时间旅行调试 |
| Tool System | 可插拔工具 + 依赖注入 |
| ACP Protocol | JSON-RPC 2.0 over StdIO，IDE-Agent通信标准 |

**Kimi Claw**（2026-02-15发布）：基于OpenClaw的持久化云Agent环境，24/7运行，40GB存储，5000+技能市场。

### 2.7 工作区与产出物

- Kimi CLI Agent通过YAML声明式定义工作配置
- KimiSoul引擎支持检查点保存/恢复
- MCP集成连接外部工具服务器
- 子Agent产出物在独立空间管理，编排器统一汇总输出

---

## 三、Claude Code Sub-Agent与Agent Teams

### 3.1 Sub-Agent 系统

**核心机制**：Agent tool（v2.1.63起）在运行中派生独立子智能体。

```
┌────────────────────────────────────────────┐
│          父Agent（200K上下文）               │
│                                            │
│  Agent Tool 调用                            │
│    ├── description: 任务描述                │
│    ├── subagent_type: explore/plan/general  │
│    └── isolation: 可选worktree              │
│                                            │
│  ┌─────────────┐  ┌─────────────┐          │
│  │ SubAgent A  │  │ SubAgent B  │          │
│  │ 200K上下文  │  │ 200K上下文  │          │
│  │ 受限工具集  │  │ 受限工具集  │          │
│  └──────┬──────┘  └──────┬──────┘          │
│         │                │                  │
│    产出物写入文件系统     │                  │
│    返回轻量引用（路径+摘要）                  │
└────────────────────────────────────────────┘
```

**关键限制**：
- **单层嵌套**：子Agent不能再派生子Agent
- **同步阻塞**：父Agent等待子Agent完成后继续
- **独立权限**：子Agent的工具调用需经用户确认

**内置类型**：

| 类型 | 模型 | 工具 | 用途 |
|------|------|------|------|
| Explore | Haiku | 只读 | 快速搜索 |
| Plan | 继承父模型 | 只读 | 分析规划 |
| General-purpose | 继承父模型 | 全部 | 通用执行 |

### 3.2 Agent Teams（实验性）

**启用方式**：`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

```
┌────────────────────────────────────────────────┐
│                Team Lead                        │
│                                                │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Teammate A │  │ Teammate B │  │Teammate C│ │
│  │ 独立会话   │  │ 独立会话   │  │ 独立会话 │ │
│  │ 独立上下文 │  │ 独立上下文 │  │ 独立上下文│ │
│  └─────┬──────┘  └─────┬──────┘  └─────┬────┘ │
│        │               │               │       │
│  ┌─────▼───────────────▼───────────────▼────┐  │
│  │          共享任务列表                      │  │
│  │  ~/.claude/tasks/{team-name}/             │  │
│  └──────────────────────────────────────────┘  │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │          共享文件系统                      │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

**核心工具集**：

| 工具 | 功能 |
|------|------|
| TeamCreate | 创建团队，指定队友名称 |
| TeamDelete | 解散团队，清理资源 |
| TaskCreate | 创建任务（含依赖声明） |
| TaskUpdate | 更新状态/认领任务 |
| TaskList | 查看所有任务状态 |
| SendMessage | 定向或广播消息 |

**生命周期**：`TeamCreate → TaskCreate → 并行认领执行 → SendMessage(shutdown) → TeamDelete`

**关键约束**：
- 推荐 3-5 名队友
- 禁止嵌套团队
- 任务状态仅有 pending/in-progress/completed
- 文件锁防止认领竞态
- 任务间支持依赖声明

### 3.3 上下文管理

**隔离策略**：每个Agent（父/子/队友）拥有独立200K上下文窗口。

**自动压缩（Auto-Compaction）**：

| 参数 | 值 |
|------|-----|
| 触发阈值 | 上下文~95%容量（或剩余33K-45K token） |
| 压缩效率 | 释放60-70%上下文空间 |
| 手动触发 | `/compact`命令 |
| 子Agent记录 | 独立于主对话压缩，持久化存储 |

**Anthropic Research 系统的长对话管理**：
1. Agent将研究计划保存到外部Memory存储
2. 上下文溢出时从Memory检索计划恢复
3. 完成工作阶段后主动总结，存入Memory再进入新阶段
4. 可在上下文极限时生成全新子Agent（干净上下文），通过handoff保持连续性

**Anthropic 的核心发现**：token用量解释了80%的性能方差。多Agent Opus4(Lead) + Sonnet4(Worker) 比单Agent Opus4 性能高90.2%。

### 3.4 工作区管理

**Git Worktree 隔离**：

```yaml
# .claude/agents/researcher.md
---
name: researcher
isolation: "worktree"  # 创建独立文件系统
---
```

- 每个 SubAgent 在独立 Git 分支上工作
- 文件系统隔离，但运行时（端口/Docker）共享
- 已知限制：子Agent代码修改不会自动反映到父Agent的工作目录

**团队共享文件系统**：
- 所有 Teammate 共享同一工作目录
- 通过文件锁 + 任务分配协调写入
- SendMessage 沟通修改意图

### 3.5 产出物管理

**Anthropic 官方推荐模式——"引用而非复制"**：

```
1. 子Agent将产出物（代码/报告/可视化）写入文件系统
2. 仅向父Agent返回轻量引用（文件路径 + 关键摘要）
3. 避免在上下文中传递大量数据
4. 防止"传话游戏"（game of telephone）导致信息失真
```

**持久化路径**：
- 子Agent对话记录：`~/.claude/projects/{project}/{sessionId}/subagents/agent-{agentId}.jsonl`
- 团队配置：`~/.claude/teams/{team-name}/config.json`
- 任务数据：`~/.claude/tasks/{team-name}/`

### 3.6 记忆系统

**三层记忆架构**：

| 层级 | 文件 | 加载时机 | 作用域 |
|------|------|----------|--------|
| CLAUDE.md | 用户编写 | 会话启动时全量加载 | 项目/用户/组织 |
| Auto Memory | Claude编写 | 会话启动加载索引，按需检索 | 项目级 |
| SubAgent Memory | 可配置 | 子Agent启动时 | user/project/local |

**CLAUDE.md层级**：
```
组织级 → 用户级(~/.claude/CLAUDE.md) → 项目级(./CLAUDE.md) → 子目录级
```
- 支持 `@path` 导入（最多5跳）
- 建议 < 200行

**子Agent记忆**：通过 frontmatter `memory` 字段配置，支持跨会话持久记忆。

### 3.7 Anthropic 多Agent工程经验

来自 [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)：

| 经验 | 详情 |
|------|------|
| 教会编排者如何委托 | 每个子Agent需目标、输出格式、工具指引、任务边界 |
| 按复杂度缩放投入 | 简单查询1Agent+3-10调用；复杂研究10+Agent |
| 并行工具调用 | 将研究时间缩短90% |
| 工具设计至关重要 | 坏的工具描述让Agent走错路，40%的效率差异 |
| 端态评估优于逐步评估 | 关注最终状态而非过程 |
| Rainbow Deployment | Agent系统部署时新旧版本同时运行 |
| 产出物写入文件系统 | 避免"传话游戏"，保持信息保真度 |
| 让Agent改进自身 | Claude 4做prompt engineer，改进工具描述 |

---

## 四、行业通用架构模式

### 4.1 LangChain 四大模式

来源：[Choosing the Right Multi-Agent Architecture](https://blog.langchain.com/choosing-the-right-multi-agent-architecture/)

| 模式 | 上下文策略 | 并行性 | 适用场景 |
|------|-----------|--------|----------|
| **Subagents** | 强隔离，子Agent无状态 | 高 | 多领域并行 |
| **Skills** | 渐进式披露，单Agent按需加载 | 中 | 多专长单Agent |
| **Handoffs** | 状态跨turn存活 | 低 | 顺序工作流 |
| **Router** | 无状态路由 | 高 | 多数据源并行查询 |

**性能关键发现**：
- Subagents处理多领域任务时token用量比Skills少**67%**（因上下文隔离）
- 有状态模式（Handoffs/Skills）在重复请求时节省**40%**调用
- 简单任务三种模式性能相当（3次调用）

### 4.2 四种事件驱动多Agent设计模式

来源：[Confluent Blog](https://www.confluent.io/blog/event-driven-multi-agent-systems/)

| 模式 | 核心思想 | 事件驱动实现 |
|------|----------|-------------|
| **编排者-工作者** | 中央编排者分配任务 | Kafka topic + consumer group |
| **层级式Agent** | 递归的编排者-工作者 | 树结构每层consumer group |
| **黑板模式** | 共享知识库异步读写 | Data streaming topic |
| **市场化模式** | 去中心化谈判竞争 | Bid/ask topic + market maker |

### 4.3 主流框架对比

| 框架 | 编排方式 | 状态管理 | 并行支持 | 适用场景 |
|------|----------|----------|----------|----------|
| **OpenAI Agents SDK** | Handoffs | 内置 | 是 | 通用Agent编排 |
| **LangGraph** | 有向图 | 最强（内置有状态执行） | 是 | 复杂工作流 |
| **CrewAI** | 角色驱动 | 基本 | 有限 | 结构化pipeline |
| **AutoGen** | 对话驱动 | 共享状态挑战 | 是 | 协作推理 |
| **Google ADK** | 组合式 | 内置 | 是 | Google生态 |
| **Magentic-One** | 5-Agent固定架构 | Task ledgers | 是 | 通用问题求解 |

### 4.4 Google A2A协议

2025年4月发布的开放标准，使不同框架的Agent能互操作：
- Agent发现、安全通信、任务协调
- 与MCP的关系：MCP连接模型到数据/工具，A2A连接Agent到Agent

### 4.5 Git Worktree 作为工作区隔离方案

当前AI编码Agent并行工作的主流方案（[Upsun深度分析](https://devcenter.upsun.com/posts/git-worktrees-for-parallel-ai-coding-agents/)）：

**优势**：上下文隔离、对话历史保留、安全实验
**痛点**：

| 问题 | 详情 |
|------|------|
| 端口冲突 | 多开发服务器默认同端口，需手动分配 |
| 依赖不传递 | 每个worktree需独立安装 |
| 数据库隔离缺失 | 共享本地数据库产生竞态 |
| 磁盘消耗快 | 2GB代码库20分钟消耗9.82GB |
| 合并冲突 | 并行Agent改同一文件 |

### 4.6 上下文压缩最佳实践

**多层压缩级联**策略：
```
1. 先压缩工具输出（去除冗余数据）
2. 滑动窗口裁剪旧消息
3. 最后手段：LLM摘要化
```

**ContextEvolve框架**（arXiv:2602.02597）：专门的"上下文蒸馏Agent"压缩原始交互日志，在API-only约束下实现高搜索效率。

---

## 五、Nini当前架构基线

### 5.1 整体架构

```
WebSocket层 (api/websocket.py)
    ↓
Agent Runner层 (agent/runner.py) — ReAct主循环 ~5000行
    ↓
Session层 (agent/session.py) — 会话状态管理
    ↓
Tool层 (tools/) — 14个LLM可见工具
    ↓
Memory层 (memory/) — 四层记忆架构
    ↓
Workspace层 (workspace/) — 文件系统工作空间
```

### 5.2 多Agent能力现状

| 组件 | 文件 | 功能 |
|------|------|------|
| AgentRegistry | `agent/registry.py` | 9个内置Specialist Agent（YAML定义） |
| TaskRouter | `agent/router.py` | 双轨制路由（规则 < 5ms / LLM兜底 ~500ms） |
| SubAgentSpawner | `agent/spawner.py` | 并行派生 + 重试 + 信号量(4)控制 |
| DispatchAgentsTool | `tools/dispatch_agents.py` | 主Agent专用工具，防止递归派生 |
| ResultFusionEngine | `agent/fusion.py` | 4种融合策略（concatenate/summarize/consensus/hierarchical） |
| SubSession | `agent/sub_session.py` | 子Agent隔离会话，共享datasets/artifacts |

### 5.3 上下文管理现状

**四层记忆**：

| 层 | 机制 | 持久化 |
|----|------|--------|
| 对话记忆 | ConversationMemory (.jsonl, append-only) | 磁盘 |
| 知识记忆 | KnowledgeMemory (.md) | 磁盘 |
| 压缩摘要 | CompressionSegment（增量压缩） | meta.json |
| 长期记忆 | LongTermMemory（向量检索+语义搜索） | 跨会话 |

**压缩触发**：token数超过 `memory_compress_threshold_tokens` 时自动触发，保留最近N条消息。

### 5.4 工作区现状

```
data/sessions/{session_id}/
├── meta.json
├── memory.jsonl
├── knowledge.md
├── workspace/
│   ├── index.json          # 资源索引
│   ├── uploads/            # 用户上传
│   ├── artifacts/          # Agent产物
│   ├── charts/             # 图表
│   ├── scripts/            # 受管脚本
│   ├── reports/            # 报告
│   └── executions/         # 执行记录
```

### 5.5 关键差距分析

| 维度 | Nini现状 | 行业最佳实践 | 差距 |
|------|----------|-------------|------|
| 上下文隔离 | SubSession共享datasets/artifacts | 每个Agent独立上下文窗口 | 部分隔离 |
| 并行控制 | asyncio.Semaphore(4) | 动态调度 + 依赖管理 | 固定并发上限 |
| 产出物管理 | 回写到父Session | 写入文件系统，传递引用 | 回写内存 |
| 任务协调 | 无任务板，一次性dispatch | 共享任务列表 + 依赖声明 | 缺少状态跟踪 |
| 通信模式 | 单次dispatch → 融合 | 持续消息传递 + 协调 | 无中间通信 |
| Worktree隔离 | 无 | Git Worktree | 无文件系统隔离 |
| Agent编排训练 | 无（规则+LLM路由） | PARL强化学习 | 无学习优化 |

---

## 六、横向对比与关键洞察

### 6.1 上下文管理策略对比

| 策略 | Kimi Agent Swarm | Claude Code | Nini |
|------|-----------------|-------------|------|
| **隔离方式** | 语义隔离 + 独立工作记忆 | 独立200K窗口 | SubSession共享datasets |
| **压缩策略** | 通过并行化减少单Agent负担 | Auto-Compaction(60-70%) | CompressionSegment增量压缩 |
| **信息路由** | 仅结构化结果回传 | 写文件系统+传引用 | 产物回写内存 |
| **长上下文** | 主动分片 | 外部Memory存储 | 长期记忆向量检索 |
| **训练优化** | PARL强化学习编排 | 无 | 无 |

**关键洞察**：
1. **隔离 > 共享**：所有领先系统都采用上下文隔离而非共享
2. **主动 > 被动**：Kimi的主动式分片优于被动式截断
3. **引用 > 复制**：Anthropic的"引用而非复制"模式是产出物管理的最佳实践
4. **token用量是性能核心变量**：解释80%性能方差

### 6.2 工作区管理策略对比

| 策略 | Kimi CLI | Claude Code | Nini |
|------|----------|-------------|------|
| **隔离方式** | YAML声明 + MCP | Git Worktree可选 | 无隔离 |
| **运行时隔离** | 云环境隔离 | 部分隔离（端口共享） | 无 |
| **产物追踪** | 检查点机制 | 文件系统引用 | index.json + artifacts |
| **冲突解决** | 编排器协调 | 文件锁 + 消息沟通 | 串行执行避免 |

### 6.3 通信模式对比

| 模式 | Kimi | Claude Code | Nini |
|------|------|-------------|------|
| **拓扑** | 集中式编排 | Sub-Agent:星形 / Teams:网状 | 星形（主Agent→子Agent） |
| **同步性** | 异步并行 | Sub-Agent:同步 / Teams:异步 | 同步（dispatch→等待） |
| **中间通信** | 无（独立执行后汇总） | SendMessage(Teams) | 无 |
| **协调训练** | PARL强化学习 | 无 | 无 |

### 6.4 架构模式适用性分析

对于Nini（科研数据分析）场景的适用性评估：

| 模式 | 适用度 | 原因 |
|------|--------|------|
| Sub-Agent（星形委托） | ★★★★★ | Nini已有的模式，适合数据分析的并行子任务 |
| Skills（渐进式披露） | ★★★★☆ | 按需加载专业分析知识，减少上下文占用 |
| Router（并行路由） | ★★★☆☆ | 适合多数据源并行查询，但Nini场景相对固定 |
| Handoffs（顺序交接） | ★★☆☆☆ | 科研分析流程非严格顺序 |
| Agent Teams（对等协作） | ★★★☆☆ | 复杂研究项目可能需要，但增加大量复杂度 |

---

## 七、对Nini的启示与建议

### 7.1 短期优化（低成本高收益）

#### P0: 完善上下文隔离

**现状问题**：SubSession 共享父 Session 的 `datasets` 和 `artifacts`，子Agent操作可能干扰父上下文。

**建议**：
- 子Agent应操作datasets的**深拷贝**或**引用计数**的视图
- 产出物写入 workspace/artifacts/ 目录，仅返回轻量引用（文件路径 + 摘要）
- 参考 Anthropic 的"引用而非复制"模式

```
改进前: sub_session.datasets = parent_session.datasets (共享引用)
改进后: sub_session.dataset_refs = {name: "workspace/uploads/xxx.csv"} (轻量引用)
```

#### P0: 增加任务状态跟踪

**现状问题**：dispatch_agents 是一次性派发，无中间状态跟踪。

**建议**：
- 引入简单的 TaskBoard（类似 Claude Code Teams 的 TaskList）
- 支持 pending → in_progress → completed 状态流转
- 子Agent完成后更新状态，而非全部完成后才融合

#### P1: 优化产出物管理

**建议**：
- 子Agent将产出物（图表/报告/变换后的数据）写入 workspace 对应子目录
- 仅返回结构化引用：`{"type": "chart", "path": "workspace/charts/xxx.json", "summary": "..."}`
- ResultFusionEngine 基于引用摘要融合，而非完整内容

### 7.2 中期增强（需要架构调整）

#### P1: 工作区隔离

**建议**：
- 为需要文件系统操作的子Agent创建临时工作目录（类似轻量版 worktree）
- `workspace/sandbox_tmp/{agent_id}/` 下创建隔离沙箱
- 子Agent完成后，产物移入主 workspace

#### P1: 异步并行执行

**现状问题**：SubAgentSpawner.spawn_batch() 虽然并行派生，但结果融合是同步等待。

**建议**：
- 引入 asyncio.Event 或类似机制，子Agent可主动报告中间进度
- 主Agent不阻塞等待所有子Agent，可基于中间结果提前行动
- 参考 Anthropic Research 系统的"Lead Agent 可创建新子Agent"模式

#### P2: 子Agent中间通信

**建议**：
- 为需要协作的子Agent提供共享"黑板"（workspace/shared/blackboard.json）
- 或引入轻量消息队列（基于 asyncio.Queue）
- 参考黑板模式（Blackboard Pattern）

### 7.3 长期演进（需要研究投入）

#### P2: 渐进式上下文披露（Skills模式）

**建议**：
- 当前后 Agent 注册中心的 9 个 Specialist Agent 可演变为 Skills
- 按需加载专业知识的完整提示词，而非始终保持在上下文中
- 参考 LangChain Skills 模式和 Claude Code 的 Markdown Agent 定义

#### P3: Agent编排能力优化

**建议**：
- 收集 dispatch_agents 的使用数据（任务分解质量、子Agent完成率、融合质量）
- 构建评估数据集，参考 Anthropic 的"LLM-as-judge"评估方法
- 长期考虑参考 PARL 的思路，通过强化学习优化编排策略

#### P3: 混合模型策略

**建议**：
- 参考 Anthropic 的发现：Lead用强模型(如GPT-4o/Claude Opus)，Worker用性价比模型
- 简单任务（文献检索、数据清洗）用轻量模型
- 复杂任务（统计建模、研究规划）用强模型
- 可在 AgentDefinition 中增加 `model_preference` 字段

### 7.4 架构演进路线图

```
Phase 1（当前）: 星形委托 + 一次性派发
  └── 主Agent → dispatch_agents → SubAgentSpawner → ResultFusion

Phase 2（短期）: 隔离优化 + 状态跟踪
  ├── SubSession 上下文隔离（深拷贝/引用）
  ├── 产出物写入文件系统 + 轻量引用
  └── TaskBoard 状态跟踪

Phase 3（中期）: 异步协调 + 工作区隔离
  ├── 异步并行 + 中间进度报告
  ├── 子Agent沙箱工作区
  └── 共享黑板/消息队列

Phase 4（长期）: 智能编排 + 混合模型
  ├── Skills 渐进式上下文披露
  ├── 混合模型策略
  └── 编排能力评估与优化
```

---

## 八、参考资料

### Kimi
- [Kimi K2: Open Agentic Intelligence - arXiv](https://arxiv.org/abs/2507.20534)
- [Kimi K2.5: Visual Agentic Intelligence - arXiv](https://arxiv.org/abs/2602.02276)
- [Kimi CLI 技术深度分析 - llmmultiagents.com](https://llmmultiagents.com/en/blogs/kimi-cli-technical-deep-dive)
- [Kimi K2 技术分析 - intuitionlabs.ai](https://intuitionlabs.ai/kimi-k2-technical-deep-dive/)
- [Kimi Claw Tutorial - DataCamp](https://www.datacamp.com/tutorial/kimi-claw-tutorial)
- [Kimi-Researcher - Moonshot AI](https://moonshotai.github.io/Kimi-Researcher/)

### Claude Code
- [How we built our multi-agent research system - Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Sub-agents 文档 - code.claude.com](https://code.claude.com/docs/en/sub-agents)
- [Agent Teams 文档 - code.claude.com](https://code.claude.com/docs/en/agent-teams)
- [Memory 文档 - code.claude.com](https://code.claude.com/docs/en/memory)
- [Compaction 文档 - platform.claude.com](https://platform.claude.com/docs/en/build-with-claude/compaction)
- [Claude Agent SDK - GitHub](https://github.com/anthropics/claude-agent-sdk-python)

### 通用多Agent
- [Choosing the Right Multi-Agent Architecture - LangChain](https://blog.langchain.com/choosing-the-right-multi-agent-architecture/)
- [Four Design Patterns for Event-Driven Multi-Agent Systems - Confluent](https://www.confluent.io/blog/event-driven-multi-agent-systems/)
- [Git Worktrees for Parallel AI Coding Agents - Upsun](https://devcenter.upsun.com/posts/git-worktrees-for-parallel-ai-coding-agents/)
- [Magentic-One - Microsoft Research](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/)
- [Google A2A Protocol](https://a2a-protocol.org/latest/specification/)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/multi_agent/)
- [Google ADK Multi-Agent](https://google.github.io/adk-docs/agents/multi-agents/)
- [ContextEvolve - arXiv:2602.02597](https://arxiv.org/html/2602.02597v1)
- [Multi-Agent Coordination Survey - arXiv:2502.14743](https://arxiv.org/html/2502.14743v2)
