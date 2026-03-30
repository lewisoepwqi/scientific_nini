---
name: experiment-design-helper
description: |
  实验设计引导工作流，覆盖问题定义、设计选择、样本量计算、方案生成四个步骤。
  当用户提到：实验设计、样本量估算、研究方案、RCT、随机对照试验、功效分析、
  效应量、检验功效、实验方案、研究设计时使用。适用于临床研究、基础科研和量化研究设计阶段。
category: experiment_design
agents:
  - nini
tags:
  - experiment-design
  - sample-size
  - power-analysis
  - research-planning
  - rct
aliases:
  - 实验设计
  - 样本量计算
  - 研究方案设计
  - experiment design
  - sample size calculation
allowed-tools:
  - sample_size
  - stat_test
  - task_state
user-invocable: true
disable-model-invocation: false
contract:
  version: "1"
  trust_ceiling: t1
  steps:
    - id: define_problem
      name: 问题定义
      description: 引导用户明确研究假设、自变量/因变量、比较目标和研究背景
      tool_hint: task_state
      depends_on: []
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: choose_design
      name: 设计选择
      description: 基于问题类型推荐实验设计方案（RCT、配对、析因、交叉等）
      tool_hint: null
      depends_on:
        - define_problem
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: calculate_params
      name: 参数计算
      description: 调用 sample_size 工具计算所需样本量，明确效应量、显著性水平和检验功效
      tool_hint: sample_size
      depends_on:
        - choose_design
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: generate_plan
      name: 方案生成
      description: 生成实验方案草稿，标注 O2 草稿级，包含伦理提示和局限性声明
      tool_hint: null
      depends_on:
        - calculate_params
      trust_level: t1
      review_gate: true
      retry_policy: skip
  input_schema:
    type: object
    properties:
      research_question:
        type: string
        description: 研究问题或假设描述
      domain:
        type: string
        description: 研究领域（如临床医学、生物学、心理学等）
  output_schema:
    type: object
    properties:
      experiment_plan:
        type: string
        description: 实验方案草稿（O2 级）
      sample_size:
        type: integer
        description: 每组所需样本量
  evidence_required: false
---

# 实验设计引导工作流

> **输出等级声明**：本 Skill 所有输出标注为 **O2 草稿级**（可编辑初稿，需专业人员审核）。
> trust_ceiling = T1（草稿级），实验方案生成前将触发人工复核门（review_gate）。

本技能引导研究者完成实验设计四步骤：**问题定义 → 设计选择 → 参数计算 → 方案生成**。
最终方案供参考使用，不可直接用于临床实施或正式申报。

---

## 步骤一：问题定义（define_problem）

### 目标

帮助用户将模糊的研究意图转化为可检验的科学假设，明确实验的核心要素。

### LLM 提示模板

```
你是一名生物统计顾问，正在协助研究者进行实验设计。
请基于用户描述，通过提问引导其明确以下要素：

1. **研究问题**：想回答什么科学问题？
2. **主要假设**：零假设（H₀）和备择假设（H₁）是什么？
3. **主要结局指标**：主要观测的变量是什么（如血压、基因表达量）？
4. **自变量/干预因素**：实验组和对照组如何区分？
5. **研究对象**：纳入/排除标准是什么？
6. **时间框架**：观察期多长？

每次只问一个问题，等待用户回答后再继续。
输出格式：提出问题 + 示例答案（帮助用户理解）
```

### 输出规范

- 以结构化摘要形式呈现研究问题核心要素
- 明确标注哪些信息已确认、哪些仍需补充
- 等级标注：**O2 草稿级**

---

## 步骤二：设计选择（choose_design）

### 目标

基于步骤一的问题定义，推荐最适合的实验设计类型，说明选择理由和适用前提。

### LLM 提示模板

```
基于以下研究问题摘要：
{define_problem_output}

请为研究者推荐合适的实验设计方案。重点考量：

**主要设计类型**：
- **RCT（随机对照试验）**：适合干预性研究，因果关系最强，但成本高
- **配对设计**：适合个体差异大的情况，提高检验功效
- **析因设计**：适合同时研究多个因素及其交互作用
- **交叉设计**：适合慢性病或稳定结局，同一受试者接受多种干预

**推荐原则**：
1. 说明推荐的设计类型及其核心理由
2. 说明该设计的统计检验方法（t 检验、ANOVA 等）
3. 列出主要假设和局限性
4. 建议效应量的参考范围（引用文献领域惯例）

输出包含：设计类型、适用理由、统计方法、建议效应量参考值。
标注：本推荐为 O2 草稿级，需结合具体学科规范和文献调研调整。
```

### 输出规范

- 推荐 1-2 种设计方案，含理由对比
- 注明文献领域常用效应量参考范围（小/中/大效应）
- 等级标注：**O2 草稿级**

---

## 步骤三：参数计算（calculate_params）

### 目标

调用 `sample_size` 工具，基于效应量、显著性水平和检验功效计算所需样本量。

### LLM 提示模板

