## Context

工具调用入口是 `ToolRegistry.execute()`（最终由 `tool_executor.py` 的 `execute_with_fallback` 调用）。当前流程：LLM 产出 tool_call → `tool_executor.py` 解析参数 → `registry.execute_with_fallback()` → `registry.execute()` → `Tool.execute()`。

guardrail 的最佳插入点是 `ToolRegistry.execute()` 内部、实际 `Tool.execute()` 调用之前，这样所有工具调用路径（含 fallback 路径）都经过检查。

已有安全机制：
- `sandbox/policy.py`：AST 静态分析，仅保护 `run_code`/`run_r_code` 的代码执行
- `sandbox/executor.py`：multiprocessing 进程隔离，同上

这两层保护不覆盖其他工具的"调用语义"层面：例如 `clean_data` 工具的 `inplace=True` 参数会修改原始 DataFrame，`organize_workspace` 可能删除文件。

## Goals / Non-Goals

**Goals:**
- 在 `ToolRegistry.execute()` 中插入可插拔的 guardrail 检查链
- 实现第一个具体规则：`DangerousPatternGuardrail`，拦截针对科研原始数据的破坏性操作
- BLOCK 决策以标准 `ToolResult(success=False)` 格式返回，对调用方透明
- 设计可扩展接口（后续 change 可增加新规则，无需修改框架代码）

**Non-Goals:**
- 不实现 `REQUIRE_CONFIRMATION` 决策的挂起/等待机制（本次仅定义枚举，实际执行降级为 BLOCK）
- 不引入基于 LLM 的语义评估（纯规则型）
- 不覆盖沙箱层已有的代码执行安全（不重复保护 `run_code`/`run_r_code`）

## Decisions

### 决策 1：插入点选 `ToolRegistry.execute()` 而非 `tool_executor.py`
`tool_executor.py` 是 agent 层的调用者，不属于工具层。guardrail 属于工具调用的安全策略，应在工具注册中心内部实施，与 agent 层解耦。此外，`execute_with_fallback` 最终也调用 `execute()`，选此点保证单一拦截。

### 决策 2：`REQUIRE_CONFIRMATION` 本次降级为 BLOCK
挂起工具执行并等待用户确认需要与 `ask_user_question` 机制联动，属于未来扩展。本次仅定义该枚举值，决策引擎返回 `REQUIRE_CONFIRMATION` 时运行时同等处理为 BLOCK，附加提示信息"需要用户确认后才能执行"。

### 决策 3：初始只实现一个具体 guardrail 规则类
`DangerousPatternGuardrail` 覆盖最高风险场景（原始数据集覆写、工作区大范围删除）。接口设计为链式，后续可轻松添加新规则，不修改 `registry.py`。

### 决策 4：被 BLOCK 的调用记录日志但不抛出异常
返回 `ToolResult(success=False, message="操作被安全策略拦截：...")` 并写 warning 日志。LLM 收到失败结果后可以自行调整策略，会话不中断。

## Risks / Trade-offs

- **[风险] 规则误拦截合法操作** → 缓解：初始规则集保守（仅针对明确的破坏性模式），优先漏报而非误报；规则以白名单+黑名单组合，可快速调整
- **[风险] 规则维护成本** → 缓解：规则集中在 `guardrails.py` 的常量中，修改无需改业务逻辑
- **[权衡] 每次工具调用增加规则检查开销** → 纯内存操作，预计 < 1ms，可忽略

## Migration Plan

- `ToolRegistry.execute()` 修改为先调用 guardrail 链，ALLOW 则继续原有流程，无现有行为改变
- 回滚：移除 guardrail 调用点，恢复原 `execute()` 实现即可

## Open Questions

（无）
