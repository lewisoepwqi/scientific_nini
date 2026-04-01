# claw-code 分析报告（综合版）

> 日期：2026-04-01
> 综合来源：
> - `docs/reports/claw-code-analysis-2026-04-01-glm5.1.md`
> - `docs/reports/claw-code-analysis-2026-04-01.md`
> - `docs/reports/agent-robustness-analysis-20260401.md`
> 结论立场：借鉴 `claw-code` 的 harness 设计思想，但不把其当前 Python shim/porting 结构直接等同于 `nini` 的目标运行时。

---

## 1. 两份现有报告的优劣与互补

### 1.1 GLM5.1 版本的优点

GLM5.1 版本的强项主要有三点：

1. **结构性思考更激进**。它不满足于修补当前问题，而是主动提出 `runner.py` 模块拆分、不可变状态快照、预编码 toolchain、事件协议分层等长期架构方向。这一部分有助于避免只在当前 bug 点打补丁。
2. **更强调“减少 LLM 决策点”**。它对 `auto_run`、toolchain、静态权限策略、硬预算的偏好，与问题文档中“软约束失败”的核心诊断是一致的。
3. **实施计划意识更强**。它比另一份报告更像“架构备忘录”，提出了若干可演进的目标形态。

### 1.2 GLM5.1 版本的不足

GLM5.1 版本也有几个明显问题：

1. **对 `claw-code` 的可迁移性判断偏乐观**。`claw-code` 当前 Python 端口大量是 mirrored/shim 结构，它擅长的是 surface、route、session summary、permission filter 这类 harness 元能力，而不是 `nini` 这种真实科研分析运行时。因此，把其某些模式直接上升为 `nini` 的近期目标，会有偏差。
2. **部分建议不适合 `nini` 当前维护阶段**。例如把 `runner.py` 拆分作为 P0，或引入“全量不可变 session”作为近期主线，风险过高、收益周期过长，而且会直接冲击现有 WebSocket、数据集、artifact、压缩链路。
3. **低估了科学分析场景的语义复杂度**。`claw-code` 的 token-based route 对通用命令面是有效的，但 `nini` 的多变量统计分析、阶段切换、图表/报告/工具联动，不能主要依赖 token 匹配路由。
4. **有些建议更像“新架构愿景”，不是当前代码库的最优下一步**。例如事件协议大幅简化，理论上更整洁，但会触碰前后端契约，不应作为短期重点。

### 1.3 Codex 版本的优点

Codex 版本的强项主要是：

1. **对 `claw-code` 的定位更谨慎**。它明确区分了“值得借鉴的 harness 方法”和“不能直接照搬的执行模型”，这更贴近 `nini` 的现实。
2. **更贴合当前问题文档**。它直接围绕 `pending_scripts`、`tool_failures`、`surface governance`、`debug CLI` 这些和现有痛点强相关的方向展开，落地性更强。
3. **对维护期项目更友好**。建议更偏“局部结构增强 + 诊断能力补齐”，不要求先做高风险重构。

### 1.4 Codex 版本的不足

Codex 版本也存在不足：

1. **对长期结构治理的推动不够强**。它对 “snapshot / pending_actions / debug CLI” 讲得比较充分，但对“中长期如何让 runner 不再继续膨胀”讲得还不够。
2. **缺少分阶段实施计划**。建议虽然合理，但没有把依赖关系、阶段目标、验证方式和风险控制组织成工程计划。
3. **没有充分吸收 GLM5.1 的两个好点子**：`不可变快照思维` 和 `toolchain/自动链接思维`。这两个点不适合全量迁移，但适合被缩小后局部引入。

### 1.5 互补结论

两份报告最好的互补方式不是“二选一”，而是：

- **保留 Codex 版本的谨慎迁移与项目贴合度**
- **吸收 GLM5.1 版本的结构治理意识与阶段化实施视角**
- **剔除 GLM5.1 中那些与 `nini` 当前阶段不匹配的重构激进项**

综合后，最合理的方向不是“大改架构”或“继续只修提示词”，而是：

1. 先把**关键执行状态显式化**；
2. 再把**诊断与回放能力做成产品级工具**；
3. 最后才做**局部模块化拆分**，而不是先做全面重构。

---

## 2. 对 claw-code 的综合判断

### 2.1 真正值得借鉴的，不是 shim 本身，而是 harness 工程方法

`claw-code` 当前最有价值的部分不是 `execute_tool()` 这类 shim，而是下面四种方法：

1. **surface 显式化**：命令面、工具面、权限面都可枚举、可过滤、可回归。
2. **状态显式化**：会话状态、stop_reason、permission_denials、transcript 都是结构化对象。
3. **诊断产品化**：`summary / bootstrap / turn-loop / load-session` 这种调试入口是默认提供的。
4. **约束前置化**：通过权限上下文、工具池过滤、预算门控在“执行前”收缩自由度，而不是主要靠执行后补救。

