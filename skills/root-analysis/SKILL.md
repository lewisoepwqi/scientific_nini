---
name: root-analysis
description: |
  植物根长度数据的自动化统计分析，包含方差分析(ANOVA)、Tukey HSD多重比较和出版级可视化。
  当用户提到：根长度、植物表型、处理组比较（Mock vs ISX）、R语言ANOVA分析，或提供包含
  sample/treatment/length列的CSV/Excel数据时使用。也适用于生物统计和科学绘图。
category: statistics
agents:
  - nini
  - claude-code
  - codex
tags:
  - root-length
  - anova
  - tukey-hsd
  - plant-phenotype
  - biostatistics
aliases:
  - 根长分析
  - 根长度分析
  - 根系分析
  - root length analysis
allowed-tools:
  - run_code
  - run_r_code
  - create_chart
  - generate_report
argument-hint: "<data-file-path>"
user-invocable: true
disable-model-invocation: false
license: MIT
---

# 植物根长度分析

使用ANOVA方差分析、Tukey HSD事后检验和出版级图表，对植物根长度数据进行专业的统计分析和可视化。

## 快速开始

本技能帮助生物学研究者通过简单的3步工作流程分析根长度数据：

1. **验证** → 检查数据格式
2. **配置** → 选择颜色方案和样本排序
3. **执行** → 运行分析并获得出版级图表

**最低要求**：
- 数据文件（CSV或Excel），包含列：`sample`（样本）、`treatment`（处理）、`length`（长度）
- 至少2个样本，包含"Mock"和至少一个其他处理组
- 每个样本×处理组合至少3次测量

**您将获得**：
- 统计分析结果（ANOVA + Tukey HSD）
- 两张出版级PDF图表
- 显著性字母标记（显示哪些样本有差异）
- ISX/Mock比率分析

**示例对话**：
```
用户："我有根长度数据需要分析"
Claude："我来帮您分析根长度数据。请提供CSV或Excel文件的路径。"
用户："C:/data/roots_2024.csv"
Claude：[验证数据，询问颜色方案，生成分析]
结果：5分钟内得到专业图表和统计结果
```

### ✨ 新功能亮点

#### 1. 多处理组支持
不再限于Mock vs ISX两组比较！现在支持：
- **任意数量的处理组**（3个、4个或更多）
- **灵活的基线选择**：可选择任意处理组作为比率分析的基线
- **自动分面**：图表自动适应处理组数量

**示例**：
```
处理组：Mock, ISX, Treatment3, Treatment4
基线：Mock（默认）或任意其他组
结果：4个分面的图表 + 多组比率分析
```

#### 2. 批量分析
一次性分析多个实验数据！
- **自动处理整个目录**的数据文件
- **独立分析**：每个文件生成独立的项目和图表
- **HTML汇总报告**：可视化查看所有结果
- **并行执行**：节省时间

**使用场景**：
- 多个时间点的实验数据
- 不同条件下的重复实验
- 需要对比的多个独立实验

#### 3. Python分析选项 🐍
无需安装R环境！现在支持纯Python模式：
- **零R依赖**：使用scipy、statsmodels、matplotlib完成所有分析
- **相同的统计方法**：ANOVA、Tukey HSD、显著性字母
- **相同的可视化效果**：出版级PDF图表
- **跨平台兼容**：Windows、macOS、Linux

**适用场景**：
- 没有R环境的用户
- 需要集成到Python数据处理流程
- 偏好Python生态的研究者

**如何使用**：
```bash
# 生成Python项目（而非R项目）
python scripts/generate_r_project.py --data-file data.csv --use-python

# 批量分析使用Python模式
python scripts/batch_analysis.py --files *.csv --use-python
```

---

## 数据要求

您的数据文件必须包含**3列**（列名区分大小写）：

| 列名 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `sample` | 文本 | 样本或基因型名称 | Col_0, mutant1, Aox1a OE |
| `treatment` | 文本 | 处理组（必须包含"Mock"） | Mock, ISX |
| `length` | 数值 | 根长度测量值 | 5.23, 4.1, 3.87 |