```
基于步骤二确定的实验设计，现在计算样本量。

请引导用户确认以下参数：
1. **设计类型**：two_sample_ttest / anova / proportion
2. **效应量**：使用步骤二推荐的参考范围，或请用户提供文献中的估计值
3. **显著性水平（α）**：通常 0.05，高风险研究用 0.01
4. **检验功效（1-β）**：通常 0.8，高要求研究用 0.9
5. **组数**（ANOVA 设计）：实验组数量

调用 sample_size 工具后，将结果整理为：
- 每组所需样本量
- 考虑 20% 脱落率后的实际招募量建议
- 参数敏感性说明（效应量估计误差对样本量的影响）
```

### 输出规范

- 展示 `sample_size` 工具的完整计算结果
- 提供考虑脱落率的实际招募量建议（通常 +10%~30%）
- 等级标注：**O2 草稿级**

---

## 步骤四：方案生成（generate_plan）

### 目标

综合前三步结果，生成完整的实验方案草稿。

> **⚠️ review_gate = true**：方案生成前将暂停，等待用户确认前三步结果后方可继续。

### 伦理提示规则

检测用户输入中的伦理相关关键词，自动触发伦理提示：

**触发关键词**：`临床试验`、`人体`、`患者`、`受试者`、`志愿者`、`动物实验`、`小鼠`、`大鼠`、`IRB`、`伦理`

**伦理提示内容**（关键词匹配时必须包含）：
```
⚠️ 伦理审查提示：
本研究设计涉及人体试验/动物实验，实施前必须：
1. 向所在机构伦理审查委员会（IRB/IACUC）提交申请并获批
2. 确保知情同意程序符合赫尔辛基宣言（人体研究）或 3R 原则（动物研究）
3. 在中国临床试验注册中心（ChiCTR）或 ClinicalTrials.gov 完成注册（临床试验）
本 AI 不提供伦理判断，上述责任由研究者和所在机构承担。
```

### LLM 提示模板

```
综合以下研究设计信息：
- 研究问题：{define_problem_output}
- 实验设计：{choose_design_output}
- 样本量计算：{calculate_params_output}

请生成完整的实验方案草稿，结构如下：

---
**实验方案草稿**（O2 草稿级）

## 1. 研究背景与问题
[简述研究背景和核心假设]

## 2. 实验设计类型与理由
[设计类型 + 选择理由]

## 3. 受试者/样本
- 纳入标准：
- 排除标准：
- 样本量：每组 N 例（考虑脱落率后建议招募 M 例）

## 4. 样本量计算过程
[完整参数：effect_size, alpha, power, 设计类型]

## 5. 干预/处理方案
[实验组 vs 对照组的具体干预描述]

## 6. 主要结局指标
[测量时间点 + 统计方法]

## 7. 统计分析计划
[主要检验方法 + 多重比较处理]

## 8. 伦理考量
[如适用，包含 IRB/IACUC 要求]

## 9. 局限性与风险
[主要方法学局限]

---
⚠️ **输出等级声明**：本方案为草稿级（O2），需专业人员审核后方可实施。
研究者应结合具体学科规范、文献证据和机构要求对本方案进行修订完善。
```

### 输出规范

- 严格按照上述结构生成完整方案
- 方案末尾必须包含 O2 等级声明和审核提示
- 如检测到伦理相关关键词，必须在"伦理考量"章节包含完整伦理提示
- 等级标注：**O2 草稿级**

---

## 使用示例

```
用户：我想设计一个研究，比较新药 A 和安慰剂对高血压患者血压的影响

Claude（步骤一）：好的，让我帮您定义研究问题。请问：
  您预期的血压变化（主要结局指标）是收缩压还是舒张压，还是两者都要测量？

用户：主要看收缩压的变化

Claude（步骤一完成）：研究问题摘要：
  - 干预：新药 A vs 安慰剂
  - 主要结局：收缩压变化量（mmHg）
  - 研究对象：高血压患者
  [继续确认其他要素...]

Claude（步骤二）：推荐设计：平行组 RCT
  统计方法：独立样本 t 检验
  文献参考效应量：Cohen's d 通常在 0.3~0.6 之间...

Claude（步骤三）：样本量计算结果：
  调用 sample_size(design_type="two_sample_ttest", effect_size=0.5, alpha=0.05, power=0.8)
  → 每组 64 例，考虑 20% 脱落率建议招募 77 例/组

[review_gate 触发：等待用户确认以上结果]

用户：确认，继续生成方案

Claude（步骤四）：[生成完整方案，包含伦理提示...]
⚠️ 本方案为草稿级（O2），需专业人员审核后方可实施。
```

---

## 重要限制声明

1. **本 Skill 不提供**：伦理合规判断、临床适应症建议、统计推断的最终结论
2. **本 Skill 仅提供**：实验设计引导和样本量估算的框架性参考（O2 草稿级）
3. **使用前提**：用户需具备基本统计背景，或在统计顾问指导下使用
4. **更新频率**：样本量计算使用统计公式，无需更新；领域效应量参考值请查阅最新文献
