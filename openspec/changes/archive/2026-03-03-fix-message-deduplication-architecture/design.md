## Context

### 当前架构问题

Nini 项目采用 ReAct 循环架构，后端通过 WebSocket 流式推送 TEXT 事件到前端。当前消息流如下：

```
┌─────────────────────────────────────────────────────────────────┐
│  问题场景: generate_report 工具                                  │
├─────────────────────────────────────────────────────────────────┤
│  1. LLM 流式生成报告内容                                         │
│     → TEXT("分析完成") → TEXT("相关矩阵...")                      │
│     → 前端累积: _streamingText = "分析完成 相关矩阵..."            │
│                                                                 │
│  2. generate_report 执行成功                                     │
│     → 返回 report_markdown (完整报告)                            │
│                                                                 │
│  3. runner.py:1136 再次发送 TEXT(report_markdown)               │
│     → 前端无法识别是重复内容，追加显示                            │
│     → 【结果】用户看到重复内容！                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 根本原因

1. **消息语义不明确**: TEXT 事件既可能是流式增量，也可能是完整消息替换
2. **缺乏消息标识**: 无法区分同一消息的不同更新 vs 全新消息
3. **状态管理混乱**: 前端 `_streamingText` 临时状态与后端持久化状态不同步

### 行业最佳实践参考

- **OpenAI/Claude API**: 使用 `message_id` 关联所有流式更新，明确的 `message_stop` 标记结束
- **ChatGPT UI**: 采用事件溯源模式，通过 `sequence_number` 追踪消息版本
- **SignalR + OpenAI 示例**: 使用消息累积 + 缓冲区发送，避免重复

## Goals / Non-Goals

**Goals:**
- 根治消息重复显示问题，确保同一内容不会多次渲染
- 建立清晰的消息生命周期语义（append/replace/complete）
- 实现前后端消息状态的一致性
- 保持向后兼容，旧客户端可正常工作

**Non-Goals:**
- 不引入新的持久化存储（继续使用现有 conversation_memory）
- 不改写整个事件系统（在现有 WebSocket 架构上增强）
- 不实现完整的事件溯源模式（仅引入消息ID去重）

## Decisions

### Decision 1: 消息ID生成策略

**选择**: 后端生成消息ID，使用 `{turn_id}-{sequence}` 格式

**理由**:
- 后端是消息的来源，理应负责ID生成
- `turn_id` 已存在，可确保同一对话轮次的消息关联
- `sequence` 确保同一轮次内多条消息的排序

**替代方案**: 前端生成消息ID
- 拒绝原因：前端生成可能导致ID冲突，且无法处理后端主动推送的场景

### Decision 2: 消息操作类型设计

**选择**: 三种操作类型：`append` | `replace` | `complete`

| 操作类型 | 语义 | 使用场景 |
|---------|------|---------|
| `append` | 追加到当前消息 | 正常流式生成 |
| `replace` | 替换整个消息内容 | generate_report 等工具返回完整内容 |
| `complete` | 标记消息结束 | 流式生成完成，最终确认 |

**理由**:
- 明确区分增量更新和完整替换场景
- `complete` 操作可触发前端清理临时状态
- 与 OpenAI/Claude API 的流式结束标记语义一致

### Decision 3: 向后兼容策略

**选择**: 新字段为可选，无新字段时按原逻辑处理

```typescript
// 新逻辑
if (evt.metadata?.message_id) {
  // 基于消息ID去重
} else {
  // 旧逻辑：简单追加
  newStreamText = get()._streamingText + text;
}
```

**理由**:
- 允许前后端独立部署
- 旧客户端可继续工作（只是没有修复效果）
- 降低部署风险

### Decision 4: 前端状态管理优化

**选择**: 引入 `_messageBuffer` 记录每个消息ID的累积内容

```typescript
interface MessageBuffer {
  [messageId: string]: {
    content: string;
    operation: 'append' | 'replace' | 'complete';
    timestamp: number;
  }
}
```

**理由**:
- 支持非连续的消息更新（如 replace 操作）
- 便于实现去重逻辑
- 与现有 `_streamingText` 分离，避免状态混乱

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 消息ID冲突 | 使用 `turn_id` + 递增序列号确保唯一性 |
| 内存泄漏（消息Buffer无限增长） | 设置Buffer大小上限，complete后清理 |
| 网络乱序导致消息丢失 | 保留序列号检查，乱序消息等待或丢弃 |
| 向后兼容复杂性 | 新字段为可选，旧代码路径保留 |
| 前后端部署不同步 | 先部署后端，再部署前端；或同时部署 |

## Migration Plan

### 部署步骤

1. **Phase 1: 后端部署**
   - 部署修改后的 `runner.py` 和 `schemas.py`
   - 验证新字段正确发送

2. **Phase 2: 前端部署**
   - 部署修改后的 `event-handler.ts` 和 `types.ts`
   - 验证消息去重生效

3. **Phase 3: 验证**
   - 测试 generate_report 场景
   - 测试普通对话场景
   - 测试刷新页面后状态一致性

### 回滚策略

- 后端回滚：前端新代码可兼容旧后端（无新字段时按旧逻辑）
- 前端回滚：需同时回滚后端，否则消息可能显示异常

## Open Questions

1. **消息Buffer清理时机**: 是在 `complete` 后立即清理，还是保留一段时间用于去重？
   - 建议：complete 后 5 分钟内保留，之后清理

2. **序列号重置策略**: 新对话轮次重置序列号，是否会导致跨轮次消息ID冲突？
   - 当前设计：`{turn_id}-{seq}` 确保跨轮次唯一

3. **是否需要持久化消息ID**: 是否需要将消息ID保存到 conversation_memory？
   - 建议：当前版本不持久化，仅运行时去重
