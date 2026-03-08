---
name: article_draft
description: 根据会话中已完成的数据分析结果，逐章生成结构完整的科研论文初稿（含摘要、引言、方法、结果、讨论、结论），并将各章节保存为工作区文件。
category: report
research-domain: general
difficulty-level: advanced
typical-use-cases:
  - 基于实验数据自动生成论文初稿
  - 将统计分析结果整理为标准学术论文格式
  - 生成可供人工润色的结构化论文草稿
allowed-tools:
  - ask_user_question
  - data_summary
  - dataset_catalog
  - list_workspace_files
  - stat_test
  - stat_model
  - stat_interpret
  - chart_session
  - edit_file
  - workspace_session
  - report_session
  - code_session
  - task_state
  - analysis_memory
  - export_document
  - export_report
---

# 科研文章初稿生成工作流

本技能指导 Agent 基于当前会话中已完成的数据分析，逐步生成完整的科研论文初稿。

## 执行前提

在调用本技能前，用户应已完成：
- 兼容旧工作流时，`data_summary` 可视为 `dataset_catalog` 的等价入口
- 数据加载（`dataset_catalog`）
- 至少一项统计分析（如 `stat_test`、`stat_model`、`code_session`、`chart_session` 等）
- 可选：图表生成（`chart_session` 或复杂场景下的 `code_session`）

## 工作流步骤

### 第一步：收集数据与分析概况

调用 `dataset_catalog` 获取已加载数据集的基本统计信息（样本量、变量列表、缺失值等）。

若用户已描述分析目标，结合会话历史中已生成的统计结果（t 值、p 值、回归系数、相关系数等）作为写作素材。

### 第二步：解读统计结果（如需要）

若会话中有统计分析结果但尚未进行文字解读，调用 `stat_interpret` 生成结果的自然语言描述，作为「结果」章节的写作依据。

### 第三步：生成配图（如需要）

根据分析类型补充必要图表：
- 回归分析 → 散点图 + 回归线（`chart_session` 或 `code_session`）
- 差异分析 → 箱线图（`chart_session`）
- 相关分析 → 热力图（`chart_session` 或 `code_session`）

### 第四步：确定文件名并创建文章

**4.1 智能生成文件名**

基于以下信息生成语义化文件名：
- 数据集名称（如 `blood_pressure_data` → 提取 "blood_pressure"）
- 研究主题/分析目标（如 "心率与血压相关性研究"）
- 主要分析变量（如 "t_test_group_comparison"）

文件名格式：`{主题关键词}_{日期}.md`
示例：
- `heart_rate_blood_pressure_correlation_20250302.md`
- `group_comparison_analysis_20250302.md`
- `diabetes_clinical_study_20250302.md`

**4.2 向用户确认文件名（推荐）**

生成文件名后，先向用户展示建议的文件名，询问是否需要修改：
> "我将为您生成科研论文初稿，建议保存为：`heart_rate_blood_pressure_correlation_20250302.md`。您确认使用此文件名，或希望修改为其他名称？"

如用户指定了文件名，使用用户提供的名称（自动添加 `.md` 扩展名）。

**4.3 创建初始文件**

使用 `workspace_session`（operation=write）创建文件，写入文章标题和结构大纲：

兼容旧工作流描述时，可将 `edit_file` 视为 `workspace_session` 的文件写入/追加能力封装。

然后使用 `workspace_session`（operation=append）依次追加各章节内容：

**摘要（Abstract）**
- 约 250 字
- 包含：研究背景、目的、方法、主要结果、结论
- 格式：单段落，不分小节

**引言（Introduction）**
- 约 400-600 字
- 包含：研究背景与意义、现有研究局限、本研究目的与假设

**方法（Methods）**
- 约 300-500 字
- 包含：研究设计、数据来源与样本描述、统计分析方法（明确说明所用检验方法及软件）

**结果（Results）**
- 约 400-600 字
- 包含：描述性统计（引用 `dataset_catalog` 结果）、推断性统计（引用 `stat_interpret` 结果，汇报统计量、p 值、效应量）
- **图表嵌入**：使用 Markdown 图片引用语法直接嵌入图表，格式如下：

```markdown
## 图表

### 图 1：{图表描述标题}
![图1：{图表描述}]({图表下载URL})

### 图 2：{图表描述标题}
![图2：{图表描述}]({图表下载URL})
```