### 关键规则

✅ **必须满足**：
- 列名必须完全一致：`sample`、`treatment`、`length`（小写）
- 处理组必须包含 `Mock`（大写M）
- 长度值必须只包含数字（不能有单位如"5.2 cm"）
- 每个样本×处理组合至少3次重复

❌ **常见错误**：
- 错误的列名（如"Sample_Name"而非"sample"）
- 缺少Mock组或拼写不同（如"mock"、"Control"）
- 长度值包含非数字（如"5.2cm"、"未测量"）
- 样本名称不一致（如"upox1-1" vs "upox1_1"）

### 有效数据示例

```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Mock,5.4
Col_0,Mock,5.1
Col_0,ISX,4.1
Col_0,ISX,4.3
Col_0,ISX,4.2
mutant1,Mock,3.8
mutant1,Mock,4.0
mutant1,Mock,3.9
mutant1,ISX,5.2
mutant1,ISX,5.4
mutant1,ISX,5.1
```

**详细格式说明见**：[references/data_format.md](references/data_format.md)

---

## 交互式工作流程

当您调用此技能时，我将引导您完成以下步骤：

### 步骤1：提供数据文件

我会询问您的数据文件路径。

**支持格式**：CSV (.csv)、Excel (.xlsx, .xls)

### 步骤2：数据验证

我会使用验证脚本自动检查您的数据：

```bash
python scripts/validate_data.py <您的文件>
```

**验证项目**：
- 文件是否存在且可读
- 必需列是否存在
- Mock处理组是否存在
- 长度列是否为数值
- 重复次数是否充足（少于3次会警告）
- 样本名称是否一致

**如果验证失败**：我会提供清晰的错误信息和具体修复建议。

**如果验证成功**：我会显示数据摘要：
```json
{
  "n_samples": 9,
  "treatments": ["Mock", "ISX"],
  "n_measurements": 450,
  "length_range": {"min": 3.0, "max": 5.5, "mean": 4.4}
}
```

### 步骤3：配置参数

我会使用 AskUserQuestion 工具询问分析参数：

**问题1：颜色方案**

选项：
- `high_contrast`（推荐）- 24种高对比度颜色，视觉最清晰
- `default` - 32种多样化颜色，适合大样本集
- `blue` - 蓝色渐变（5-16个样本）
- `green` - 绿色渐变，植物主题
- `qualitative` - 平衡的分类颜色

**问题2：样本排序**

选项：
- `auto`（推荐）- Col_0优先，然后非OE样本，最后OE样本
- `custom` - 自定义排序（我会询问具体顺序）

### 步骤4：生成R项目

我会创建完整的R分析项目：

```bash
python scripts/generate_r_project.py \
  --data-file <您的文件> \
  --color-scheme <选择> \
  --sample-order <auto或custom> \
  --output-dir output \
  --width 8 \
  --height 6
```

**输出结构**：
```
r_analysis_project/
  ├── main.R
  ├── R/
  │   ├── load_packages.R
  │   ├── data_processing.R
  │   ├── statistical_analysis.R
  │   └── plotting.R
  └── output/
      ├── figures/
      └── records/
```

### 步骤5：执行分析

我会运行R分析：

```bash
cd r_analysis_project && Rscript main.R
```

**处理过程**：
1. 加载所需R包（readxl、dplyr、ggplot2、multcompView等）
2. 读取和处理数据
3. 对每个处理组执行ANOVA
4. 计算Tukey HSD事后检验
5. 生成显著性字母
6. 创建根长度图
7. 计算ISX/Mock比率
8. 对比率执行ANOVA
9. 创建比率图
10. 保存所有输出

### 步骤6：展示结果

我会向您展示：

**统计摘要**：
```
=== ANOVA结果（Mock组）===
F统计量：12.4，p < 0.001
样本间存在显著差异

=== ANOVA结果（ISX组）===
F统计量：8.7，p < 0.001
样本间存在显著差异
```

