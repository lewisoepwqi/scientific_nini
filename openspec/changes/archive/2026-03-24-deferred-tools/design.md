## Context

`ToolRegistry` 已有完整的分层基础设施：
- `Tool.expose_to_llm` 属性（基类默认 `True`）
- `registry_core.py` 的 `get_tool_definitions()` 已按该属性过滤
- 目前 31 个工具暴露给 LLM（全量），2 个已设 `expose_to_llm = False`（`organize_workspace`、`dispatch_agents`）

缺失的只有一块：**LLM 无法发现隐藏工具**。一旦将工具标记为隐藏，LLM 就会完全不知道它的存在，无法按需调用。引入 `search_tools` 工具后，LLM 可以"先搜索后使用"，实现按需加载。

**候选隐藏工具**（低频/被高层工具覆盖的原子工具）：

| 候选工具 | 理由 |
|---------|------|
| `t_test`、`mann_whitney`、`anova`、`kruskal_wallis` | `stat_test` 已统一封装，原子版本极少直接调用 |
| `correlation_analysis`、`regression_analysis` | `stat_model` + `complete_*` 系列已覆盖 |
| `export_chart`、`export_document`、`export_report` | 低频，用户明确要求导出时才调用 |
| `analysis_memory`、`search_memory_archive` | 低频，仅在需要回溯时调用 |
| `update_profile_notes` | 极低频，系统辅助工具 |
| `fetch_url` | 情景性使用，非核心 |

目标：将 LLM 可见工具从 31 个降至约 18 个，每次请求减少约 2000-3000 token。

## Goals / Non-Goals

**Goals:**
- 实现 `search_tools` 工具，使 LLM 可通过关键词或精确名称发现并获取隐藏工具的完整 schema
- 将约 13 个低频工具标记为 `expose_to_llm = False`
- 在 system prompt 中说明 `search_tools` 的使用场景

**Non-Goals:**
- 不实现"动态运行时加载/注册"工具（工具仍在启动时注册，只是对 LLM 隐藏 schema）
- 不改变工具的执行逻辑
- 不引入工具优先级排序或自动推荐

## Decisions

### 决策 1：`search_tools` 返回完整 schema，不需要二次调用
LLM 调用 `search_tools` 后直接得到目标工具的完整 JSON Schema，可在同一轮对话中立即使用该工具。不需要像 function calling 的两阶段方式那样额外获取 schema。

### 决策 2：查询支持两种形式
- `select:name1,name2`：精确按名获取，适合 LLM 已知工具名但 schema 不在 context 中的场景
- 关键词搜索（任意字符串）：对工具名称和 description 做子字符串匹配，返回最多 5 个结果

不引入正则搜索（deer-flow 有第三种正则形式）——正则对 LLM 调用工具的场景过于复杂，关键词匹配已足够。

### 决策 3：工具隐藏范围保守，优先隐藏"原子版本"
`stat_test`（统一）保留可见，`t_test`/`mann_whitney`/`anova`/`kruskal_wallis`（原子版本）隐藏。LLM 用高层工具完成大多数任务，只有在需要精细控制时才通过 `search_tools` 取原子工具。

### 决策 4：system prompt 中明确说明何时应使用 search_tools
避免 LLM 因工具不在 context 中而直接猜测或放弃。system prompt 补充一条规则："当需要使用某工具但发现它不在工具列表中时，调用 `search_tools` 按名称或关键词获取其 schema"。

### 决策 5：SearchToolsTool 通过构造函数注入获取 ToolRegistry 引用
`SearchToolsTool.execute()` 需要访问 `ToolRegistry` 以查询所有工具（含隐藏工具）。采用与 `DispatchAgentsTool` 相同的构造注入模式：在 `create_default_tool_registry()` 中实例化 `SearchToolsTool` 时将 `registry` 自身引用作为构造参数传入（`SearchToolsTool(registry=registry)`），而非通过 `session` 参数在运行时动态查找。这样依赖关系在初始化时即明确，避免运行时耦合。

## Risks / Trade-offs

- **[风险] LLM 不知道某工具可以被搜索到** → 缓解：system prompt 明确说明，`search_tools` 自身的 description 也应清楚说明"可以发现所有工具包括隐藏工具"
- **[风险] 隐藏范围过大导致 LLM 找不到工具** → 缓解：保守策略，核心工具（数据加载、统计、代码执行、报告）全部保持可见；隐藏工具可通过 search_tools 精确名称获取
- **[权衡] search_tools 本身占用一个 tool slot** → 可忽略，替换掉的 13 个工具 schema token 远大于 search_tools 自身

## Migration Plan

- 分两步：先实现 `search_tools`，验证 LLM 能正确使用后，再逐批隐藏工具
- 回滚：将工具的 `expose_to_llm` 改回 `True` 即可

## Open Questions

（无）