### 2.2 不应直接照搬的部分

以下内容不应被直接作为 `nini` 的近期目标：

1. **全量 shim 化执行模型**：`nini` 是真实科研分析系统，不是 porting workspace。
2. **全面 immutable session 化**：`nini` 当前 session 持有 DataFrame、artifact、memory、streaming state，直接全量不可变会显著提高复杂度。
3. **token-based 主路由**：科学分析任务需要 richer semantic routing，不能降级成关键词匹配主导。
4. **大幅压缩事件协议**：`nini` 当前事件类型多，虽然冗余，但与前端能力绑定较深，短期不适合剧烈收缩。

### 2.3 对 nini 更合理的借鉴方式

最合理的借鉴方式是“局部结构迁移”，也就是：

- 不迁移 `claw-code` 的执行形态
- 迁移它的**状态建模方式**
- 迁移它的**调试/回放入口设计**
- 迁移它的**surface 治理与权限前置思路**

---

## 3. 面向 nini 的综合判断

### 3.1 当前问题的根因没有变

`nini` 当前最关键的问题仍然是问题文档里已经指出的那一句：**大量关键行为仍依赖模型“读懂消息后主动遵守”**。这意味着：

- 任何继续停留在“再补一段提示词”“再加一条 warning”“再扩一点关键词匹配”的方案，边际收益都会越来越低；
- 真正有效的改进，必须把信息从“消息文本”升级为“结构化状态”，把约束从“提示模型”升级为“系统代做/系统前置过滤/系统硬拒绝”。

### 3.2 当前项目阶段决定了优化顺序

仓库当前处于维护阶段，目标是稳定性、性能和可观测性优化，不适合先做高风险大重构。因此更合理的策略是：

1. **先修行为失效链路**：解决 `create_script`、`task_state`、`tool_failures`、completion check、timeout 这些会直接导致错误结论或空转的点。
2. **再补诊断基础设施**：把 session snapshot、summary CLI、surface manifest 做起来。
3. **最后做局部重构**：在有足够 trace 和 snapshot 之后，再抽离 `runner.py` 的局部模块。

### 3.3 因此，综合版的总体判断是

GLM5.1 版本更像“长期架构方向报告”，Codex 版本更像“当前维护期行动报告”。  
对 `nini` 来说，更好的版本应该是：

- **短期采用 Codex 路线为主**
- **中期吸收 GLM5.1 的 snapshot/toolchain/module split 思维**
- **拒绝把高风险大重构提前到 P0**

---

## 4. 综合优化建议（P0/P1/P2）

以下建议已经合并两份报告，并按“更适合项目、更合理”重新排序。

### P0：先把关键执行状态显式化，消除当前最真实的失效链路

#### P0-1：引入统一的 `pending_actions` 账本，替代零散状态字段

不要只加 `pending_script_ids` 或 `current_turn_tool_failures` 两个孤立字段，而是引入统一账本：

```python
@dataclass
class PendingAction:
    kind: str
    key: str
    status: str
    detail: str
    created_at: str
    source_tool: str | None = None
```

建议纳入的 `kind`：
- `script_not_run`
- `tool_failure_unresolved`
- `artifact_promised_not_materialized`
- `user_confirmation_pending`
- `task_noop_blocked`

理由：
- 这是对问题文档优化 A/B/D/G 的统一承接；
- 它比单独补字段更可维护；
- 它也是最接近 `claw-code`“结构化状态收敛”的借鉴方式。

#### P0-2：把 `create_script → run_script` 升级为系统级自动链接，而不是只靠消息提醒

这里吸收 GLM5.1 的 toolchain 思维，但不必上完整通用框架。更适合 `nini` 的第一步是：

1. `create_script` 默认 `auto_run=True`
2. 若 `auto_run=False` 或运行失败，则写入 `pending_actions`
3. `ContextBuilder` 只注入统一 `pending_actions`

也就是说，近期不需要引入完整 `Toolchain` 框架，但要先把“自动链接”这个思想落地。

#### P0-3：Completion Check 改为“基于结构化证据”的校验

把当前 completion check 从“关键词 + 文本恢复提示”升级为：

- 先生成结构化 evidence
- 再由 evidence 映射成 completion items

最低限度应覆盖：
- 是否存在 unresolved tool failure
- 是否存在 promised artifact 未落地产物
- 是否仍有 pending action
- 是否还有未完成任务
- 是否属于 transitional output

这样可以把问题文档中的 `F/G/H` 合并到一个更稳的框架内。

#### P0-4：按 `purpose` 区分沙箱 timeout，同时把 timeout 失败纳入 `pending_actions`

