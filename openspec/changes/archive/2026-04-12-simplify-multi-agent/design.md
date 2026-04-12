## Context

多 Agent 系统由 5 个独立子系统组成：TaskRouter（路由）、DagExecutor（DAG 执行）、SubAgentSpawner（子 Agent 生命周期）、ResultFusionEngine（结果融合）、ArtifactRef（产物引用），加上作为入口的 DispatchAgentsTool。总代码量约 3900 行，但实际运行路径高度集中：用户只使用自然语言，从不写 DAG 依赖声明，路由层只是重复了主 Agent 已完成的推理，fusion 层降维了主 Agent 可获得的信息。

本次 design 目标：将多 Agent 精简为"主 Agent 声明 → 并行执行 → 原始输出拼接"三步，删除不被使用或重复推理的层。

---

## Goals / Non-Goals

**Goals:**
- 移除 TaskRouter / DagExecutor / ResultFusionEngine / ArtifactRef 四个子系统
- 重写 DispatchAgentsTool，schema 改为主 Agent 直接声明 `agent_id`
- 精简 SubAgentSpawner，移除 preflight / retry / hypothesis-driven / OTel
- 子 Agent 结果以带标签的拼接文本返回给主 Agent，主 Agent 自行综合
- 前端子 Agent 事件流（agent_start / agent_complete / agent_error）保持不变
- 清理对应测试文件（删除或重写）

**Non-Goals:**
- 不改动主 Agent runner.py 主循环结构
- 不修改子 Agent YAML 内容（仅验证 allowed_tools 完整性）
- 不改动多模型路由（model_resolver）
- 不改动前端代码
- 不改动 tool_exposure_policy.py 对主 Agent 的阶段检测逻辑
- 不改动 compute_tool_exposure_policy（主 Agent 工具面动态计算，与本次变更无关）

---

## Decisions

### D1：新 dispatch_agents schema —— 主 Agent 直接声明 agent_id

**决策**：将参数从 `tasks: [string | {task, id, depends_on}]` 改为 `agents: [{agent_id, task}]`。

**理由**：当前 schema 将意图推理（"这件事该谁做"）委托给 TaskRouter，但主 Agent LLM 在生成 dispatch_agents 调用时已经完成了这一推理。两次推理叠加带来双重不确定性，且 LLM 无法直接控制路由结果。新 schema 让主 Agent 直接声明目标，行为完全透明。

**可用 agent_id 列表**（写入主 Agent system prompt，LLM 知道选哪个）：
```
literature_search  文献检索、论文搜索
literature_reading 文献精读、批注、深度理解
data_cleaner       数据清洗、缺失值处理、异常值检测
statistician       统计检验、回归、描述性统计、特征衍生
viz_designer       数据可视化、图表制作
writing_assistant  科研写作、论文润色
citation_manager   引用格式、参考文献管理
research_planner   研究规划、实验设计
review_assistant   审稿辅助、同行评审
```

**备选方案**：保留路由层，改为更简单的纯关键词路由。否定原因：路由层本质上在复制主 Agent 的推理，且需要持续维护关键词列表。

### D2：移除 DAG 执行引擎，有序执行由主 Agent 多次调用实现

**决策**：删除 DagExecutor，dispatch_agents 只支持并行执行（所有 agents 同时启动）。

**理由**：用户通过自然语言提出需求，不会写 `depends_on` 依赖声明。有序执行（"先清洗数据，再统计"）应由主 Agent 拆成两次 dispatch_agents 调用来表达，这比 DAG 声明更自然、更透明、更易调试。

**约束**：dispatch_agents 调用中所有 agents 并行启动；如有执行顺序需求，主 Agent 多次调用 dispatch_agents 实现串行化。

### D3：移除 ResultFusionEngine，子 Agent 原始输出直接返回

**决策**：删除 fusion.py，dispatch_agents 返回带标签的拼接文本：

```
[literature_search]
{子 Agent 1 的完整输出}

[literature_search]
{子 Agent 2 的完整输出}
```

**理由**：fusion engine 在 summarize/consensus 策略下额外触发一次 LLM 调用，且将结果降维为单一文本，主 Agent 失去对各子 Agent 输出的独立判断能力。直接拼接保留全部信息，主 Agent 在综合阶段质量更高。

