# Skill 执行契约规范（草案）

> 版本：v0.1
> 日期：2026-03-26
> 状态：待评审
> 关联文档：`docs/nini-vision-charter.md`

---

## 1. 文档目标

本文档定义 Nini 中 Skill 的最小执行契约，用于统一工作流模板的描述方式、运行时要求、降级语义与可观测字段。

本文档解决的问题不是“如何实现某个具体 Skill”，而是“一个 Skill 至少需要声明什么，运行时至少应保证什么”。

---

## 2. 适用范围

本规范适用于以下类型的 Skill：

- 可执行工作流模板
- 由多个步骤组成的深任务模板
- 需要联网、插件、人工确认或降级策略的任务模板

以下内容不属于本规范直接覆盖范围：

- 仅用于提示增强的纯说明型文档
- 原子 Tool 的函数签名规范
- Capability 内部执行器的具体实现细节

仅有说明文档而无执行语义的 Skill，不应被表述为“可执行工作流”。

---

## 3. 设计原则

Skill 契约必须遵守以下原则：

- 最小完备：字段不求多，但必须足以驱动执行、观测和降级
- 显式边界：高风险场景、联网条件和人工确认点必须显式声明
- 可降级：依赖不可用时，必须给出明确降级路径或失败终态
- 可审计：运行时必须能记录关键状态、输入摘要和证据来源
- 可演进：允许字段扩展，但不破坏既有契约的基础语义

---

## 4. Skill 最小元数据

每个 Skill 至少应声明以下元数据：

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | Skill 内部唯一标识，使用 `snake_case` |
| `display_name` | 是 | 展示名称 |
| `version` | 是 | Skill 契约版本 |
| `phase` | 是 | 所属研究阶段 |
| `summary` | 是 | Skill 的一句话说明 |
| `risk_level` | 是 | `low / medium / high / critical` |
| `trust_ceiling` | 是 | 输出可信度上限：`T1 / T2 / T3` |
| `requires_human_review` | 是 | 是否存在强制人工复核点 |
| `input_schema` | 是 | 输入参数契约 |
| `output_schema` | 是 | 输出产物契约 |
| `steps` | 是 | 步骤列表 |
| `fallback` | 否 | 全局降级策略 |
| `required_plugins` | 否 | 必需插件 |
| `optional_plugins` | 否 | 可选增强插件 |
| `observability` | 是 | 运行时记录要求 |

---

## 5. 输入契约

输入契约应至少定义：

- 必填参数
- 可选参数
- 参数类型
- 默认值
- 取值范围或枚举
- 缺失参数的交互策略

推荐结构：

```yaml
input_schema:
  required:
    - key: topic
      type: string
      description: 研究主题
  optional:
    - key: date_range
      type: string
      description: 时间范围
    - key: max_items
      type: integer
      default: 20
  prompt_for_missing: true
```

规则：

- 运行时不得假设缺失参数总能自动推断
- 高风险参数必须明确要求用户确认
- 需要人工选择的策略参数，不应用隐式默认值替代用户确认

---

## 6. 输出契约

输出契约应至少定义：

- 主产物类型
- 主产物格式
- 可选附属产物
- 输出可信度说明
- 是否允许进入最终摘要

推荐结构：

```yaml
output_schema:
  primary:
    type: report
    format: [markdown, docx]
    trust_level: T2
    eligible_for_final_summary: false
  secondary:
    - type: reference_list
    - type: evidence_bundle
```

规则：

- 高风险 Skill 的默认输出不得直接标记为最终结论
- 若输出依赖联网来源，必须同时声明来源可得性和证据边界

---

## 7. 步骤语义

每个步骤至少应声明以下字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 步骤标识 |
| `type` | 是 | 步骤类型，如 `tool`、`capability`、`review_gate` |
| `executor` | 是 | 执行单元名称 |
| `depends_on` | 否 | 前置步骤列表 |
| `inputs` | 否 | 本步骤输入映射 |
| `outputs` | 否 | 本步骤输出声明 |
| `retry` | 否 | 重试规则 |
| `on_failure` | 否 | 失败处理策略 |
| `requires_human_review` | 否 | 是否必须人工确认 |
| `evidence_required` | 否 | 是否要求证据绑定 |

推荐结构：

```yaml
steps:
  - id: search
    type: capability
    executor: literature_search
    inputs:
      query: "$topic"
    outputs:
      - search_results
    retry:
      max_attempts: 2
    on_failure:
      action: fallback
      target: local_knowledge

  - id: review_gate
    type: review_gate
    executor: human_confirmation
    depends_on: [search]
    requires_human_review: true
```