这条保留原问题文档建议，但要强调两点：

1. timeout 调整是必要的，但不是根治；
2. timeout 后必须留下结构化待处理状态，而不是只留一条文本报错。

这使得 timeout 成为“待恢复任务”，而不是“历史里的一个错误片段”。

---

### P1：补齐调试、回放和 surface 治理能力

#### P1-1：新增 `HarnessSessionSnapshot`

这条吸收 GLM5.1 的“快照思维”，但不做全量 immutable session。  
更适合 `nini` 的实现方式是：**为每轮执行额外生成不可变摘要快照，而不是让整个 session 全量不可变**。

建议结构至少包含：
- `session_id`
- `turn_id`
- `stop_reason`
- `pending_actions`
- `task_progress`
- `selected_tools`
- `tool_failures`
- `token_usage`
- `compressed_rounds`
- `trace_ref`

这会成为诊断、回放、恢复和 CLI 展示的统一数据源。

#### P1-2：新增 `nini debug summary` / `nini debug snapshot` / `nini debug load-session`

这条直接借鉴 `claw-code` 的调试产品化思路。  
建议近期至少提供三类 CLI：

- `nini debug summary <session-id>`
- `nini debug snapshot <session-id> [--turn N]`
- `nini debug load-session <session-id>`

这会显著降低鲁棒性分析成本，也让后续复盘不再高度依赖人工翻消息流。

#### P1-3：新增 `nini doctor --surface`

这条结合两份报告共识：

- 输出当前 tools
- 输出高风险 tools
- 输出 skills snapshot
- 输出按策略过滤后的 visible tools
- 输出与基线快照的差异

这项工作短期不直接影响用户结果，但对“为什么模型看到了这个工具”“为什么这轮暴露面失控”非常关键。

#### P1-4：把工具暴露策略前置成 `ToolExposurePolicy`

不要直接照搬 `claw-code` 的静态 deny 机制，但要借鉴它的“暴露前过滤”思想。  
更适合 `nini` 的做法是基于任务阶段和风险等级生成暴露策略：

- `profile` 阶段只暴露最小工具面
- `analysis` 阶段按方法类型暴露统计工具
- `export` 阶段才暴露导出相关工具
- 未授权时 export/write 类操作不暴露或仅暴露审批占位能力

这条建议的目标不是“减少所有工具”，而是减少本轮不该出现的工具。

---

### P2：在稳定之后再做中期结构治理

#### P2-1：为常见链路引入轻量 toolchain

这里保留 GLM5.1 的好思路，但降级为中期目标。  
优先候选链路：

- `create_script -> run_script`
- `dataset_catalog(profile) -> stat_model/stat_test`
- `chart_session(create/update) -> export`
- `report_session(create/patch) -> export`

第一阶段只实现 1-2 条高频链路，不做通用框架大铺开。

#### P2-2：为压缩与恢复链路补契约测试

建议把下面几类问题做成测试契约：

- 压缩后 `pending_actions` 仍存在
- 压缩后 completion recovery 仍可判断 unresolved failure
- 压缩后任务状态不会退化成“全部 pending”
- runtime context budget 不会优先裁掉关键结构状态

这条会把当前的“靠文档复盘发现问题”变成“测试提前阻断回归”。

#### P2-3：基于 snapshot 和 trace 证据，逐步拆分 `runner.py`

这条不取消，只是后移。  
更合理的顺序是：

1. 先有 snapshot、pending_actions、completion evidence
2. 再提取 `turn_budget.py`
3. 再提取 `completion_verifier.py`
4. 再提取 `tool_execution_guard.py`

只有当这些结构性对象先稳定下来，拆分 `runner.py` 才不会把复杂度从一个文件搬到四个文件。

---

## 5. 不推荐作为近期主线的建议

为了避免方向漂移，以下建议明确不作为近期主线：

1. **全量 immutable session 改造**  
原因：对 `nini` 当前数据结构侵入过大，收益周期不匹配维护阶段。

2. **token-based 主路由**  
原因：科研分析任务语义复杂度高，容易误判。

3. **事件协议大幅瘦身**  
原因：触碰前后端契约过广，不适合作为当前主任务。

4. **先拆大文件再修问题**  
原因：现在的首要目标是减少失效与空转，不是先获得形式上的模块整洁。

---

## 6. 后续项目迭代优化实施计划

### Iteration 1：行为可靠性收敛（1 周）

目标：优先消除已经在真实会话里反复出现的执行失效。

范围：
- `create_script` 默认自动执行
- 统一 `pending_actions` 账本
- completion check 基于结构化 evidence
- timeout 按 purpose 分层

