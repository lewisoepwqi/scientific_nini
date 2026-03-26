## Context

C4 的 ContractRunner 实现了线性 DAG 执行（拓扑排序 + 逐步串行）。SkillStep 已有 depends_on 字段。本 change 扩展执行引擎，利用 depends_on 的 DAG 语义支持并行。

## Goals / Non-Goals

**Goals:**
- 支持并行分支执行
- 支持条件步骤
- 支持步骤间数据传递
- 向后兼容线性 DAG

**Non-Goals:**
- 不实现动态 DAG
- 不实现分布式执行

## Decisions

### D1: 并行执行策略

**选择**：基于拓扑排序分层：同一层的步骤（依赖均已完成）使用 `asyncio.gather` 并发执行。

```
层 0: [A]           → 串行
层 1: [B, C]        → 并行（A 完成后 B、C 同时执行）
层 2: [D]           → 串行（B 和 C 都完成后执行 D）
```

**理由**：分层并行是最直观的实现，复用现有拓扑排序逻辑。asyncio.gather 天然支持并发。

### D2: SkillStep 扩展字段

**选择**：

```python
# 新增字段
condition: str | None = None        # 条件表达式（引用前置步骤输出）
input_from: dict[str, str] = {}     # 输入绑定：{参数名: "step_id.output_key"}
output_key: str | None = None       # 输出键名（存入步骤上下文）
```

**理由**：condition 使用简单表达式（如 `"normality_test.p_value < 0.05"`），由 Python eval 在受控上下文中执行。input_from 实现显式的数据流绑定。output_key 将步骤输出存入共享上下文。

### D3: 条件步骤实现

**选择**：条件步骤的 `condition` 字段引用前置步骤的输出。执行引擎在步骤启动前评估条件，条件为 False 时标记为 skipped。

**理由**：简单直接。V1 场景中条件表达式很简单（如检查 p 值）。

**安全措施**：condition 表达式仅能访问步骤输出上下文中的值，不能调用任何函数或访问外部资源。使用 `ast.literal_eval` 风格的安全评估。

### D4: 向后兼容

**选择**：线性 DAG（每步依赖前一步）的分层结果为每层一个步骤，执行效果与现有串行模式一致。现有 Skill 无需修改 contract 即可在新引擎上运行。

**理由**：分层并行是串行执行的超集。

## Risks / Trade-offs

- **[风险] 并行步骤的错误处理更复杂** → asyncio.gather 使用 return_exceptions=True，每个步骤独立处理失败。
- **[风险] condition eval 的安全性** → 仅允许访问步骤输出的值，使用白名单变量上下文。
- **[回滚]** revert 两个文件即可恢复。