- 图表 URL 获取方式：调用 `workspace_session(operation="list")` 获取图表的 `download_url`
- 若沿用旧提示词，`list_workspace_files` 对应当前 `workspace_session(operation="list")`
- 优先使用工具返回的实际 `download_url`；不要通过 `code_session` 枚举工作区目录
- 支持的图表格式：PNG、JPEG、SVG 等图片格式可直接渲染；HTML 格式使用链接 `[查看交互图表](url)`
- 正文中引用图表时使用「如图 1 所示」格式

**讨论（Discussion）**
- 约 500-700 字
- 包含：主要发现解释、与已有研究的比较、局限性分析、未来研究方向

**结论（Conclusion）**
- 约 100-200 字
- 简明概括研究贡献与主要发现

**参考文献（References）**
- 使用 APA 7th 格式（如用户未指定）
- 仅列出文中实际引用的文献；若无具体文献信息，标注「[待补充]」占位

### 第五步：导出文档（可选）

若用户需要 DOCX 或 PDF 格式：
1. 若工作区中已经存在文章草稿 Markdown 文件，优先调用 `export_document`
2. 仅当用户明确要求重新生成标准结构化分析报告时，再调用 `report_session`
3. `export_report` 仅在明确需要 PDF/DOCX 导出且已有报告资源时使用

## 输出规范

- **文件名**：基于研究主题智能生成语义化文件名，格式 `{主题关键词}_{日期}.md`（如 `heart_rate_analysis_20250302.md`），保存前向用户确认
- **文件位置**：保存于工作区根目录
- **语言**：默认与用户对话语言一致；学术惯例需英文时使用英文
- **统计结果格式**：`t(df) = x.xx, p = .xxx, d = x.xx`（APA 风格）
- **图表嵌入**：使用 Markdown 图片语法 `![图N：描述](download_url)` 直接嵌入，便于直接预览
- **写入方式**：每次 append 调用写入一个完整章节，避免超长单次写入

## 注意事项

- **不捏造数据**：所有统计量必须来自会话中实际执行的分析结果
- **数据缺失处理**：若某项分析数据缺失，在对应章节标注「[数据待补充]」
- **参考文献**：若用户已提供参考文献，优先使用；否则标注占位符
- **文件名确认**：生成文件前，建议先向用户展示建议的文件名并确认，提升用户体验
- **图表嵌入技巧**：
  - 优先使用 Markdown 图片语法 `![描述](url)` 嵌入，可在文档中直接预览
  - 使用 `workspace_session(operation="list")` 获取工作区中图表结果文件的实际 `download_url`
  - 如有多张图表，按顺序编号并添加描述性标题
- **完成提示**：生成完毕后，主动告知用户文件位置、文件名，并询问是否需要进一步修改

## 示例：完整执行流程

假设用户已完成心率与血压的相关性分析，会话中有数据集 `heart_data.csv` 和相关性图表。

### Step 1: 生成并确认文件名
```
Agent: 我将为您生成科研论文初稿。
根据分析内容（心率与血压相关性研究），建议文件名为：
`heart_rate_blood_pressure_correlation_20250302.md`

您确认使用此文件名，或希望修改？
```

### Step 2: 创建文件并写入标题和大纲
```python
workspace_session(
    file_path="heart_rate_blood_pressure_correlation_20250302.md",
    operation="write",
    content="# 心率与血压相关性研究\n\n## 摘要\n\n[待补充]\n\n## 引言\n\n[待补充]\n..."
)
```

### Step 3: 逐章追加内容
每章使用 `workspace_session(operation="append")` 追加。

### Step 4: 嵌入图表
在「结果」章节中嵌入图表：
```markdown
## 结果

### 描述性统计
心率均值 = 75.2 ± 8.5 bpm，血压均值 = 125.3 ± 15.2 mmHg...

### 相关性分析
如图 1 所示，心率与收缩压呈显著正相关（r = 0.62, p < 0.001）...

## 图表

### 图 1：心率与血压散点图
![图1：心率与血压散点图](/api/artifacts/session_xxx/heart_bp_scatter_20250302_143052.png)

### 图 2：相关性热力图
![图2：变量间相关性热力图](/api/artifacts/session_xxx/correlation_heatmap_20250302_143105.png)
```

### Step 5: 告知用户完成
```
Agent: 论文初稿已生成并保存为 `heart_rate_blood_pressure_correlation_20250302.md`。
文件包含摘要、引言、方法、结果（含图表）、讨论、结论和参考文献共 7 个章节。
您可以直接在文档中查看嵌入的图表，或告诉我需要修改哪些内容。
```