涉及文件：
- `src/nini/agent/session.py`
- `src/nini/agent/components/context_builder.py`
- `src/nini/agent/prompt_policy.py`
- `src/nini/harness/runner.py`
- `src/nini/tools/code_session.py`
- `src/nini/sandbox/policy.py` 或对应配置文件

交付物：
- 新增 `pending_actions` 数据结构
- runtime context 中新增 `pending_actions` 块
- `create_script` 自动执行默认开启
- unresolved failure / promised artifact / pending action 完成校验上线

验证：
- `pytest -q`
- 针对 `code_session`、completion verifier、timeout 的新增回归测试
- 至少复现并覆盖问题文档里的 `create_script` 漏执行案例

风险：
- `pending_actions` 设计不当会与现有 task manager 语义重复
- `auto_run` 可能改变少量依赖“先创建后审查”的行为

控制方式：
- `auto_run` 保留显式关闭开关
- `pending_actions` 首期只覆盖 4 类高价值状态

### Iteration 2：诊断与回放基础设施（1 周）

目标：把鲁棒性分析从“读消息”升级为“读快照/摘要”。

范围：
- `HarnessSessionSnapshot`
- `nini debug summary`
- `nini debug snapshot`
- `nini debug load-session`
- `nini doctor --surface`

涉及文件：
- `src/nini/harness/`
- `src/nini/agent/session.py`
- `src/nini/cli/` 或 CLI 对应入口
- `src/nini/tools/registry.py`

交付物：
- 每轮执行生成快照
- CLI 可查看 session 摘要、某轮 snapshot、surface 差异

验证：
- CLI 回归测试
- 对同一失败会话，能在不读原始消息历史的情况下定位问题

风险：
- 快照字段过多导致冗余
- CLI 与内部数据结构耦合过深

控制方式：
- 首期快照只存摘要字段和 ref，不复制大对象

### Iteration 3：暴露面治理与压缩契约（1-2 周）

目标：降低弱模型工具误选和压缩回归。

范围：
- `ToolExposurePolicy`
- 阶段化 `simple_mode`
- 压缩/恢复契约测试

涉及文件：
- `src/nini/agent/runner.py`
- `src/nini/agent/components/context_builder.py`
- `src/nini/memory/compression.py`
- `tests/`

交付物：
- 分阶段工具池
- 压缩/恢复契约测试集
- surface manifest 基线文件

验证：
- 压缩后任务状态与 pending_actions 不丢失
- 工具暴露面在典型场景下显著收缩

风险：
- 工具面收缩过度，反而影响完成率

控制方式：
- 从最简单的 `profile / export` 两阶段开始
- 保留 feature flag

### Iteration 4：局部模块化重构（维护期后半段）

目标：在前面三轮稳定后，再处理 `runner.py` 的长期维护问题。

建议拆分顺序：
1. `turn_budget.py`
2. `completion_verifier.py`
3. `tool_execution_guard.py`
4. 视情况再拆 `recovery.py`

不建议一步拆成 4-5 个大模块；每次只抽一类已经被结构化的职责。

验证：
- 每次拆分后跑 `pytest -q`
- 行为快照前后对比一致

---

## 7. 最终结论

如果只问“哪份原始报告更好”，答案并不稳定：

- 从**长期架构想象力**看，GLM5.1 版本更强；
- 从**当前项目贴合度与落地性**看，Codex 版本更强。

但如果问“哪种综合结论更适合 `nini` 当前项目”，答案是明确的：

> **先做结构化状态和诊断能力，再做局部模块化，而不是先做大重构。**

也就是说，`nini` 当前最合理的路线不是把 `claw-code` 的形式照搬过来，而是借用它的工程方法：

- 把运行面做成结构化对象；
- 把调试面做成默认可用工具；
- 把约束尽量前置；
- 把真正的大重构放到证据足够之后。

这条路线既吸收了 `claw-code` 的优点，也保留了 `nini` 作为真实科研分析运行时的现实约束。

---

## 8. 参考资料

### 综合比较对象

- `docs/reports/claw-code-analysis-2026-04-01-glm5.1.md`
- `docs/reports/claw-code-analysis-2026-04-01.md`
- `docs/reports/agent-robustness-analysis-20260401.md`

### 外部项目：claw-code

- `README.md`
- `src/query_engine.py`
- `src/runtime.py`
- `src/commands.py`
- `src/tools.py`
- `src/permissions.py`
- `src/session_store.py`
- `src/transcript.py`
- `tests/test_porting_workspace.py`

### 本地项目：nini

- `src/nini/agent/session.py`
- `src/nini/agent/components/context_builder.py`
- `src/nini/agent/prompts/builder.py`
- `src/nini/agent/prompt_policy.py`
- `src/nini/harness/runner.py`
- `src/nini/memory/compression.py`
