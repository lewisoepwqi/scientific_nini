# claw-code 分析报告

> 日期：2026-04-01
> 对比对象：`claw-code`（commit `9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a`） vs `nini` 当前方案
> 说明：本文重点借鉴 `claw-code` 的 harness 设计方法，不把它当前 Python 端口视为 `nini` 的功能级替代品。

## 1. claw-code 设计理念

### 1.1 Harness-first，而不是先堆功能

`claw-code` 在 README 中直接把定位写成 “Better Harness Tools”，并明确说自己关注的是 harness、tool wiring、agent workflow 和 runtime context，而不是单纯保留原始代码归档。这说明它的第一原则不是“先把能力做多”，而是“先把代理运行框架做稳、做清楚”。这一点在代码层也一致：`src/main.py` 暴露的核心入口是 `summary`、`manifest`、`route`、`bootstrap`、`turn-loop` 等运行时诊断命令，而不是领域功能命令。

可验证依据：
- README 的定位与 backstory 明确强调 harness engineering、tool wiring、runtime context。
- `src/main.py` 围绕 manifest、route、bootstrap、turn-loop 组织 CLI。
- `src/bootstrap_graph.py` 把启动链路拆成可读的 bootstrap stages。

### 1.2 用显式清单管理命令面和工具面

`claw-code` 的第二个明显设计理念是“先把表面定义清楚，再谈运行时行为”。`src/commands.py` 和 `src/tools.py` 不是动态散落地暴露能力，而是从快照加载镜像清单，统一提供 `get_*`、`find_*`、`render_*`、`execute_*` 入口。测试里还要求镜像命令和工具数量达到下限，并验证 CLI 可枚举、可查询、可显示、可执行 shim。

这背后的理念是：代理系统的能力面必须先可盘点、可搜索、可回归验证，否则任何“工具太多”“工具选错”“能力漂移”的问题都很难定位。

可验证依据：
- `src/commands.py` / `src/tools.py` 使用 snapshot 加载 `PORTED_COMMANDS` / `PORTED_TOOLS`。
- `tests/test_porting_workspace.py` 对命令数、工具数、CLI 输出和 show/exec 行为做回归验证。
- README 的 “Current Parity Checkpoint” 也强调先对齐 surface，再逐步逼近 runtime parity。

### 1.3 把会话状态、停止原因和转录历史做成一等公民

`claw-code` 的第三个设计理念是“状态显式化”。`QueryEngineConfig` 明确有 `max_turns`、`max_budget_tokens`、`compact_after_turns`、`structured_output` 等约束；`TurnResult` 把 `matched_commands`、`matched_tools`、`permission_denials`、`usage`、`stop_reason` 统一收敛；`TranscriptStore`、`StoredSession` 负责 replay、flush、persist。也就是说，它不假设问题只能通过自然语言提示解决，而是把“当前轮发生了什么、为什么停、哪些权限被拒绝”直接写进结构体。

可验证依据：
- `src/query_engine.py` 的 `QueryEngineConfig`、`TurnResult`、`persist_session()`、`stream_submit_message()`。
- `src/session_store.py` 的 `StoredSession` 与 `.port_sessions` 持久化。
- `src/transcript.py` 的追加、压缩、回放、flush。

### 1.4 权限和暴露面过滤是运行时对象，不是散落提示词

`claw-code` 还体现出一个很实用的理念：权限控制和工具暴露面应该是结构化运行时对象。`ToolPermissionContext` 负责 deny name / deny prefix；`get_tools()` 负责 `simple_mode`、`include_mcp` 和 permission filter；运行时则显式生成 `permission_denials`。这意味着“哪些工具当前能用、为什么不能用”是可计算、可测试、可显示的，而不是主要依赖模型去理解一句提示。

可验证依据：
- `src/permissions.py` 的 `ToolPermissionContext`。
- `src/tools.py` 的 `filter_tools_by_permission_context()` 与 `get_tools()`。
- `src/runtime.py` 的 `_infer_permission_denials()` 与 `RuntimeSession`。

## 2. 架构优势（对比 nini）

先给结论：`claw-code` 当前 Python 端口的能力深度远不如 `nini`，但它在“harness 可审计性”和“运行面可盘点性”上有几处明显优势，正好对应 `nini` 近期暴露出的鲁棒性问题。

