# Nini 项目开发状态记录

## 文档说明

- 文档目的：记录当前这一轮架构优化的实际落地状态，作为后续继续开发、代码审查、任务拆解和回归验证的基线。
- 记录时间：2026-02-28
- 记录范围：本轮围绕 `Nini 2.0` 架构愿景推进的后端、前端、测试与任务规划状态。
- 当前结论：项目已从“概念规划”推进到“关键骨架可运行”，但仍未完全达到目标愿景，尤其是 `ResearchProfile`、更多可执行 Capability、增强版 Intent 理解、科研专项深度能力仍待补齐。

---

## 一、架构愿景回顾

本轮优化的北极星目标如下：

```text
Intent Layer → Skill Runtime → MCP Gateway
  (意图理解)      (技能执行)      (生态连接)

Progressive Disclosure (三级披露)
  Index → Instruction → Runtime Resources

Multi-Layer Memory (四层记忆)
  Conversation + Analysis + Knowledge + Research Profile

Scientific Research Specialization
  统计严谨性 + 方法智能推荐 + 发表级输出 + 跨研究积累
```

当前判断：

- `Intent Layer`：已落最小可用实现，并接入 API、Runner、前端。
- `Skill Runtime`：三级披露、语义目录、技能选择、允许工具聚合已完成基础闭环。
- `MCP Gateway`：仓库内已有初始实现，但尚未纳入本轮主线收口。
- `Multi-Layer Memory`：`AnalysisMemory` 已持久化，`ResearchProfile` 尚未实现。
- `Scientific Research Specialization`：能力比优化前更强，但仍未达到“方法推荐 + 发表级输出 + 跨研究积累”的完整目标。

---

## 二、本轮已完成的核心工作

### 1. Capability 执行契约修正与统一

#### 已完成内容

- 修正 `DifferenceAnalysisCapability` 早期依赖不存在工具 `data_quality` 的问题。
- 差异分析能力内部改为自行执行最小前提检验：
  - Shapiro-Wilk 正态性检验
  - Levene 方差齐性检验
- 为 Capability 元数据增加执行态字段：
  - `is_executable`
  - `execution_message`
- 将 Capability 目录模型和执行模型统一到注册表契约：
  - `Capability` 支持 `executor_factory`
  - `CapabilityRegistry` 支持统一 `execute()` / `create_executor()`
- API 侧不再硬编码 `difference_analysis` 特例执行分支。

#### 当前效果

- 能力目录展示和实际执行能力不再完全脱节。
- 目前真正可执行的 Capability 已明确为 `difference_analysis`。
- 其余能力仍可保留为目录项，但不会再误导为“已经支持直接执行”。

---

### 2. AnalysisMemory 磁盘持久化

#### 已完成内容

- `AnalysisMemory` 从进程内字典缓存升级为磁盘持久化。
- 持久化位置：

```text
data/sessions/<session_id>/analysis_memories/
```

- 实现能力包括：
  - 按会话自动加载
  - 写入后自动保存
  - 会话级列出分析记忆
  - 区分“清空内存缓存”和“删除持久化数据”

#### 当前效果

- `AnalysisMemory` 已具备跨进程重启恢复能力。
- 记忆连续性已从“仅当前进程有效”提升为“可跨会话恢复”。

#### 仍有限制

- 当前仅覆盖 `AnalysisMemory`，尚未完成完整四层记忆闭环。
- `ResearchProfile` 缺失，用户长期研究偏好尚不能沉淀。

---

### 3. Skill 元数据增强 v1

#### 已完成内容

- Function Tool 与 Markdown Skill 已统一支持以下元数据字段：
  - `brief_description`
  - `research_domain`
  - `difficulty_level`
  - `typical_use_cases`

- 支持方式：
  - Python Function Tool：由 `tools/base.py` 与 `tools/manifest.py` 提供统一输出
  - Markdown Skill：由 `tools/markdown_scanner.py` 解析 frontmatter 并透传到目录层

#### 当前效果

- 技能目录已具备更好的语义描述基础。
- 为后续语义检索、意图匹配、推荐排序、前端展示提供了统一字段。
- 老技能无需全部改造也可通过默认值维持兼容。

---

### 4. 三级披露与语义技能目录

#### 已完成内容

- 在 Tool/Skill 注册表中补齐三级披露接口：
  - `get_skill_index()`
  - `get_skill_instruction()`
  - `get_runtime_resources()`
  - `get_semantic_catalog()`

- 语义目录现在会返回更完整的运行属性，包括：
  - `disable_model_invocation`
  - `user_invocable`

