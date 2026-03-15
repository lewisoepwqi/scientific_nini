# Capability: result-fusion-engine

## Purpose

提供 `ResultFusionEngine`，负责将多个子 Agent 的执行结果融合为统一输出，支持自动策略选择（concatenate / summarize / hierarchical）、显式策略指定、冲突检测与标注。

## Requirements

### Requirement: FusionResult 数据结构
系统 SHALL 提供 `FusionResult` 数据类，字段：`content: str`（融合后文本内容）、`strategy: str`（实际使用的策略名称）、`conflicts: list[dict]`（冲突标注列表，默认空列表）、`sources: list[str]`（来源 Agent ID 列表）。

#### Scenario: FusionResult 合法创建
- **WHEN** 以合法字段实例化 `FusionResult`
- **THEN** 所有字段 SHALL 可通过属性访问
- **AND** `conflicts` 默认值 SHALL 为空列表

---

### Requirement: ResultFusionEngine 自动策略选择（strategy="auto"）
`ResultFusionEngine.fuse(results, strategy="auto")` SHALL 根据结果数量自动选择策略：
- 0 个结果 → `content=""` 的 `FusionResult`，strategy="concatenate"
- 1 个结果 → strategy=`"concatenate"`，直接返回该结果内容，零 LLM 调用
- 2-4 个结果 → strategy=`"summarize"`，通过 `model_resolver.chat(purpose="analysis")` 生成整合摘要
- >4 个结果 → strategy=`"hierarchical"`，分批 summarize 后再汇总

#### Scenario: 单结果无 LLM 调用
- **WHEN** 调用 `fuse([result1], strategy="auto")`
- **THEN** 返回的 `FusionResult.strategy` SHALL 等于 `"concatenate"`
- **AND** 内容 SHALL 等于 `result1.summary`
- **AND** SHALL 不发起任何 LLM 调用

#### Scenario: 多结果触发摘要策略
- **WHEN** 调用 `fuse([r1, r2, r3], strategy="auto")`
- **THEN** 返回的 `FusionResult.strategy` SHALL 等于 `"summarize"`
- **AND** `content` SHALL 非空

#### Scenario: 空结果集
- **WHEN** 调用 `fuse([], strategy="auto")`
- **THEN** 返回的 `FusionResult.content` SHALL 等于空字符串
- **AND** SHALL 不抛出异常

---

### Requirement: 显式策略支持
`ResultFusionEngine.fuse()` SHALL 支持显式指定 `strategy` 参数，接受 `"concatenate"` / `"summarize"` / `"consensus"` / `"hierarchical"` 四个值；不支持的策略名 SHALL 降级为 `"concatenate"` 并记录 WARNING。

#### Scenario: concatenate 策略
- **WHEN** 调用 `fuse(results, strategy="concatenate")`
- **THEN** 内容 SHALL 为各结果 `summary` 按顺序拼接，以换行分隔
- **AND** SHALL 不发起 LLM 调用

#### Scenario: summarize 超时降级
- **WHEN** LLM summarize 调用超过 60 秒
- **THEN** SHALL 降级为 `"concatenate"` 策略
- **AND** SHALL 不抛出异常

---

### Requirement: 冲突检测（仅标注不阻断）
`ResultFusionEngine` 在 `"summarize"` 或 `"consensus"` 策略下 SHALL 对结果内容进行冲突检测；检测结果仅追加到 `FusionResult.conflicts`，不修改 `content`，不阻断融合流程。

#### Scenario: 冲突标注不影响输出
- **WHEN** 两个 Agent 的结论存在分歧
- **AND** 冲突检测命中
- **THEN** `FusionResult.conflicts` SHALL 包含冲突标注条目
- **AND** `FusionResult.content` SHALL 仍为完整融合内容
