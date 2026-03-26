---
name: writing-guide
description: |
  论文写作引导工作流，负责将当前会话中的分析结果桥接为可写作的素材包、
  章节结构与分节撰写提示。适用于论文初稿、实验报告和结果章节整理。
category: workflow
research-domain: general
difficulty-level: advanced
typical-use-cases:
  - 将统计分析结果整理为论文写作素材
  - 先规划章节再逐节撰写结果与讨论
  - 在无分析结果时切换为纯引导式写作
allowed-tools:
  - collect_artifacts
  - workspace_session
  - task_write
  - analysis_memory
user-invocable: true
disable-model-invocation: false
contract:
  version: "1"
  trust_ceiling: t1
  steps:
    - id: collect_materials
      name: 素材收集
      description: 调用 collect_artifacts 收集统计结果、图表、方法记录和数据集概要
      tool_hint: collect_artifacts
      depends_on: []
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: plan_structure
      name: 结构规划
      description: 基于素材包确定论文结构、章节重点与证据分布
      tool_hint: null
      depends_on:
        - collect_materials
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: write_sections
      name: 分节撰写
      description: 逐节生成写作提示，嵌入统计结果模板与图表引用占位
      tool_hint: null
      depends_on:
        - plan_structure
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: review_revise
      name: 修订复核
      description: 检查数据与结论一致性，输出修订建议与缺口清单
      tool_hint: null
      depends_on:
        - write_sections
      trust_level: t1
      review_gate: false
      retry_policy: skip
  input_schema:
    type: object
    properties:
      writing_goal:
        type: string
        description: 论文、报告或章节写作目标
      target_sections:
        type: array
        items:
          type: string
        description: 需要优先撰写的章节
  output_schema:
    type: object
    properties:
      materials_bundle:
        type: object
        description: collect_artifacts 返回的写作素材包
      writing_outline:
        type: string
        description: 结构规划与章节提示
      revision_notes:
        type: array
        description: 修订建议列表
---

# 论文写作引导工作流

> **输出等级声明**：本 Skill 的所有输出均为 **O2 草稿级**，仅用于协助作者整理写作思路，最终内容必须由作者审阅、改写并承担学术责任。

本 Skill 采用四步线性流程：**素材收集 → 结构规划 → 分节撰写 → 修订建议**。如果当前会话已有分析结果，优先复用真实统计值与图表；如果没有，则退化为纯引导模式，不得捏造结果。

## 第一步：素材收集（collect_materials）

1. 调用 `collect_artifacts` 获取结构化素材包，重点检查以下字段：
   - `statistical_results`
   - `charts`
   - `methods`
   - `datasets`
   - `summary`
2. 若 `summary.mode == "pure_guidance"`，必须明确说明：
   - 当前会话暂无可引用的统计结果或图表
   - 后续只能提供结构规划与写作提示，不能生成带真实数值的结果描述
3. 若已有分析产物，先整理成写作证据清单：
   - 哪些统计结果适合进入 Results
   - 哪些方法记录适合进入 Methods
   - 哪些图表适合在 Results / Appendix 中引用

## 第二步：结构规划（plan_structure）

根据素材包和用户目标，推荐论文结构。最小结构建议为：

1. 摘要
2. 引言
3. 方法
4. 结果
5. 讨论
6. 结论

规划时必须输出每章的输入来源：

- 方法章节：优先引用 `methods`
- 结果章节：优先引用 `statistical_results` 与 `charts`
- 讨论章节：基于结果做解释，但不得超出已有证据

如果用户只想写局部章节，应改写为章节级规划，例如只输出 Results + Discussion 的分节框架。

## 第三步：分节撰写（write_sections）

逐节引导作者撰写时，必须显式区分「可直接引用的真实结果」与「待作者补写内容」。

### Results 章节模板

当 `statistical_results` 非空时，可使用如下模板：

```markdown
### 主要结果
在 {dataset_name} 中，采用 {method_name} 得到 {test_statistic_label} = {test_statistic}，
p = {p_value}，效应量 {effect_type} = {effect_size}。

### 图表引用
如图 1 所示，{图表核心趋势或差异的文字描述}。
```

如果只有部分字段存在，缺失项必须改成占位提示，例如 `[效应量待补充]`，不得编造。

### 图表嵌入模板

```markdown
![图1：{图表标题}]({download_url})
```

若图表为 HTML 或交互文件，则改为链接形式：

```markdown
[查看图1：{图表标题}]({download_url})
```

### Methods 章节模板

当 `methods` 非空时，按以下结构提示作者整合方法描述：

```markdown
本研究在 {step_name} 阶段使用 {method_name}。
关键参数：{key_parameters}
如存在缺失信息：{missing_fields}
```

### 纯引导模式

若没有分析产物，则仅输出章节提纲与提问清单，例如：

- 你的主要研究问题是什么？
- 结果章节需要报告哪些指标？
- 是否已经有可引用的图表与检验结果？

## 第四步：修订复核（review_revise）

完成章节草稿后，给出修订建议时至少检查：

1. 统计值是否与素材包一致
2. 图表引用是否有对应文件或链接
3. 方法描述是否覆盖关键参数与数据来源
4. 讨论中的结论是否超出了结果支持范围

修订输出建议使用以下格式：

```markdown
## 修订建议（O2 草稿级）
- 数值核对：
- 图表引用核对：
- 方法描述补足：
- 讨论收敛建议：
```

## 执行约束

- 不得捏造统计量、p 值、效应量、图表标题或方法步骤
- 如果素材包为空，必须明确说明当前为纯引导模式
- 所有带数值的段落都应默认标注“需作者审阅和修改”