- API 层新增或增强相关能力：
  - `GET /api/skills/semantic-catalog`
  - `GET /api/skills/markdown/{skill_name}/instruction`
  - `GET /api/skills/markdown/{skill_name}/runtime-resources`

#### 当前效果

- Skill Runtime 已不再依赖“直接把 Markdown 全文塞进上下文”的单一模式。
- 目录、说明、运行资源已经可以分层按需加载。

#### 仍有限制

- 当前仍以规则和元数据驱动为主，未引入更强的语义召回机制。

---

### 5. 统计模块拆分完成

#### 已完成内容

原本较大的统计实现已拆分为独立模块：

- `statistics/t_test.py`
- `statistics/anova.py`
- `statistics/correlation.py`
- `statistics/regression.py`
- `statistics/nonparametric.py`
- `statistics/multiple_comparison.py`

同时：

- `statistics/__init__.py` 已切换为导出拆分后的实现
- `_statistics_legacy.py` 已收口为纯兼容层，仅做 re-export

#### 当前效果

- 统计相关实现边界更清晰。
- 后续维护、测试、局部重构成本明显下降。
- 旧导入路径仍保留兼容，减少对现有代码的破坏。

---

### 6. Intent Layer 最小实现落地

#### 已完成内容

新增模块：

- `src/nini/intent/base.py`
- `src/nini/intent/service.py`
- `src/nini/intent/__init__.py`

当前 Intent 层已支持：

- Capability 候选分析
- Markdown Skill 候选分析
- 显式 `/skill` 调用解析
- Active Skills 选择
- `allowed_tools` 聚合
- 澄清问题与澄清选项生成
- `tool_hints` 输出

并已接入以下位置：

- `CapabilityRegistry.suggest_for_intent()`
- `AgentRunner` 的技能自动匹配与技能选择
- API：
  - `POST /api/intent/analyze`
  - 增强 `GET /api/capabilities/suggest`

#### 当前效果

- 意图理解逻辑不再完全散落在 Runner 和 Registry 内部。
- 能力推荐、技能选择、推荐工具和澄清逻辑已有统一入口。

#### 当前实现级别

- 当前版本属于 `rule_based_v1`
- 仍以规则、关键词、元数据匹配为主

---

### 7. Intent 结果接入 Agent Runner

#### 已完成内容

- 在首轮 LLM 调用前增加 Intent 分析。
- 当输入存在明显歧义时，可复用现有 `ask_user_question` 机制先发起澄清。
- 在消息构建阶段，将以下内容注入运行时上下文：
  - Capability 候选
  - Skill 候选
  - `tool_hints`

#### 当前效果

- 模型在正式回答前，可以得到更明确的研究任务方向提示。
- 当输入模糊时，系统可以先追问，而不是直接盲答。

---

### 8. 前端已展示 Intent 理解结果

#### 已完成内容

前端状态层新增：

- `currentIntentAnalysis`
- `intentAnalysisLoading`
- `analyzeIntent()`
- `composerDraft`

前端交互行为已实现：

- 发送消息前先调用 `/api/intent/analyze`
- 重试上一轮时重新分析意图
- 聊天面板顶部展示 `IntentSummaryCard`
- 摘要卡展示：
  - 能力候选
  - Active Skills
  - 显式 `/skill`
  - 推荐工具
  - 澄清建议
- 用户点击建议后可直接写回输入框

#### 当前效果

- 用户在模型正式回答前，已经可以看到系统当前如何理解请求。
- 意图理解结果已从“仅后端内部能力”变成“前端可见的产品能力”。

#### 当前限制

- 当前主要停留在聊天顶部摘要卡。
- 还未深入接入每轮对话时间线或更细粒度的运行提示。

---

## 三、当前架构状态总览

### 1. Intent Layer

状态：基础可用，已接入主链路。

已完成：

- 统一意图分析入口
- Capability 推荐
- Skill 匹配
- Active Skill 选择
- 允许工具聚合
- 澄清问题触发
- 前端摘要展示

未完成：

- 更强的语义检索或 embedding 方案
- 更细粒度的解释链
- 会话级意图历史积累

### 2. Skill Runtime

状态：基础闭环已形成。

已完成：

- 三级披露
- 语义目录
- 元数据增强
- Runner 侧技能选择整合

未完成：

- 更强的语义召回与排序
- 更精细的资源加载策略
- 更强的科研任务编排能力

### 3. Capability Layer

状态：契约统一，能力执行面仍偏薄。

已完成：

- 目录与执行契约统一
- `difference_analysis` 可直接执行

未完成：

- 更多 Capability 接入真实执行器
- 能力级编排与结果模板体系

### 4. Memory Layer

