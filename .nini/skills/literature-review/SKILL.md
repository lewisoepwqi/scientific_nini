---
name: literature-review
description: |
  文献调研引导工作流，覆盖检索、筛选、综合与输出四个步骤。
  适用于开题调研、方法对比、争议梳理和综述提纲生成；在线时优先调用 search_literature，
  离线时自动切换到手动模式，引导用户上传 PDF 或提供引用列表。
category: workflow
research-domain: general
difficulty-level: advanced
typical-use-cases:
  - 围绕研究主题快速收集候选文献
  - 对近年核心论文进行人工筛选与证据综合
  - 生成带来源标注的综述草稿提纲
allowed-tools:
  - search_literature
  - workspace_session
  - task_state
  - analysis_memory
user-invocable: true
disable-model-invocation: false
contract:
  version: "1"
  trust_ceiling: t1
  evidence_required: true
  steps:
    - id: search_papers
      name: 文献检索
      description: 优先调用 search_literature 检索候选文献；离线时切换到手动模式
      tool_hint: search_literature
      depends_on: []
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: filter_papers
      name: 文献筛选
      description: 按研究问题、时效性、证据层级和相关性筛选候选文献
      tool_hint: null
      depends_on:
        - search_papers
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: synthesize
      name: 证据综合
      description: 提炼共同结论、争议点、研究空白，并为每个结论保留来源映射
      tool_hint: null
      depends_on:
        - filter_papers
      trust_level: t1
      review_gate: false
      retry_policy: skip
    - id: generate_output
      name: 输出生成
      description: 生成带 O2 草稿级声明的综述摘要或提纲，缺证据处显式标注待验证
      tool_hint: null
      depends_on:
        - synthesize
      trust_level: t1
      review_gate: false
      retry_policy: skip
  input_schema:
    type: object
    properties:
      topic:
        type: string
        description: 研究主题或检索问题
      year_from:
        type: integer
        description: 可选的起始年份
  output_schema:
    type: object
    properties:
      review_outline:
        type: string
        description: 带来源标注的综述草稿
      evidence_table:
        type: array
        description: 结论与来源映射表
---

# 文献调研引导工作流

> **输出等级声明**：本 Skill 全部输出均为 **O2 草稿级**，仅用于研究准备与写作辅助，引用前必须人工复核。
> **证据约束**：每个关键结论都必须标注来源；没有来源支撑的断言必须标注为“缺少文献支撑，需进一步检索验证”。

本技能采用四步线性流程：**检索 → 筛选 → 综合 → 输出**。默认先尝试在线检索；若网络不可用，则立即转入手动模式，不静默失败。

## 第一步：检索（search_papers）

### 在线模式

1. 使用 `search_literature`，参数建议包含：
   - `query`：主题词、疾病名、方法名、关键机制
   - `year_from`：需要聚焦近年研究时设置
   - `sort_by`：默认 `relevance`；若做近年进展综述可改为 `date`
2. 返回结果后，先整理为候选文献表，至少包含：
   - 标题
   - 作者
   - 年份
   - DOI
   - 摘要
   - 引用次数

### 手动模式

当 `search_literature` 返回离线或降级提示时，必须明确告知用户：

> 当前为离线模式，无法在线检索文献。请上传 PDF、粘贴参考文献列表，或提供 DOI/标题后继续。

随后引导用户选择一种手动输入方式：

1. 上传 PDF：适合已有全文的文献
2. 粘贴引用列表：适合已有参考文献条目
3. 提供 DOI / 标题：适合已有零散线索

不得假装已经完成在线检索；必须明确区分“在线结果”和“用户手动提供的文献”。

## 第二步：筛选（filter_papers）

围绕研究问题建立筛选清单，对每篇候选文献至少判断以下维度：

- **相关性**：是否直接回答研究问题
- **时效性**：是否属于当前研究阶段需要优先关注的年份
- **证据层级**：系统综述、随机对照试验、观察性研究、方法论文等
- **可复用性**：是否提供关键方法、数据集、评价指标或局限性信息

筛选输出建议使用三栏结构：

1. 保留：与主题直接相关、证据强
2. 备选：间接相关，但可辅助背景或讨论
3. 排除：主题偏离、方法不可比或信息不足

## 第三步：综合（synthesize）

综合阶段必须以“结论 - 证据 - 争议/局限”三联结构组织内容。推荐模板：

```text
结论：
证据：
- [作者, 年份, 标题]
争议/局限：
```

必须覆盖以下内容：

- 主流共识：多个来源重复支持的结论
- 关键争议：研究结论不一致之处及可能原因
- 方法学差异：样本、设计、指标、模型或统计策略的差异
- 研究空白：现有文献尚未充分回答的问题

若某个判断仅来自单篇文献，必须显式标注“单一来源，需扩大检索后再确认”。

## 第四步：输出（generate_output）

输出可以是综述摘要、章节提纲或证据表，但必须包含以下部分：

1. **O2 草稿级声明**
   - 本综述为草稿级（O2），需人工审核后方可引用。
2. **核心结论**
   - 每条结论后附 `(作者, 年份, 标题)` 形式的来源标注
3. **争议与局限**
   - 明确指出证据不足、结论冲突或方法局限
4. **后续建议**
   - 建议补检索的关键词、需重点阅读全文的论文、值得追踪的综述或方法论文

### 输出格式模板

```markdown
## 文献调研摘要（O2 草稿级）

### 1. 核心发现
- 结论 A（作者1，2023，标题1；作者2，2024，标题2）
- 结论 B（缺少文献支撑，需进一步检索验证）

### 2. 争议点
- 争议 A：...

### 3. 研究空白
- 空白 A：...

### 4. 建议下一步
- 补充关键词：
- 优先阅读全文：
```

## 执行约束

- 不得捏造不存在的文献、DOI、作者或年份
- 不得将无来源的推断表述成已证实结论
- 若用户只提供少量文献，必须提醒样本偏窄，综合结论可能失真
- 若离线模式下继续工作，所有结论都应注明“基于用户提供文献”
