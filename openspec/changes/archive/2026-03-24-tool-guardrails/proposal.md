## Why

`tools/registry.py` 的 `invoke()` 方法直接执行工具调用，没有任何前置安全检查。当 LLM 出现幻觉或被误导时，可能在科研数据上执行破坏性操作（覆盖原始数据集、清除工作区、执行危险代码）。现有的沙箱安全（AST 静态分析 + multiprocessing 隔离）只保护代码执行工具，不覆盖其他 30+ 工具的调用语义层面安全。

## What Changes

- 新建 `src/nini/tools/guardrails.py`：定义 `ToolGuardrail` 抽象基类和 `GuardrailDecision`（ALLOW / BLOCK / REQUIRE_CONFIRMATION）
- 实现 `DangerousPatternGuardrail`：对预定义的高风险工具+参数组合（如覆盖原始数据集、删除工作区文件）返回 BLOCK 或 REQUIRE_CONFIRMATION
- 修改 `src/nini/tools/registry.py` 的 `execute()` 方法：在执行前调用 guardrail 链，BLOCK 时直接返回拒绝响应，REQUIRE_CONFIRMATION 时（未来扩展）可挂起等待确认
- 新增 `tests/test_guardrails.py`

## Capabilities

### New Capabilities

- `tool-guardrails`：工具调用前置安全防护，可插拔 guardrail 链 + 初始危险模式检测规则

### Modified Capabilities

（无现有规格变更）

## Impact

- **修改文件**：`src/nini/tools/registry.py`（`execute()` 方法插入 guardrail 调用）
- **新增文件**：`src/nini/tools/guardrails.py`、`tests/test_guardrails.py`
- **无 API 变更**：BLOCK 决策以 `ToolResult(success=False, ...)` 格式返回，对上层调用方透明
- **无新依赖**：纯规则型实现，无需额外 LLM 调用