**生成的文件**：
- `output/figures/root_length_plot.pdf` - 主图表，带显著性字母
- `output/figures/ratio_plot.pdf` - ISX/Mock比率比较
- `output/records/sample_order.txt` - 使用的样本排序
- `output/records/color_mapping.csv` - 颜色分配

**可选**：我可以解释统计结果、显著性字母或分析的任何方面。

---

## 理解结果

### ANOVA结果

**单因素方差分析**检验每个处理组内不同样本的平均根长度是否存在差异。

**关键数值**：
- **F统计量**：组间方差与组内方差的比值。越大表示差异越明显。
- **p值**：偶然获得此F统计量的概率
  - p < 0.05：样本间存在显著差异 ✓
  - p ≥ 0.05：未检测到显著差异

**示例**：
```
处理组：Mock
F(8, 216) = 12.43，p < 0.001
```
解读：在8个样本和216次测量中，我们发现强有力的证据（p < 0.001）表明样本的Mock根长度存在差异。

### Tukey HSD显著性字母

ANOVA检测到差异后，**Tukey HSD**识别具体哪些配对存在差异。

**结果以字母显示**（a、b、c等）：

**规则**：共享字母的组 → 无显著差异

**示例1**：
```
Col_0:    a
mutant1:  b
mutant2:  c
```
三者互相都有显著差异。

**示例2**：
```
Col_0:    a
mutant1:  ab
mutant2:  b
```
- Col_0 vs mutant1：无显著差异（共享"a"）
- mutant1 vs mutant2：无显著差异（共享"b"）
- Col_0 vs mutant2：可能有显著差异（无共同字母，但通过mutant1连接）

### ISX/Mock比率图

**目的**：显示对ISX处理的相对响应。

**计算方法**：
```
比率 = (单个ISX长度值) / (该样本Mock组的平均值)
```

**解释**：
- 比率 > 1.0：ISX增加根长度
- 比率 = 1.0：ISX无影响
- 比率 < 1.0：ISX减少根长度

比率图上的**显著性字母**表明哪些样本对ISX的响应不同。

**详细统计方法说明见**：[references/statistical_methods.md](references/statistical_methods.md)

---

## 输出文件

### 1. 根长度图 (`root_length_plot.pdf`)

**内容**：
- 两个分面：Mock（左）和ISX（右）
- 柱高 = 平均根长度
- 彩色柱/点 = 各个样本
- 误差线 = 标准误
- 柱上方字母 = 显著性分组
- 散点 = 单个测量值

**用途**：展示绝对根长度和处理效应

### 2. 比率图 (`ratio_plot.pdf`)

**内容**：
- 单面板显示ISX/Mock比率
- 柱高 = 平均比率
- 误差线 = 标准误
- 字母 = 比率差异的显著性分组

**用途**：比较不同样本对处理的相对响应

### 3. 样本顺序记录 (`sample_order.txt`)

**内容**：
```
样本排列顺序（左→右）：
1. Col_0
2. om66
3. upox1_1
4. Aox1a OE
5. UPOX1 OE
```

**用途**：理解图表布局，重现分析

### 4. 颜色映射 (`color_mapping.csv`)

**内容**：
```csv
sample,color
Col_0,#808080
om66,#8fb79d
upox1_1,#dd3125
```

**用途**：跨图表保持颜色一致性，创建自定义图表

### 5. 控制台输出

**内容**：
- 完整的ANOVA表格
- Tukey HSD配对比较
- 显著性字母
- 处理信息

**用途**：详细统计数据，论文方法部分

---

## 故障排查

### 数据验证错误

**错误**："缺少必需列"
```
修复：将列重命名为：sample、treatment、length（小写）
Excel：右键点击列 → 重命名
CSV：在文本编辑器中编辑
```

**错误**："treatment列必须包含'Mock'"
```
修复：将对照组重命名为"Mock"（大写M）
查找替换："control" → "Mock"
```

**错误**："length列包含非数值"
```
修复：从长度列中删除单位和文本
错误："5.2 cm"、"未测量"
正确：5.2、NA（表示缺失）
```