规则：

- `depends_on` 必须构成有向无环图
- 需要人工确认的步骤不得被静默跳过
- 高风险步骤若缺少证据，不得进入最终总结链路

---

## 8. 降级与失败终态

Skill 必须区分以下三类结果：

- 正常完成
- 降级完成
- 失败终止

推荐结构：

```yaml
fallback:
  when_plugin_unavailable:
    action: degrade
    trust_level: T1
    user_message: "学术搜索插件不可用，当前切换为离线草稿模式。"
  when_evidence_missing:
    action: block_final_summary
    user_message: "证据不足，当前结果不会进入最终摘要。"
```

规则：

- 降级不是“无提示地继续”
- 降级后必须同步降低可信度等级
- 对高风险输出，缺证据时优先阻断，而不是默认继续

---

## 9. 人工复核门

以下任一情况出现时，应引入人工复核门：

- 输出属于高风险或极高风险
- 关键参数具有明显方法学后果
- 输出将进入可导出级或最终摘要
- 外部来源存在冲突或证据不足

人工复核门至少应记录：

- 待确认内容摘要
- 风险说明
- 用户确认结果
- 确认时间

---

## 10. 可观测性要求

每个 Skill 运行时至少应输出以下观测信息：

- `skill_started`
- `step_started`
- `step_completed`
- `step_failed`
- `step_degraded`
- `review_requested`
- `review_completed`
- `skill_completed`

每条事件至少包含：

- `skill_name`
- `skill_version`
- `step_id`
- `timestamp`
- `status`
- `input_summary`
- `output_summary`
- `error_summary`
- `trust_level`

规则：

- 记录摘要而非原始敏感数据
- 保证日志可追溯，但不扩大隐私暴露面

---

## 11. 可信度与风险联动规则

Skill 的输出可信度不得超过其 `trust_ceiling`。

建议采用以下联动规则：

| 风险等级 | 默认可信度上限 | 是否允许无人工复核进入最终摘要 |
|----------|----------------|-------------------------------|
| `low` | `T2` | 允许 |
| `medium` | `T2` | 视证据完整性而定 |
| `high` | `T2` | 默认不允许 |
| `critical` | `T1` 或 `T2` | 不允许 |

规则：

- `high` 和 `critical` Skill 不得默认输出“最终正确答案”
- 若缺少联网来源或关键证据，可信度应自动下调

---

## 12. 示例契约

```yaml
name: literature_review_draft
display_name: 文献综述草稿
version: "0.1"
phase: literature_review
summary: 围绕研究主题生成综述结构草稿和引用清单
risk_level: medium
trust_ceiling: T2
requires_human_review: false

input_schema:
  required:
    - key: topic
      type: string
      description: 研究主题
  optional:
    - key: date_range
      type: string
    - key: max_items
      type: integer
      default: 20
  prompt_for_missing: true

output_schema:
  primary:
    type: report
    format: [markdown]
    trust_level: T2
    eligible_for_final_summary: false
  secondary:
    - type: reference_list

steps:
  - id: search
    type: capability
    executor: literature_search
    inputs:
      query: "$topic"
      date_range: "$date_range"
    outputs:
      - search_results
    retry:
      max_attempts: 2
    on_failure:
      action: fallback
      target: local_knowledge

  - id: synthesize
    type: capability
    executor: knowledge_synthesis
    depends_on: [search]
    inputs:
      sources: "$search_results"
    outputs:
      - outline
      - references
    evidence_required: true

fallback:
  when_plugin_unavailable:
    action: degrade
    trust_level: T1
    user_message: "学术搜索插件不可用，当前切换为离线草稿模式。"

observability:
  emit_events: true
  include_input_summary: true
  include_output_summary: true
```

---

## 13. 验收清单

一个新的可执行 Skill 至少应通过以下检查：

- 元数据完整
- 输入输出契约完整
- 步骤图无环
- 降级策略明确
- 高风险场景含人工复核门
- 可信度上限声明明确
- 运行时事件字段完整
- 离线与插件缺失场景可验证

---

## 14. 与其他文档的关系

- `docs/nini-vision-charter.md`：定义为什么做、做什么、不做什么
- `docs/skill-contract-spec.md`：定义 Skill 至少如何描述和执行
- `docs/high-risk-capability-review.md`：定义高风险能力如何评审与上线

---

> 下一步建议：在实现前，先选 1 到 2 个 V1 Skill 按本规范补出真实样例，验证字段是否足够支撑运行时。