### 2.1 会话恢复路径更直接，少依赖“从消息反推状态”

`nini` 当前 `Session` 很强大，但任务状态恢复仍有一部分依赖于回放历史消息中的 `task_write / task_state` tool call，再重建 `TaskManager`。这说明一旦历史压缩、消息污染或恢复链条出现偏差，会话状态仍然存在“需要推断”的成分。相比之下，`claw-code` 直接把 `messages`、token 统计和 transcript 作为显式会话数据保存与加载，恢复路径更短。

对比点：
- `nini`：`src/nini/agent/session.py` 通过 `_reconstruct_task_manager_from_messages()` 回放 tool call 恢复任务状态。
- `claw-code`：`src/session_store.py` 直接保存 `StoredSession`，`src/query_engine.py` 通过 `from_saved_session()` 恢复。

### 2.2 调试入口更统一，诊断成本更低

`nini` 已有 `HarnessRunner`、trace 和 runtime context，但更多是“内部机制已经存在”；运维和开发视角下，还缺一个轻量、标准、可直接运行的“本轮发生了什么”的统一诊断出口。`claw-code` 把这件事做成了默认 CLI：`summary`、`manifest`、`route`、`bootstrap`、`turn-loop`、`load-session`。这会显著降低回归分析成本。

对比点：
- `nini`：`src/nini/harness/runner.py` 有 budget warning、completion check、trace，但主要围绕真实执行链路工作。
- `claw-code`：`src/main.py` + `src/runtime.py` 提供面向操作者的摘要、路由、bootstrap、turn-loop、load-session。

### 2.3 工具面治理更强，能力漂移更容易发现

`nini` 当前更强调“系统提示词中的工具黄金路径”和“运行时上下文中的能力引导”，这对真实任务完成很重要，但副作用是工具面治理分散在 prompt、runtime context、tool schema 和 harness 校验里。`claw-code` 把命令面和工具面先做成清单，再做 CLI 和测试校验，这种治理方式更适合发现能力膨胀、命名漂移和暴露面异常。

对比点：
- `nini`：`src/nini/agent/prompts/builder.py` 用大量策略规则约束工具调用，`src/nini/agent/components/context_builder.py` 再补 runtime context。
- `claw-code`：`src/commands.py` / `src/tools.py` / `tests/test_porting_workspace.py` 以 snapshot 和回归测试治理 surface。

### 2.4 权限决策更结构化

`nini` 已经有高风险工具放行、session 级授权和 harness 阻断，这是正确方向；但当前规则同时分布在提示词、运行时工具规则和执行器逻辑里。`claw-code` 的做法更统一：权限上下文先变成对象，再过滤工具暴露面，再记录 denial。对弱模型来说，这比“告诉模型某些情况要小心”更稳定。

对比点：
- `nini`：高风险工具和批准逻辑分散在 `src/nini/agent/runner.py` 与会话授权状态中。
- `claw-code`：`ToolPermissionContext` → `get_tools()` → `permission_denials` 是一条直接链路。

## 3. nini 现有方案评价

### 3.1 有效性

`nini` 当前问题文档的核心诊断是准确的：真正的问题不是单个提示词写得不够清楚，而是太多关键行为仍依赖模型“看懂提示后自觉遵守”。文档把这一点明确归纳为“软约束为主、硬约束为辅”，并把优化重点放在 `auto_run`、`pending_scripts`、`tool_failures`、`success=false`、结构化 completion check 等方向上，这与 `claw-code` 的方法论是同向的。

我认为现有规划中最有效的部分有三类：
- 把 `create_script → run_script` 从两步软约束变成一步或结构化待办。
- 把任务状态和失败信息放进 session/runtime context，而不是只留在自然语言消息里。
- 改善压缩摘要，尽量保住工具结果、任务状态和数值产出。

### 3.2 局限性

当前规划也有明显边界：

第一，它还是偏“故障点修补”。文档主要围绕 `task_state`、`code_session`、completion recovery 和 compression 展开，能修当前痛点，但还没有上升到“整个 agent surface 怎么盘点、诊断、回归”的层面。