### 样本名称不一致

**警告**："某些样本的测量次数少于3次"
```
原因：某些行中样本名称拼写不同
修复：统一拼写
  upox1-1 → upox1_1（选择一种风格）
  Mutant1 → mutant1（检查大小写）
```

### R包安装

**错误**："未找到包'readxl'"
```
修复：脚本首次运行时会自动安装包
如果失败，在R中手动安装：
  install.packages(c("readxl", "dplyr", "ggplot2", "multcompView", "tidyr"))
```

### 颜色方案问题

**样本数量超过颜色方案**：
```
解决方案：使用"default"或"high_contrast"方案
这些方案会自动为大样本集生成额外颜色
```

### 图表元素被截断

**样本名称截断或重叠**：
```
修复1：增加图表宽度
  --width 10（代替8）

修复2：编辑 R/plotting.R
  修改：angle = 45 为 angle = 90（垂直标签）
  修改：size = 12 为 size = 10（更小字体）
```

### 缺少显著性字母

**图表上没有字母显示**：
```
原因：ANOVA p值 > 0.05（无显著差异）
检查：控制台输出的ANOVA结果
如果确实不显著，这是正确的 - 不需要字母
如果数据看起来有差异，检查：
  - 样本量（需要>3次重复）
  - 高方差（离群值？）
  - 数据录入错误
```

### 分析时间太长

**脚本运行缓慢**：
```
正常时间：200-500次测量需要1-2分钟
如果>5分钟：
  - 检查数据文件大小（>10,000行？）
  - 关闭其他R会话
  - 检查是否有无限循环（报告为bug）
```

### 获取更多帮助

1. **查看示例数据**：将您的文件与 `assets/example_data.csv` 比较
2. **运行验证**：`python scripts/validate_data.py your_file.csv`
3. **查看参考文档**：
   - 数据格式问题 → [references/data_format.md](references/data_format.md)
   - 统计问题 → [references/statistical_methods.md](references/statistical_methods.md)
   - 自定义 → [references/customization.md](references/customization.md)
4. **查看R控制台输出**：寻找具体错误信息

---

## 高级自定义

想要修改分析的用户：