状态：部分完成。

已完成：

- `Conversation`：已有
- `AnalysisMemory`：已持久化

未完成：

- `Knowledge` 侧系统化沉淀尚不充分
- `ResearchProfile` 未落地

### 5. MCP Gateway

状态：初始存在，但未成为本轮推进主线。

说明：

- 仓库中已有 `mcp/` 相关实现
- 但尚未围绕新 Intent / Capability / Skill Runtime 完整对齐

---

## 四、已验证结果

### 1. 后端测试回归

本轮关键阶段已通过的测试集合包括但不限于：

```bash
pytest -q tests/test_intent.py tests/test_capabilities.py tests/test_ask_user_question_tool.py tests/test_ecosystem_alignment.py tests/test_conversation_observability.py tests/test_skills_architecture.py tests/test_hybrid_skills.py
```

结果：

```text
115 passed, 2 skipped in 4.40s
```

另有统计拆分与记忆持久化等定向回归已通过。

### 2. 前端构建验证

已执行：

```bash
cd web && npm run build
```

结果：

- 构建通过
- 仍存在既有的 `plotly` chunk 过大告警

当前判断：

- 属于非阻塞性能优化项
- 不是本轮改动新引入的问题

---

## 五、主要修改范围

### 后端核心文件

- `src/nini/capabilities/base.py`
- `src/nini/capabilities/defaults.py`
- `src/nini/capabilities/registry.py`
- `src/nini/capabilities/__init__.py`
- `src/nini/capabilities/implementations/difference_analysis.py`
- `src/nini/api/routes.py`
- `src/nini/memory/compression.py`
- `src/nini/agent/session.py`
- `src/nini/agent/runner.py`
- `src/nini/tools/base.py`
- `src/nini/tools/manifest.py`
- `src/nini/tools/markdown_scanner.py`
- `src/nini/tools/registry.py`
- `src/nini/tools/tool_adapter.py`
- `src/nini/tools/statistics/__init__.py`
- `src/nini/tools/statistics/anova.py`
- `src/nini/tools/statistics/correlation.py`
- `src/nini/tools/statistics/regression.py`
- `src/nini/tools/statistics/nonparametric.py`
- `src/nini/tools/statistics/multiple_comparison.py`
- `src/nini/tools/_statistics_legacy.py`
- `src/nini/intent/base.py`
- `src/nini/intent/service.py`
- `src/nini/intent/__init__.py`

### 前端核心文件

- `web/src/store.ts`
- `web/src/components/CapabilityPanel.tsx`
- `web/src/components/ChatPanel.tsx`
- `web/src/components/ChatInputArea.tsx`
- `web/src/components/IntentSummaryCard.tsx`

### 测试文件

- `tests/test_capabilities.py`
- `tests/test_difference_analysis_capability.py`
- `tests/test_analysis_memory_integration.py`
- `tests/test_skills_architecture.py`
- `tests/test_hybrid_skills.py`
- `tests/test_ecosystem_alignment.py`
- `tests/test_statistics_split.py`
- `tests/test_intent.py`

---

## 六、当前仍未完成或需要优化的部分

### P1：高优先级未完成项

#### 1. `ResearchProfile` 尚未实现

影响：

- 四层记忆仍未闭环
- 用户研究偏好、常用方法、输出习惯无法稳定积累

建议方向：

- 新增 `research_profile.py`
- 支持跨会话持久化
- 可选择性注入 Prompt
- 支持显式更新而非完全自动学习

#### 2. 只有一个真正可执行的 Capability

当前现状：

- `difference_analysis` 可执行
- 其他能力仍主要停留在目录和推荐层

影响：

- “Capability” 仍偏展示层
- 难以体现能力编排架构的完整价值

建议方向：

- 优先实现第二个可执行 Capability
- 候选：
  - `data_exploration`
  - `correlation_analysis`

#### 3. Intent 仍是规则版 v1

当前现状：

- 规则可用，但上限有限

风险：

- 长尾表达、隐式任务、跨领域语义理解能力不足

建议方向：

- 引入更强的语义匹配
- 可评估 embedding / 检索增强方案
- 保持规则层作为稳定回退

---

### P2：中优先级优化项

#### 4. Intent 前端体验仍较浅

当前现状：

- 已有顶部摘要卡和可点击建议

仍可优化：

- 将 Intent 结果接入每轮会话时间线
- 展示更明确的“系统准备怎么做”
- 在工具调用和技能激活时给出更一致的可视反馈

#### 5. 科研专项深度能力仍需增强

当前仍不足的方向：

