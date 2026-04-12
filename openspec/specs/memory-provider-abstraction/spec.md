# memory-provider-abstraction Specification

## Purpose
TBD - created by syncing change memory-provider-architecture.

## Requirements

### Requirement: MemoryProvider 定义统一的记忆生命周期接口
系统 SHALL 提供 `MemoryProvider` 抽象基类，定义所有记忆 provider 必须实现或可选继承的生命周期钩子，包含 `initialize`、`prefetch`、`sync_turn`、`on_session_end`、`on_pre_compress`、`get_tool_schemas`、`handle_tool_call`、`shutdown`，以解耦 agent 核心与具体存储实现。

#### Scenario: 未实现全部抽象方法的子类不可实例化
- **WHEN** 定义一个继承 `MemoryProvider` 的类但未实现 `name`、`initialize`、`get_tool_schemas` 中任一方法
- **THEN** 尝试实例化该类 SHALL 抛出 `TypeError`

#### Scenario: 实现全部抽象方法的子类可实例化，可选钩子有默认实现
- **WHEN** 定义一个实现了 `name`、`initialize`、`get_tool_schemas` 的 `MemoryProvider` 子类
- **THEN** 该类 SHALL 可被实例化
- **AND** `system_prompt_block()` SHALL 返回空字符串
- **AND** `on_pre_compress([])` SHALL 返回空字符串
- **AND** `prefetch(query)` SHALL 返回空字符串

### Requirement: MemoryManager 编排内置 provider 与可选的外部 provider
系统 SHALL 提供 `MemoryManager` 类，要求内置 provider（`name="builtin"`）始终存在于 `providers` 列表首位，允许注册任意数量的外部 provider，并为所有 provider 的钩子调用提供异常隔离。

当前版本（P005）只实现 `ScientificMemoryProvider` 这一个内置 provider，不实现任何外部 provider。

#### Scenario: 内置 provider 注册成功
- **WHEN** 向 `MemoryManager` 注册 `name="builtin"` 的 provider
- **THEN** 该 provider SHALL 出现在 `providers` 列表中

#### Scenario: 可以注册多个外部 provider
- **WHEN** 依次向 `MemoryManager` 注册 `name="ext1"` 和 `name="ext2"` 的 provider
- **THEN** 两个 provider SHALL 均出现在 `providers` 列表中
- **AND** 均参与 `prefetch_all` / `sync_all` / `on_session_end` 调用

#### Scenario: Provider 的 prefetch 钩子抛出异常时不影响其他 provider
- **WHEN** `MemoryManager.prefetch_all()` 被调用
- **AND** 其中某个 provider 的 `prefetch()` 抛出 `RuntimeError`
- **THEN** 其余 provider 的结果 SHALL 正常返回
- **AND** 系统 SHALL 记录警告日志
- **AND** `prefetch_all()` SHALL NOT 向调用方抛出异常

#### Scenario: prefetch_all 汇总所有 provider 的召回结果
- **WHEN** `MemoryManager` 持有 2 个 provider，各自的 `prefetch()` 返回非空字符串
- **AND** `prefetch_all(query)` 被调用
- **THEN** 返回值 SHALL 包含两个 provider 的内容
- **AND** 内容之间 SHALL 以换行分隔

### Requirement: Memory Context Fencing 防止历史记忆被 LLM 误当当前输入
系统 SHALL 提供 `build_memory_context_block()` 函数，将召回记忆包裹在 `<memory-context>` 标签内，并附加系统注记说明该内容为历史参考背景而非当前用户输入。

#### Scenario: 非空输入被正确包裹
- **WHEN** `build_memory_context_block("重要记忆内容")` 被调用
- **THEN** 返回值 SHALL 包含 `<memory-context>` 开标签和 `</memory-context>` 闭标签
- **AND** 返回值 SHALL 包含原始记忆内容
- **AND** 返回值 SHALL 包含中文系统注记

#### Scenario: 空输入返回空字符串
- **WHEN** `build_memory_context_block("")` 或 `build_memory_context_block("   ")` 被调用
- **THEN** 返回值 SHALL 为空字符串

#### Scenario: 嵌套 fence 标签被剥离（防注入）
- **WHEN** 输入包含 `<memory-context>` 或 `</memory-context>` 子字符串
- **THEN** 返回值 SHALL NOT 包含嵌套的 fence 标签
- **AND** 其余内容 SHALL 正常保留

### Requirement: MemoryManager 提供全局单例访问
系统 SHALL 提供 `get_memory_manager()` 和 `set_memory_manager()` 函数，允许跨模块访问同一个 `MemoryManager` 实例，无需通过构造函数传递依赖。

#### Scenario: 未设置时 get_memory_manager 返回空实例
- **WHEN** 进程启动后未调用 `set_memory_manager()`
- **AND** `get_memory_manager()` 被调用
- **THEN** SHALL 返回一个空的 `MemoryManager`（无 providers）而非抛出异常

#### Scenario: set 后 get 返回同一实例
- **WHEN** `set_memory_manager(mgr)` 被调用
- **AND** `get_memory_manager()` 被调用
- **THEN** 返回值 SHALL 与传入的 `mgr` 为同一对象