第二，它仍混合了结构性修复与提示词修复。像 `F/H/J/K` 这些建议有价值，但本质上仍然是优化提醒、关键词和日志；如果没有更强的状态显式化和会话快照，后续仍可能在别的路径复发。

第三，它缺少统一的调试产物。当前要理解一轮失败运行，仍然需要同时看消息历史、runtime context、harness trace、tool result 和压缩摘要。这个成本明显高于 `claw-code` 的 `RuntimeSession` 风格。

### 3.3 遗漏点

结合 `claw-code`，我认为 `nini` 现有规划还遗漏了三件事：

- 缺少“工具面/技能面清单治理”。现在更像是运行时约束强，但 surface 级回归弱。
- 缺少“可加载、可回放、可摘要”的统一调试入口。
- 缺少“统一 pending actions 账本”。问题文档已经提出 `pending_scripts` 和 `tool_failures`，但还没有把它们抽象成一个通用执行账本。

## 4. 优化建议（P0/P1/P2）

下面的建议只列可落地项，并且每条都标注 `claw-code` 依据。

### P0

#### P0-1：新增 `HarnessSessionSnapshot`，把每轮执行摘要持久化为可加载对象

建议把 `nini` 当前分散在 `Session`、`HarnessRunner`、trace、runtime context 里的关键信息，收敛成一个可持久化的 `HarnessSessionSnapshot`，至少包含：
- `turn_id / session_id / stop_reason`
- `selected_tools / denied_tools / failed_tools / pending_actions`
- `task_progress / compressed_rounds / token_usage / cost`
- `transcript_ref / trace_ref / latest_runtime_context_ref`

这不是替代现有 trace，而是增加一个面向诊断和恢复的“统一入口”。这样后续调试不再需要从消息历史里二次拼装。

为什么是 P0：
- 它直接降低故障分析成本。
- 它能承接问题文档里 `pending_scripts`、`tool_failures`、completion check 等多个建议，避免再分散存储。

`claw-code` 依据：
- `src/query_engine.py` 的 `TurnResult`、`stop_reason`、`persist_session()`
- `src/runtime.py` 的 `RuntimeSession`
- `src/session_store.py` 与 `src/transcript.py` 的显式持久化和 replay

#### P0-2：把“pending scripts / failed tools / pending confirmations / promised artifacts”统一成 `pending_actions` 账本

问题文档已经提出 `pending_scripts`、`tool_failures`，方向正确，但建议不要只补两个字段，而是一次性抽象成统一的 `pending_actions` 数据结构，按 `kind` 管理：
- `script_not_run`
- `tool_failure_unresolved`
- `user_confirmation_pending`
- `artifact_promised_not_materialized`

`ContextBuilder` 只注入这一份账本摘要；`HarnessRunner` 和工具执行器负责更新它。这样未来再遇到新的失败模式，不需要每次都新增一个孤立字段。

为什么是 P0：
- 它把问题文档中的多条 P0/P1 建议合成一个统一机制，减少后续维护复杂度。
- 它直接响应当前“模型记不住上一步还没做完什么”的根因。

`claw-code` 依据：
- `src/query_engine.py` / `src/runtime.py` 都倾向于把运行信息收敛成结构化结果，而不是散在文本中
- `src/session_store.py` 的会话结构显式持久化方式

### P1

#### P1-1：新增 `nini doctor --surface` 或 `nini debug surface`，做工具面/技能面清单回归

建议为 `nini` 增加一个 surface manifest 命令，输出：
- 当前可见 tools
- skills snapshot 数量与名称
- 高风险 tools
- 被 intent/permission/simple-mode 过滤掉的 tools
- 与基线快照相比的新增/删除项

同时配套测试，防止某次改动意外扩大或缩小暴露面。这样可以把“模型为什么看到了这个工具”变成一个可回答的问题。

`claw-code` 依据：
- `src/commands.py` / `src/tools.py` 的 snapshot 驱动 surface 管理
- `tests/test_porting_workspace.py` 对命令数、工具数和 CLI 能力做回归检查

#### P1-2：把工具/技能路由理由写入 trace，而不只记录最终调用结果

`nini` 现在更擅长执行，但对“为什么此轮选择了这个工具或这个 skill”缺少统一说明。建议参考 `claw-code` 的 `route_prompt()`，在 `HarnessRunner` 或 `ContextBuilder` 中补一份 `route_trace`：
- 候选项
- 选中原因
- 被过滤原因
- permission denial 原因

