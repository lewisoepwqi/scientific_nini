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
  - data_summary
  - preview_data
  - interpret_stat_result
  - create_chart
  - edit_file
  - generate_report
  - export_report
---

# 科研文章初稿生成工作流

本技能指导 Agent 基于当前会话中已完成的数据分析，逐步生成完整的科研论文初稿。

## 执行前提

在调用本技能前，用户应已完成：
- 数据加载（`load_dataset`）
- 至少一项统计分析（如 `t_test`、`regression`、`correlation` 等）
- 可选：图表生成（`create_chart`）

## 工作流步骤

### 第一步：收集数据与分析概况

调用 `data_summary` 获取已加载数据集的基本统计信息（样本量、变量列表、缺失值等）。

若用户已描述分析目标，结合会话历史中已生成的统计结果（t 值、p 值、回归系数、相关系数等）作为写作素材。

### 第二步：解读统计结果（如需要）

若会话中有统计分析结果但尚未进行文字解读，调用 `interpret_stat_result` 生成结果的自然语言描述，作为「结果」章节的写作依据。

### 第三步：生成配图（如需要）

根据分析类型补充必要图表：
- 回归分析 → 散点图 + 回归线（`create_chart` type=scatter）
- 差异分析 → 箱线图（`create_chart` type=box）
- 相关分析 → 热力图（`create_chart` type=heatmap）

### 第四步：创建文章文件并逐章写入

使用 `edit_file`（operation=write）创建初始文件，例如 `article_draft.md`，写入文章标题和结构大纲。

然后使用 `edit_file`（operation=append）依次追加各章节内容：

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
- 包含：描述性统计（引用 data_summary 结果）、推断性统计（引用 interpret_stat_result 结果，汇报统计量、p 值、效应量）
- 若有图表，使用「如图 N 所示」格式引用

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
1. 调用 `generate_report` 生成结构化 Markdown 报告
2. 调用 `export_report` 导出为所需格式

## 输出规范

- 文件名：`article_draft.md`（保存于工作区根目录）
- 语言：默认与用户对话语言一致；学术惯例需英文时使用英文
- 统计结果格式：`t(df) = x.xx, p = .xxx, d = x.xx`（APA 风格）
- 每次 append 调用写入一个完整章节，避免超长单次写入

## 注意事项

- 不捏造数据：所有统计量必须来自会话中实际执行的分析结果
- 若某项分析数据缺失，在对应章节标注「[数据待补充]」
- 若用户已提供参考文献，优先使用；否则标注占位符
- 生成完毕后，主动告知用户文件位置并询问是否需要进一步修改