**颜色方案**：见 [references/customization.md](references/customization.md#颜色方案)

**样本排序**：见 [references/customization.md](references/customization.md#样本排序)

**图表尺寸**：见 [references/customization.md](references/customization.md#图表尺寸)

**统计选项**：见 [references/customization.md](references/customization.md#高级自定义)

**添加自定义颜色方案**：编辑 `R/plotting.R` → `create_color_maps()`

**更改显著性水平**：编辑 `R/statistical_analysis.R` → `TukeyHSD(model, conf.level = 0.99)`

**修改图表美学**：编辑 `R/plotting.R` → `create_root_length_plot()`

---

## 示例对话

```
用户："我需要分析突变体的根长度数据"

Claude："我来帮您用ANOVA分析根长度数据并生成出版级图表。
请提供CSV或Excel文件的路径。"

用户："C:/experiments/root_data.xlsx"

Claude：[运行验证]
"✓ 数据验证通过！
- 发现9个样本：Col_0、Aox1a OE、upox1_1...
- 处理组：Mock、ISX
- 总计450次测量

现在配置分析。您想要哪种颜色方案？"

[显示颜色方案选项]

用户：[选择"high_contrast"]

Claude："很好的选择！图表中的样本应该如何排序？"

[显示排序选项]

用户：[选择"auto"]

Claude：[生成项目并运行分析]

"✓ 分析完成！

统计结果：
- Mock组：F(8,216) = 12.4，p < 0.001 → 发现显著差异
- ISX组：F(8,216) = 8.7，p < 0.001 → 发现显著差异
- 比率分析：F(8,216) = 6.3，p < 0.001 → 样本对ISX的响应不同

生成的文件：
📊 r_analysis_project/output/figures/root_length_plot.pdf
📊 r_analysis_project/output/figures/ratio_plot.pdf
📄 r_analysis_project/output/records/sample_order.txt
📄 r_analysis_project/output/records/color_mapping.csv

需要我解释显著性字母的含义吗？"

用户："是的，请解释"

Claude：[用他们数据中的示例解释Tukey HSD字母]
```

---

## 引用

如果您在发表的研究中使用此技能，请致谢：

```
根长度统计分析使用R（v4.x）及以下包完成：ggplot2（Wickham，2016）、
dplyr（Wickham等，2023）和multcompView（Graves等，2023）。
ANOVA和Tukey HSD事后检验在α = 0.05显著性水平下进行。
```

**参考文献**：
- Wickham, H. (2016). ggplot2: Elegant Graphics for Data Analysis. Springer-Verlag New York.
- R Core Team (2024). R: A Language and Environment for Statistical Computing. R Foundation for Statistical Computing, Vienna, Austria.

---

## 许可证

本技能在MIT许可证下发布。详见 [LICENSE.txt](LICENSE.txt)。

---

## 高级功能

### 多处理组分析

#### 为什么需要多处理组？

在实际研究中，您可能需要比较：
- **多种药物**：Mock、Drug1、Drug2、Drug3
- **多个浓度**：Control、Low、Medium、High
- **多个时间点**：0h、6h、12h、24h

传统的两组比较（Mock vs ISX）无法满足这些需求。多处理组支持让您可以在一张图表中比较所有条件。

#### 如何使用

**数据格式**（与之前相同，只是treatment有更多选项）：
```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Drug1,4.1
Col_0,Drug2,3.5
Col_0,Drug3,4.8
mutant1,Mock,3.8
mutant1,Drug1,5.2
mutant1,Drug2,4.2
mutant1,Drug3,4.5
```

**命令行使用**：
```bash
python scripts/generate_r_project.py \
  --data-file data.csv \
  --baseline-treatment Mock  # 指定基线处理组（默认Mock）
```

**通过对话**：
技能会自动检测您有多个处理组，并询问：
- "检测到4个处理组：Mock、Drug1、Drug2、Drug3"
- "选择基线处理组用于比率分析？（默认：Mock）"

#### 输出结果

**根长度图**：
- 自动生成多个分面（每个处理组一个）
- Mock组默认显示在最左侧
- 其他处理组按字母顺序排列

**比率图**：
- 计算所有非基线组相对于基线组的比率
- 例如：Drug1/Mock、Drug2/Mock、Drug3/Mock
- 显著性字母标记不同处理组间的差异

**统计分析**：
- 每个处理组内进行ANOVA（样本间比较）
- 比率数据的ANOVA（处理组响应比较）
- 完整的Tukey HSD事后检验

#### 注意事项

- 至少需要**2个处理组**
- 推荐包含"Mock"作为对照组（但非必需）
- 如果没有Mock组，会收到警告但仍可继续分析
- 比率分析需要指定基线处理组

---

### 批量分析

#### 适用场景

批量分析适用于以下情况：

**场景1：时间序列实验**
```
实验目录/
  ├── day1_roots.csv
  ├── day3_roots.csv
  ├── day5_roots.csv
  └── day7_roots.csv
```

**场景2：不同条件实验**
```
数据/
  ├── temperature_20C.csv
  ├── temperature_25C.csv
  └── temperature_30C.csv
```

**场景3：独立重复实验**
```
重复实验/
  ├── replicate1.csv
  ├── replicate2.csv
  └── replicate3.csv
```

#### 如何使用

**方式1：分析整个目录**
```bash
python scripts/batch_analysis.py \
  --input-dir data_directory/ \
  --output-dir batch_results \
  --color-scheme high_contrast \
  --baseline-treatment Mock
```

**方式2：指定文件列表**
```bash
python scripts/batch_analysis.py \
  --files exp1.csv exp2.csv exp3.csv \
  --output-dir batch_results
```

**方式3：通过Claude对话**
```
用户："我有10个实验的数据文件需要批量分析"
Claude："请提供文件所在目录，或提供文件列表"
用户："C:/experiments/batch_data/"
Claude：[自动批量分析所有文件]
```

#### 输出内容

**1. 独立分析结果**

每个数据文件都会生成独立的分析项目：
```
batch_results/
  ├── experiment1_20240227_143025/
  │   ├── main.R
  │   ├── R/
  │   └── output/
  │       ├── figures/
  │       │   ├── root_length_plot.pdf
  │       │   └── ratio_plot.pdf
  │       └── records/
  ├── experiment2_20240227_143026/
  │   └── ...
  └── summary_report.html
```

**2. HTML汇总报告**（`summary_report.html`）

包含：
- **总体统计**：成功/失败文件数、成功率
- **每个文件的详细信息**：
  - 数据摘要（样本数、测量值、处理组）
  - 分析状态（成功/失败）
  - 项目目录链接
  - 图表文件链接
- **可视化表格**：易于浏览和比较

**3. JSON输出**

程序结束时输出JSON格式的结果：
```json
{
  "success": true,
  "summary_report": "batch_results/summary_report.html",
  "statistics": {
    "total": 10,
    "successful": 9,
    "failed": 1
  }
}
```

#### 高级选项

**跳过R执行**（仅生成项目，不运行分析）：
```bash
python scripts/batch_analysis.py \
  --input-dir data/ \
  --skip-r
```
适用于：
- 快速验证数据格式
- 生成项目后手动修改再运行
- R环境未安装的情况

**自定义配置**：
```bash
python scripts/batch_analysis.py \
  --input-dir data/ \
  --color-scheme blue \
  --baseline-treatment Control \
  --output-dir my_batch_results
```

#### 性能与时间

- **验证阶段**：每个文件 < 1秒
- **项目生成**：每个文件 < 2秒
- **R分析**（如果启用）：每个文件 1-2分钟
- **汇总报告生成**：< 5秒

**示例**：分析10个文件
- 不运行R：< 30秒
- 运行R分析：10-20分钟

#### 错误处理

批量分析会优雅处理错误：

- **数据验证失败**：跳过该文件，继续处理其他文件
- **R执行失败**：标记为失败，保存错误信息，继续下一个
- **部分失败**：仍会生成汇总报告，显示成功和失败的详细信息

所有错误都会在HTML报告中详细记录。

#### 最佳实践

1. **先小规模测试**：用2-3个文件测试配置是否正确
2. **统一数据格式**：确保所有文件格式一致
3. **合理分组**：按实验类型分目录存放
4. **保留原始数据**：批量分析不会修改原始文件
5. **定期清理**：批量结果目录可能很大，定期归档

---

## 完整示例

### 示例1：多处理组药物筛选

**数据**（drug_screening.csv）：
```csv
sample,treatment,length
WT,Mock,5.2
WT,Mock,5.4
WT,Mock,5.1
WT,DrugA,4.1
WT,DrugA,4.3
WT,DrugB,3.5
WT,DrugB,3.7
WT,DrugC,5.8
WT,DrugC,6.0
mutant1,Mock,3.8
mutant1,DrugA,5.2
mutant1,DrugB,4.2
mutant1,DrugC,3.9
```

**分析**：
```bash
python scripts/generate_r_project.py \
  --data-file drug_screening.csv \
  --baseline-treatment Mock \
  --color-scheme high_contrast
cd r_analysis_project && Rscript main.R
```

**结果**：
- 4个分面图（Mock, DrugA, DrugB, DrugC）
- 3个比率图（DrugA/Mock, DrugB/Mock, DrugC/Mock）
- 识别对不同药物响应不同的突变体

### 示例2：时间序列批量分析

**数据结构**：
```
time_series/
  ├── day0.csv  (Mock, ISX)
  ├── day3.csv  (Mock, ISX)
  ├── day7.csv  (Mock, ISX)
  └── day14.csv (Mock, ISX)
```

**批量分析**：
```bash
python scripts/batch_analysis.py \
  --input-dir time_series/ \
  --output-dir time_series_results
```

**应用**：
- 比较不同时间点的ISX效应
- 追踪根长度变化趋势
- 识别时间依赖的表型