**拼接格式**（tool_result 注入 session 的内容）：
```
以下是 {N} 个子 Agent 的执行结果：

[{agent_id}] {task}
{summary 或错误信息}

[{agent_id}] {task}
{summary 或错误信息}
```

### D4：移除 preflight 预检

**决策**：删除 `_preflight_agent_execution`、`preflight_batch`、`BatchPreflightPlan`，子 Agent 直接执行，失败时通过 SubAgentResult.success=False 和 error 字段返回。

**理由**：preflight 对每个子 Agent 额外发一次 API 测试请求，在正常网络下是纯延迟开销（每次 +300～500ms）。测试中反复需要 mock patch 这一路径说明它是维护负担。执行失败的信息已经通过 SubAgentResult 完整返回给主 Agent，preflight 没有额外信息量。

### D5：移除 spawn_with_retry / 指数退避重试

**决策**：删除 `spawn_with_retry`，子 Agent 执行一次，失败即返回 `success=False`。

**理由**：子 Agent 失败通常是确定性的（API 错误、工具调用参数错误、任务无法完成），重试不会改变结果，只会浪费 token 和时间。主 Agent 收到失败信息后可以自己决定是否重新派发或改变策略。

### D6：移除 _spawn_hypothesis_driven

**决策**：删除假说驱动模式，dispatch_agents 只有一条执行路径。

**理由**：这是一个为特定研究场景设计的特殊模式，增加了 spawner 的分支复杂度，且与其他精简方向冲突。子 Agent 的行为由其 YAML system_prompt 定义，假说驱动的行为可通过在 task 参数中传入研究假说来实现，不需要专用执行路径。

### D7：子 Agent 工具限制保持现有机制不变

**决策**：保留 `ToolExposurePolicy`（从 agent YAML `allowed_tools` 读取白名单）和 `dispatch_agents` 的 `deny_names` 硬编码排除。不改动 `compute_tool_exposure_policy`（主 Agent 阶段检测，与本次无关）。

**理由**：`ToolExposurePolicy` 已通过 `deny_names=frozenset({"dispatch_agents"})` 防止递归派发，这一机制简单正确，无需更改。

---

## 精简后的数据流

```
主 Agent LLM
    │ tool_call: dispatch_agents(agents=[{agent_id, task}, ...])
    ▼
runner._handle_dispatch_agents
    │ 解析参数，获取 DispatchAgentsTool 实例
    ▼
DispatchAgentsTool.execute
    │ 校验 agent_ids 合法性
    │ 调用 spawner.spawn_batch
    ▼
SubAgentSpawner.spawn_batch
    │ asyncio.gather(*[_execute_agent(id, task) for ...])
    ▼
SubAgentSpawner._execute_agent (每个子 Agent，并行)
    │ 创建子会话（sub_session）
    │ 构建受限工具注册表（ToolExposurePolicy）
    │ 运行 runner 主循环（yield agent_start → 事件中继 → agent_complete）
    │ 返回 SubAgentResult(summary, success, error)
    ▼
DispatchAgentsTool
    │ 拼接结果文本（带标签）
    │ 返回 ToolResult(message=拼接文本)
    ▼
runner
    │ session.add_tool_result(tc_id, 拼接文本)
    │ 主 Agent 下一轮看到完整原始输出，自行综合
```

---

## 文件级变更清单

| 动作 | 文件 | 说明 |
|------|------|------|
| 删除 | `agent/router.py` | TaskRouter 整体删除 |
| 删除 | `agent/dag_executor.py` | DagExecutor 整体删除 |
| 删除 | `agent/fusion.py` | ResultFusionEngine 整体删除 |
| 保留 | `agent/artifact_ref.py` | spawner/code_runtime/visualization 仍在使用，超出本次范围 |
| 删除 | `tests/test_router.py` | 随 router.py 一起删除 |
| 删除 | `tests/test_dag_engine.py` | 随 dag_executor 一起删除 |
| 删除 | `tests/test_dag_executor.py` | 随 dag_executor 一起删除 |
| 删除 | `tests/test_fusion.py` | 随 fusion.py 一起删除 |
| 删除 | `tests/test_spawner_hypothesis.py` | 随 hypothesis 模式一起删除 |
| 重写 | `tools/dispatch_agents.py` | 新 schema，移除路由/DAG/fusion 路径，~150行 |
| 大幅精简 | `agent/spawner.py` | 移除 preflight/retry/hypothesis/OTel，保留 spawn_batch/_execute_agent/事件中继 |
| 重写 | `tests/test_dispatch_agents.py` | 对齐新 schema |
| 重写 | `tests/test_spawner.py` | 移除 preflight/hypothesis 相关测试，保留核心 spawn 测试 |
| 修改 | `agent/runner.py` | `_handle_dispatch_agents` 简化：移除路由分叉，对齐新 schema |
| 修改 | `tools/registry.py` | 移除对 fusion/router 的导入引用 |
| 修改 | `tests/test_multi_agent_foundation_integration.py` | 对齐新 schema |
| 修改 | `agent/prompts/builder.py` | system prompt 注入可用 agent_id 列表 |