这项建议不改变业务能力，但会显著提高误调用、空参数调用、重复调用问题的定位效率。

`claw-code` 依据：
- `src/runtime.py` 的 `route_prompt()`、`RoutedMatch`
- `src/history.py` 的 `HistoryLog`

#### P1-3：把权限策略统一成可组合对象，在“暴露前”过滤工具，而不是主要在执行时拦

`nini` 已经有授权和高风险处理，但可以再往前推一步：针对不同意图或 stage，先生成一个 `ToolExposurePolicy`，把不该暴露的工具直接从该轮工具面中移除，只把必要工具交给模型。比如：
- 数据概览轮只暴露 `dataset_catalog / task_state / ask_user_question`
- 报告导出轮再暴露 `report_session / workspace_session`
- 未授权时直接不暴露 export 类操作

这比“工具已经暴露给模型，再靠消息或 approval 拦截”更稳。

`claw-code` 依据：
- `src/permissions.py` 的 `ToolPermissionContext`
- `src/tools.py` 的 `get_tools(simple_mode, include_mcp, permission_context)`

### P2

#### P2-1：为 `nini` 增加 `simple_mode` 工具池，按任务阶段收缩工具面

`claw-code` 在 `get_tools()` 里支持 `simple_mode`，虽然实现简单，但思路很有用。`nini` 可以做得更细：在 Plan、Profile、Check、Export 等阶段提供不同的精简工具池，降低工具选择成本和错误调用概率。尤其是当前 `nini` 的系统提示词已经非常长，减少可见工具数量会比继续加提示词更有效。

`claw-code` 依据：
- `src/tools.py` 的 `simple_mode`
- `src/tool_pool.py` 的工具池装配方式

#### P2-2：补一套“harness 摘要/加载/回放”轻量 CLI

建议增加类似下面的调试命令：
- `nini debug summary <session>`
- `nini debug turn-loop <session>`
- `nini debug load-snapshot <turn>`

这类 CLI 不直接提升用户能力，但能显著缩短鲁棒性问题的复现路径，尤其适合维护期。

`claw-code` 依据：
- `src/main.py` 的 `summary / bootstrap / turn-loop / load-session`
- `tests/test_porting_workspace.py` 对这些 CLI 的回归验证

#### P2-3：把“压缩是否保住关键状态”做成显式契约测试

问题文档已经在修摘要，但建议进一步把以下内容写成测试契约：
- 有 `pending_actions` 时压缩后仍能恢复
- completion recovery 需要的信息在压缩后仍可用
- `task_progress` / `failed_tools` / `promised_artifacts` 不会被 runtime budget 意外裁掉

这项建议优先级不如前面几条高，但能避免后续优化再次破坏恢复链路。

`claw-code` 依据：
- `tests/test_porting_workspace.py` 的风格是“每个调试入口都可跑、可回归”
- `src/query_engine.py` 对 `structured_output`、`stop_reason`、`compact_after_turns` 的显式建模

## 5. 参考资料

### 外部项目：claw-code

- [claw-code 仓库主页](https://github.com/instructkr/claw-code)
- [README.md @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/README.md)
- [src/main.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/main.py)
- [src/query_engine.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/query_engine.py)
- [src/runtime.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/runtime.py)
- [src/commands.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/commands.py)
- [src/tools.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/tools.py)
- [src/permissions.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/permissions.py)
- [src/session_store.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/session_store.py)
- [src/transcript.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/src/transcript.py)
- [tests/test_porting_workspace.py @ 9ade3a7](https://github.com/instructkr/claw-code/blob/9ade3a70d70ae690ae15d3c8f1de7e6d03d87a2a/tests/test_porting_workspace.py)

### 本地项目：nini

- `docs/reports/agent-robustness-analysis-20260401.md`
- `docs/architecture-concepts.md`
- `docs/prompt-architecture.md`
- `src/nini/agent/session.py`
- `src/nini/agent/components/context_builder.py`
- `src/nini/agent/prompts/builder.py`
- `src/nini/agent/prompt_policy.py`
- `src/nini/harness/runner.py`
- `src/nini/memory/compression.py`