- 方法推荐的严谨性仍可加强
- 发表级报告输出规范尚未形成稳定模板
- 跨研究问题的偏好累积尚未形成产品能力

#### 6. MCP Gateway 尚未与新架构完全收口

当前现状：

- 已有初始实现
- 但尚未围绕 Intent / Capability / Skill Runtime 统一接线

---

### P2：性能与工程化优化项

#### 7. 前端打包体积问题

现状：

- `plotly` chunk 偏大

建议方向：

- 按需加载或动态拆包
- 分析图表相关依赖是否可进一步延迟加载

#### 8. 可观测性仍有提升空间

建议方向：

- 增加意图分析耗时日志
- 增加 Skill 激活、Capability 执行耗时指标
- 增加错误聚合与失败定位能力

---

## 七、后续开发计划

### Task 1：实现 `ResearchProfile`

- 优先级：P1
- 类型：新增
- 目标：
  - 完成四层记忆闭环
  - 沉淀研究偏好、常用方法、输出偏好、研究领域标签
- 建议涉及文件：
  - `src/nini/memory/research_profile.py`
  - `src/nini/agent/session.py`
  - `src/nini/agent/profile_manager.py`
  - `src/nini/api/routes.py`
  - 对应测试文件
- 验收标准：
  - 支持跨会话持久化
  - 支持读取并注入对话上下文
  - 不破坏现有会话流程

### Task 2：实现第二个可执行 Capability

- 优先级：P1
- 类型：新增
- 推荐目标：
  - `data_exploration` 或 `correlation_analysis`
- 目标：
  - 验证 Capability 架构不是只对一个能力成立
  - 形成“目录 -> 执行 -> 输出”的可复用模式
- 验收标准：
  - 注册表可统一发现并执行
  - API 可直接执行
  - 前端能够正确展示执行状态

### Task 3：升级 Intent Layer 到增强语义版本

- 优先级：P1/P2
- 类型：优化
- 目标：
  - 从 `rule_based_v1` 进化到更强的语义理解
- 方向：
  - 元数据加权排序
  - 更强语义匹配
  - embedding / 检索增强可评估
- 验收标准：
  - 长尾表达匹配能力优于当前规则版
  - 规则层仍保留为兜底

### Task 4：增强前端 Intent 交互体验

- 优先级：P2
- 类型：优化
- 目标：
  - 将 Intent 理解从“摘要展示”升级为“交互过程能力”
- 方向：
  - 接入会话时间线
  - 增强澄清交互反馈
  - 展示系统推荐路径与当前激活技能

### Task 5：科研专项能力深化

- 优先级：P2
- 类型：优化
- 目标：
  - 更贴近科研工作者实际使用场景
- 方向：
  - 更强的方法推荐
  - 更严格的结果解释模板
  - 发表级报告结构输出
  - 跨研究积累能力

### Task 6：MCP Gateway 与新架构对齐

- 优先级：P2
- 类型：重构/优化
- 目标：
  - 让外部生态接入更自然地对齐新的 Capability / Skill / Intent 架构

### Task 7：性能与可观测性优化

- 优先级：P2
- 类型：优化
- 方向：
  - 大体积前端依赖拆分
  - Runner / Skill / Capability 耗时日志
  - 失败定位与错误聚合

---

## 八、推荐执行顺序

建议按以下顺序推进：

1. 先补 `ResearchProfile`
2. 再实现第二个可执行 Capability
3. 然后升级 Intent 语义理解
4. 再做前端 Intent 深化展示
5. 最后推进科研专项深化与 MCP 收口

原因：

- 先闭环记忆层，能为后续更强意图理解和能力推荐提供用户级上下文
- 再补第二个可执行 Capability，可以验证现有架构不是单点特例
- 在此基础上升级 Intent，会更容易利用丰富元数据和能力契约

---

## 九、当前开发状态结论

### 当前阶段判断

项目当前已不再停留于“架构设想”阶段，而是进入“关键骨架已落地、等待能力扩展和深度优化”的状态。

### 当前最准确的状态描述

- 能跑
- 能测
- 有主链路
- 有前后端联动
- 有最小 Intent 层
- 有基础 Capability 执行模型
- 有 AnalysisMemory 持久化
- 有 Skill Runtime 的三级披露

但同时：

- 还没有完整四层记忆
- 还没有多个强执行 Capability
- 还没有更强的语义意图理解
- 还没有完全达到“科研专项深度优先”的终局形态

### 一句话总结

当前 Nini 已完成从“工具集合”向“具备意图理解、技能运行时和能力目录雏形的科研智能体”过渡的关键阶段，但离 `Nini 2.0` 的完整形态仍有一段明确且可拆解的工程路线要走。