---

## Risks / Trade-offs

**[风险] 主 Agent LLM 对 agent_id 的声明质量**
→ 缓解：在 system prompt 中明确列出所有可用 agent_id 及其适用场景，并在 dispatch_agents 描述中给出最小示例。对非法 agent_id 返回明确错误信息，而不是静默失败。

**[风险] 测试批量失效**
→ 缓解：Phase 1 先删除死代码和其对应测试，确认 `pytest -q` 通过；Phase 2 再重写 dispatch_agents，写新测试同步进行；避免"先删代码再发现测试引用了中间对象"的情形。

**[风险] 某些真实场景确实需要有序执行**
→ 缓解：主 Agent 可通过多次调用 dispatch_agents 实现串行化，这一能力不依赖 DAG 声明。在 system prompt 中给出示例："先调用 dispatch_agents 清洗数据，待结果返回后再调用 dispatch_agents 做统计"。

**[Trade-off] 子 Agent 失败无重试**
→ 主 Agent 收到 success=False 的子 Agent 结果后，可自行判断是否重新派发或在当前会话内直接执行。这比自动重试更透明，主 Agent 有完整上下文做决策。

---

## Migration Plan

**Phase 1 — 删除死代码**（独立 PR）
1. 删除 `agent/router.py`, `agent/dag_executor.py`, `agent/fusion.py`（`artifact_ref.py` 保留）
2. 删除对应测试文件（test_router / test_dag_* / test_fusion / test_spawner_hypothesis）
3. **同步**移除 `tools/dispatch_agents.py` 对 `dag_executor` 的导入，移除 `tools/registry.py` 对 `fusion` / `router` 的导入（否则 pytest 因 import 失败无法运行）
4. 运行 `pytest -q` 确认通过（此时 dispatch_agents 仍保留旧执行逻辑，仅清理了被删模块的导入）

**Phase 2 — 重写 dispatch_agents**
1. 重写 `tools/dispatch_agents.py`，新 schema，结果拼接逻辑
2. 简化 `agent/runner.py` 中的 `_handle_dispatch_agents`
3. 重写 `tests/test_dispatch_agents.py`
4. 运行 `pytest -q` 确认通过

**Phase 3 — 精简 spawner**
1. 精简 `agent/spawner.py`，移除 preflight/retry/hypothesis/OTel
2. 更新 `tests/test_spawner.py`，移除对应测试，补充核心 spawn 测试
3. 运行 `pytest -q` 确认通过

**Phase 4 — 更新 system prompt**
1. 在 `agent/prompts/builder.py` 中注入可用 agent_id 列表
2. 更新 `tests/test_multi_agent_foundation_integration.py`
3. 运行 `pytest -q` + `cd web && npm run build` 确认通过

**回滚策略**：所有删除文件均在 git 历史可恢复（`git show HEAD~n:path/to/file`）。新旧 schema 不兼容，如需回滚须同时回退 runner.py 的拦截路径和 dispatch_agents.py。

---

## Open Questions（已决策）

- **Q1 ✅ 并发上限**：spawn_batch 新增 `asyncio.Semaphore`，默认 4，通过 `settings.max_sub_agent_concurrency` 配置。详见 D3 和 multi-agent-dispatch spec。
- **Q2 ✅ 子 Agent 超时**：保留现有 `timeout_seconds`（来自 agent YAML），超时返回 `success=False, error="timeout"`，无需额外设计。
- **Q3 ✅ system prompt 格式**：agent_id + 一行中文描述的简表（9 行），避免 token 膨胀。见 D1 中的列表示例。
