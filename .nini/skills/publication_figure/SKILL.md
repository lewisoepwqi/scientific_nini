---
name: publication_figure
version: 1.1.0
min_version: 1.0
description: 生成符合 Nature/Science/Cell 等顶级期刊投稿标准的科研图表。自动输出 matplotlib/seaborn 可执行代码、PDF/PNG/EPS 矢量图、标准图注（Figure Legend）及提交前自检清单。支持柱状图、折线图、散点图、热图、Kaplan-Meier 生存曲线、火山图、多面板组合图。触发词：论文图、发表级图表、期刊图表、Nature图、Science图、Cell图、投稿用图、科研绘图、论文插图、高分辨率图表、矢量格式图表。
category: visualization
allowed-tools:
  - ask_user_question
  - dataset_catalog
  - stat_test
  - stat_model
  - stat_interpret
  - code_session
  - chart_session
  - export_chart
  - workspace_session
---

# 顶级期刊图表制作技能 (Publication-Quality Figure Skill)

## 概述

本技能指导大模型生成符合顶级学术期刊（Nature、Science、Cell、The Lancet、NEJM、PNAS、IEEE 等）发表标准的科研图表。

当用户要求绑制任何科研图表时，**必须**遵循本文档中的规范。

---

## 执行总纲（模型优先阅读）

本文档分为两部分：
- **前半部分（执行总纲 + 执行流程）**：作战地图，触发时优先阅读，明确"先做什么、再做什么"
- **后半部分（参考手册）**：详细规范、代码示例、配色参数，按需查阅

### 触发条件

- 用户要求绑制或生成科研数据图表
- 用户要求将数据可视化为论文发表级别的图形
- 用户提到 "论文图"、"发表级图表"、"期刊图表"、"Nature图"、"Science图"、"投稿用图" 等关键词
- 用户要求导出高分辨率或矢量格式图表

### 执行流程速查

```
Step 1: 需求确认（确认期刊/图表类型/数据/输出格式）
    ↓ [CP1] 向用户确认需求
Step 2: 数据预处理（清洗/统计量计算）
Step 3: 应用期刊规范（尺寸/DPI/字体/配色/线条）
    ↓ [CP2] 向用户确认规范方案
Step 4: 生成图表代码（matplotlib/seaborn + 统计标注 + 多格式保存）
    ↓ [CP3] 展示关键参数，确认后执行
Step 5: 自检与交付（清单检查 + 图注 + 交付文件）
    ↓ [CP4] 展示预览，确认或迭代
```

### 工具映射速查

| 执行步骤 | 推荐工具 | 用途说明 | 参考章节 |
|---------|---------|---------|---------|
| Step 1 需求确认 | `ask_user_question` | 向用户确认期刊、图表类型、数据状态 | 执行总纲-图表类型选择指南 |
| Step 2 数据预处理 | `dataset_catalog` | 检查数据完整性、格式、缺失值 | 第二章 |
| Step 2 统计计算 | `stat_test` / `stat_model` / `stat_interpret` | 计算统计量、p值、效应量 | 第六章 |
| Step 3 应用规范 | （规范决策步骤，无工具调用） | 按目标期刊选择尺寸/DPI/字体/配色 | 第一章、第三章 |
| Step 4 生成代码 | `code_session` / `chart_session` | 编写并执行绘图代码 | 第四章、第七章 |
| Step 4 多格式导出 | `export_chart` | 同时输出矢量(PDF/EPS/SVG)和位图(PNG/TIFF) | 7.3 节 |
| Step 5 自检交付 | `workspace_session` | 管理输出文件、交付图注与图表 | 第八章 |

> **使用原则**：优先使用上表推荐的专用工具；若工具不可用，按技能文档中的代码示例和函数模板手动实现。

### 检查点 fallback 速查

| 检查点 | 通过条件 | 未通过处理 |
|--------|---------|-----------|
| **CP1** 需求确认 | 用户确认期刊、图表类型、数据状态 | 用户提出修改 → 记录修改项，重新确认；用户未明确 → 给出推荐方案并征得同意 |
| **CP2** 规范确认 | 用户确认尺寸、配色、字体方案 | 用户要求冲突规范（3D/渐变/红绿）→ 礼貌拒绝并说明原因，提供替代方案；用户要求调整 → 返回 Step 3 修改 |
| **CP3** 代码执行前 | 用户确认关键参数（尺寸/DPI/配色/统计方法） | 用户要求调整 → 修改代码，重新展示参数摘要；用户未回复 → 等待确认，**不擅自执行** |
| **CP4** 交付确认 | 用户对图表、图注、布局满意 | 用户提出修改 → 明确修改项（配色/标签/统计/尺寸/布局），返回 Step 3 或 Step 4 迭代 |

### 异常处理速查

| 异常情况 | 快速处理 |
|---------|---------|
| 未提供数据 | 询问是否模拟演示，模拟数据须标注 |
| 数据格式错误 | 确认格式，提供转换协助 |
| 缺失值 >20% | 警告并建议处理，用户坚持则声明 |
| 样本量 n<3 | 改用个体数据点图，不适合误差线 |
| 要求 3D/渐变/阴影 | 礼貌拒绝，说明期刊规范 |
| 要求红绿配色 | 警告色盲风险，推荐蓝-橙替代 |
| 图表类型不匹配 | 解释并推荐合适类型 |
| 要求修改 p 值 | **拒绝**，坚守学术诚信 |
| 分组数 >24 / 颜色不足 | HSV 动态生成或图案填充补充 |
| 系统无 Arial 字体 | 自动回退 DejaVu/Liberation Sans |
| 中文标签显示方框 | 回退到 SimHei/Noto Sans CJK |
| 数据量过大/拥挤 | 旋转标签、抽样、改用密度图 |
| 要求动画/交互式图表 | 礼貌拒绝，提供静态版 + 可选补充材料 |

### 图表类型选择指南

根据数据特征快速定位图表类型：

| 数据特征 | 推荐图表 | 关键 MUST 规则 |
|---------|---------|---------------|
| 分类数据对比（组间均值） | **柱状图** | Y轴从0开始，必须含误差线（SD/SEM/CI） |
| 时间序列 / 连续变化 | **折线图** | 时间轴按比例，线型+颜色双重区分，≤5-6条线 |
| 两变量相关性 | **散点图** | 重叠点用透明度（alpha 0.3-0.6），标注R²和p值 |
| 数据分布对比 | **箱线图/小提琴图** | 显示中位数和四分位，图注标注样本量 |
| 矩阵型连续数据 | **热图** | 必须含 colorbar，基因表达须聚类 |
| 生存数据 | **Kaplan-Meier** | 必须含风险表、置信区间、删失标记、p值和HR |
| 差异表达数据 | **火山图** | 显示阈值线，上调/下调/不显著分色 |
| 多子图组合 | **多面板图** | 面板编号 (a,b,c)，粗体10-12pt，严格对齐 |

### 自检速查（交付前必查）

- [ ] 分辨率：位图 ≥300 DPI，线条图 ≥600 DPI
- [ ] 格式：矢量(PDF/EPS/SVG) + 位图(TIFF/PNG) 同时提供
- [ ] 尺寸：符合目标期刊单栏/双栏要求
- [ ] 字体：Arial/Helvetica，最小 6pt
- [ ] 边框：去除上/右边框，纯白背景
- [ ] 配色：色盲友好，不仅靠颜色区分
- [ ] 统计：误差线类型注明（SD/SEM/CI），p值格式正确
- [ ] 样本量：图注中标注 n 数
- [ ] 图注：含标题、面板说明、统计方法、缩写解释

---

## 适用场景

- 用户要求绑制或生成科研数据图表
- 用户要求将数据可视化为论文发表级别的图形
- 用户提到 "论文图"、"发表级图表"、"期刊图表" 等关键词
- 用户要求导出高分辨率或矢量格式图表

---

## 执行流程

### 快速决策入口

根据用户输入的完整度，选择切入步骤：

| 用户状态 | 切入步骤 | 说明 |
|---------|---------|------|
| 仅提出绘图需求，未提供数据/期刊/图表类型 | **Step 1** | 完整走流程，从需求确认开始 |
| 提供了数据和图表类型，但未指定期刊 | **Step 2** | 跳过期刊确认，使用通用规范，生成前询问目标期刊 |
| 提供了完整参数（数据+期刊+图表类型） | **Step 3** | 直接应用规范生成代码，在 CP2 确认尺寸和配色 |
| 要求修改已有图表 | **Step 3/4** | 明确修改项（配色/标签/统计/布局），定位到对应步骤 |
| 仅要求图注/自检已有图表 | **Step 5** | 跳过代码生成，直接自检和撰写图注 |

---

当触发本技能时，按以下步骤执行：

### Step 1: 需求确认（输入 → 决策）

**输入**: 用户的图表请求 + 数据（如有）  
**输出**: 明确的图表类型、目标期刊、数据状态  
**推荐工具**: `ask_user_question`

1. **确认目标期刊**：询问用户投稿期刊（如用户未指定，默认按最通用规范执行）
2. **确认图表类型**：根据数据特征确定图表类型（柱状图/折线图/散点图/热图/生存曲线/火山图/多面板组合图）
3. **确认数据完整性**：
   - 数据格式（CSV/Excel/直接提供/需模拟）
   - 样本量、分组信息、统计检验需求
   - 如用户未提供数据，询问是否使用模拟数据演示，或等待用户提供
4. **确认输出格式**：矢量格式（PDF/EPS/SVG）+ 位图格式（TIFF/PNG）

> **[检查点 CP1]** 在继续前，向用户确认需求。使用以下模板提问：
> 
> ```
> 请确认以下信息是否正确：
> - 投稿期刊：[期刊名，如 Nature/Science/Cell，未指定则写"通用规范"]
> - 图表类型：[柱状图/折线图/散点图/热图/生存曲线/火山图/多面板组合图]
> - 数据来源：[用户已提供 / 使用模拟数据演示 / 等待用户提供]
> - 输出格式：[PDF + PNG / 其他]
> 
> 如有调整请告诉我，确认后我将继续生成。
> ```
> 
> 如用户未明确期刊或图表类型，给出推荐方案并征得同意。

### Step 2: 数据预处理

**输入**: 原始数据  
**输出**: 清洗后的数据 + 统计量  
**推荐工具**: `dataset_catalog`（数据检查）、`stat_test` / `stat_model` / `stat_interpret`（统计计算）

#### 2.1 数据清洗与质量检查

1. **缺失值检测**：计算每列/每组缺失比例
   - > 20%：警告用户，建议插补或剔除（见异常处理表）
   - ≤ 20%：记录处理方法，在图注中声明
2. **异常值检测**：使用 IQR 法（1.5×IQR 规则）或 Z-score（|z| > 3）标记极端值
   - 不擅自删除异常值，仅在图注中声明检测方法
3. **数据类型确认**：确保数值型变量未误录入为字符串，分组变量为类别型

#### 2.2 统计量计算（按图表类型选择）

| 图表类型 | 必须计算的统计量 | 推荐检验 |
|---------|----------------|---------|
| 柱状图 / 条形图 | mean ± SEM（或 SD / 95% CI） | 独立 t-test / ANOVA |
| 折线图 | mean ± SEM 各时间点 | 重复测量 ANOVA |
| 散点图 | Pearson/Spearman r, R², p-value | 线性回归 |
| 箱线图 / 小提琴图 | median, Q1, Q3, IQR, 异常值 | Mann-Whitney U / Kruskal-Wallis |
| 热图 | 行/列 z-score 标准化（如需要） | 层次聚类 |
| 生存曲线 | KM 生存概率, 95% CI | log-rank test, Cox HR |
| 火山图 | log2 fold change, -log10(p), adjusted p | DESeq2/edgeR 等差异分析 |
| 多面板组合 | 各面板独立统计量 | 按面板类型选择 |

> **注意**：计算完成后，将统计结果汇总为表格，供 Step 4 代码直接调用。

#### 2.3 数据适配性验证

1. **样本量检查**：
   - n < 3 per group：不适合误差线和统计检验 → 建议改用个体数据点图（dot plot），并在图注标注样本量
   - n < 30：优先使用非参数检验
2. **分组数检查**：
   - > 24 组：触发颜色不足边界，使用 HSV 动态扩展或图案填充（见异常处理表）
3. **数据-图表匹配检查**：
   - 分类数据误要求折线图 → 返回 Step 1 推荐柱状图
   - 时间序列误要求柱状图 → 返回 Step 1 推荐折线图
   - 单变量分布误要求散点图 → 返回 Step 1 推荐箱线图/小提琴图

### Step 3: 应用期刊规范

**输入**: 图表类型 + 目标期刊  
**输出**: 规范参数清单  
**推荐工具**: 无（纯规范决策步骤，依赖本技能文档内的参数表）

1. **尺寸**：按目标期刊选择单栏/双栏宽度（见 1.2 节）
2. **分辨率**：位图 ≥300 DPI，线条图 ≥600 DPI（见 1.1 节）
3. **字体**：Arial/Helvetica，字号 7-9 pt（见 1.3 节）
4. **配色**：使用色盲友好配色（见 第三章 及 7.4 节）
5. **线条与标记**：按 1.5 节设置线宽、标记大小
6. **去除冗余元素**：按 2.1 节数据墨水比原则清理

> **[检查点 CP2]** 在生成代码前，向用户确认规范方案。使用以下模板提问：
> 
> ```
> 我将使用以下规范生成图表，请确认：
> - 图片尺寸：[单栏 89mm / 双栏 183mm / 其他]
> - 配色方案：[Okabe-Ito / Paul Tol Bright / 其他，说明选择理由]
> - 字体：Arial，最小 7pt
> - 背景：纯白，无边框阴影
> 
> 如无异议，我将继续编写绘图代码。
> ```
> 
> 如用户要求与规范冲突（如 3D 效果、渐变填充、红绿对比），礼貌拒绝并说明原因，提供替代方案。

### Step 4: 生成图表代码

**输入**: 规范参数清单 + 清洗后数据  
**输出**: 可执行的 Python/Matplotlib/Seaborn 代码  
**推荐工具**: `code_session` / `chart_session`（代码生成与执行）、`export_chart`（多格式导出）

#### 4.0 图表类型 → 代码模板索引

| 图表类型 | 对应章节 | 核心函数 / 关键参数速查 |
|---------|---------|----------------------|
| 柱状图 | 4.1 | `ax.bar(alpha=0.5)` + `ax.scatter(alpha=0.85)` jitter |
| 折线图 | 4.2 | `ax.plot()` + `ax.fill_between(alpha=0.2)` |
| 散点图 | 4.3 | `ax.scatter(alpha=0.3-0.6)` + `linregress` |
| 箱线图/小提琴图 | 4.4 | `violinplot()` + `boxplot()` + `scatter(alpha=0.6)` |
| 热图 | 4.5 | `sns.heatmap(cmap='RdBu_r')` + `z-score` |
| 生存曲线 | 4.6 | `kaplan_meier_estimator()` + 风险表 |
| 火山图 | 4.7 | `scatter()` + 阈值线 + `annotate` |
| 多面板组合 | 4.8 | `gridspec` + `text(label, fontweight='bold', fontsize=12)` |

**操作**：按上表定位图表类型，复制对应章节的代码框架，替换数据和参数。

#### 4.1 代码编写步骤

1. **导入必要库**（matplotlib, seaborn, numpy, scipy 等）
2. **设置全局主题**：调用 `set_publication_theme()`（见 7.5 节）或更新 rcParams（见 7.1 节）
3. **绘制主图**：按 4.0 索引定位到对应章节，复制代码框架，替换数据
   - 必须应用半透明叠加原则（2.5 节）：汇总元素 `alpha=0.4-0.6`，个体点 `alpha=0.7-0.9`
   - 必须使用色盲友好配色（第三章）
4. **添加统计标注**：误差线、显著性标记、样本量（见 第六章）
5. **保存多格式**：调用 `save_publication_figure()`（见 7.3 节），同时输出 PDF + PNG

> **[检查点 CP3]** 代码编写完成后、执行前，向用户展示关键参数摘要。使用以下模板提问：
> 
> ```
> 代码已准备就绪，关键参数如下：
> - 图片尺寸：[宽度 x 高度] inch
> - DPI：[数值]
> - 配色：[方案名]
> - 字体：Arial [字号]pt
> - 统计方法：[t-test/ANOVA/log-rank/等]
> 
> 确认无误后我将执行绘图。如需调整请告诉我。
> ```
> 
> 确认无误后再运行代码生成图表。

### Step 5: 自检与交付

**输入**: 生成的图表文件 + 代码  
**输出**: 最终交付物 + 图注  
**推荐工具**: `workspace_session`（文件管理与交付）

1. 按 第八章 自检清单逐项检查
2. 撰写图注（Figure Legend，见 第五章）
3. 向用户展示图表，确认是否需调整

   > **[检查点 CP4]** 展示图表预览后，使用以下模板询问用户：
   >
   > ```
   > 图表已生成，请确认：
   > - 整体布局是否符合您的预期？
   > - 配色是否满意？
   > - 标签和统计标注是否正确？
   >
   > 如需调整，请告诉我具体修改项（如：配色、标签文字、统计方法、尺寸、布局等），我将返回修改。
   > ```
   >
   > 如用户提出修改，明确修改项后返回 Step 3 或 Step 4 迭代。

4. 交付最终文件（矢量 + 位图 + 图注文本）

## 异常处理与边界条件

执行过程中遇到以下情况时，按对应策略处理：

| 异常情况 | 处理策略 |
|---------|---------|
| **用户未提供数据** | 询问是否使用模拟数据演示，或请用户提供数据。如使用模拟数据，必须在图注中明确标注 "Simulated data for demonstration"。 |
| **数据格式错误/无法解析** | 向用户确认数据格式（CSV/Excel/JSON），提供数据格式要求示例，协助转换。 |
| **缺失值过多（>20%）** | 警告用户缺失值比例，建议插补或剔除。如用户坚持，在图注中声明处理方法。 |
| **样本量过小（n<3 per group）** | 说明该样本量不适合误差线和统计检验，建议使用个体数据点图（dot plot）而非柱状图，并在图注中标注样本量。 |
| **用户要求 3D 效果/渐变/阴影** | 礼貌拒绝，解释 Nature/Science 等顶级期刊禁止此类装饰，提供平面替代方案。 |
| **用户要求红绿配色** | 警告色盲不友好风险，推荐蓝-橙或紫-黄替代方案。如用户坚持用于非色盲场景，需用户书面确认。 |
| **图表类型与数据不匹配** | 向用户解释原因并推荐合适类型（如分类数据误用折线图 → 推荐柱状图；时间序列误用柱状图 → 推荐折线图）。 |
| **用户要求的分辨率/尺寸超出期刊限制** | 说明期刊限制，提供合规替代方案。 |
| **统计检验不显著（p≥0.05）** | 如实报告，不夸大。图注中标注 "ns, not significant"，不隐藏或删除数据。 |
| **用户要求修改已统计显著的 p 值** | **拒绝**，说明学术诚信要求，引用 9.3 节伦理规范。 |
| **分组数超过可用颜色数（>24 组）** | 使用 3.5 节高区分度色板的 HSV 动态生成补充色，或改用图案填充（hatch）+ 颜色双重区分。 |
| **系统缺少指定字体（如 Linux 无 Arial）** | 自动回退到 `['DejaVu Sans', 'Liberation Sans', 'sans-serif']`，不报错中断。 |
| **中文/特殊字符标签显示为方框** | 字体回退到支持中文的无衬线字体（如 SimHei、WenQuanYi Zen Hei、Noto Sans CJK），并提醒用户最终投稿前替换为期刊要求的英文字体。 |
| **数据量过大导致标签/点重叠拥挤** | 分类标签过多（>15）时旋转 90° 或抽样显示；散点重叠时提高透明度或改用 hexbin/密度图；热图行列过多时分块或聚类后抽样。 |
| **用户要求动画/交互式/可缩放图表** | 礼貌拒绝，说明期刊只接受静态图。可提供静态高分辨率版本 + 单独交互版（HTML/Plotly）作为补充材料（需期刊允许）。 |

---

## 一、硬性技术规范（MUST 遵守）

### 1.1 分辨率与输出格式

#### 各期刊具体要求

| 期刊 | 最低 DPI | 推荐格式 | 线条图 DPI | 备注 |
|------|---------|---------|-----------|------|
| **Nature** | 300 | TIFF/EPS/PDF | 600-1200 | 单栏 89mm，双栏 183mm (Nature) |
| **Science** | 300 | PDF/EPS/AI (优先矢量) | 300+ | 单栏 5.7cm，双栏 12.1cm，三栏 18.4cm |
| **Cell Press** | 300 | TIFF/EPS/PDF | 未明确 | 接受多种格式，排版时可能调整大小 |
| **The Lancet** | 300 | 可编辑文件优先 | 未明确 | 数字摄影至少 300dpi，最小 107mm |
| **PNAS** | 300 | TIFF/EPS/PDF | 未明确 | 按最终出版尺寸准备，不要全页大小 |
| **IEEE** | 300 (彩色/灰度) | EPS/PDF/PS (矢量优先) | 600 (线条图) | 单栏 3.5 inch (88.9mm)，双栏 7.16 inch (182mm) |
| **NEJM** | 高分辨率 | PDF/高分辨率图形 | 未明确 | 上传单独的高分辨率图形文件 |

#### 通用安全值（MUST）

- **位图分辨率**：至少 **300 DPI**（照片/彩色图），线条图 **600 DPI** 或更高
- **推荐矢量格式**：**PDF > EPS > SVG**（矢量格式可无限缩放不失真）
- **最终提交**：同时提供 **矢量版** 和 **高分辨率位图版**（TIFF/PNG）
- **禁止**：低分辨率 JPG、Word/PowerPoint 嵌入图、上采样（upsampling）图像

### 1.2 图片尺寸标准

#### 期刊标准尺寸

| 期刊 | 单栏 (mm) | 双栏 (mm) | 全页深度 (mm) |
|------|----------|----------|--------------|
| Nature | 89 | 183 | 170 |
| Science | 57 (小图) / 121 | 184 | - |
| IEEE | 88.9 | 182 | - |

#### 通用安全值（单位同时提供 mm 和 inch）

```python
# 期刊标准图片宽度（inch）
FIG_WIDTH_SINGLE = 3.54      # 单栏 ≈ 89 mm
FIG_WIDTH_ONE_HALF = 5.51    # 1.5 栏 ≈ 140 mm  
FIG_WIDTH_DOUBLE = 7.48      # 双栏 ≈ 190 mm

# 推荐高宽比
ASPECT_RATIOS = {
    'golden': 0.618,         # 黄金比例
    'standard': 0.75,        # 4:3 标准比例
    'wide': 0.5625,          # 16:9 宽屏
}
```

**重要**：
- 避免小于单栏宽度，极端放大可能导致失真 (IEEE)
- 减少尺寸会提高有效分辨率，增大尺寸会降低分辨率
- 按最终出版尺寸准备图形，不要准备全页大小

### 1.3 字体规范

#### 通用安全值

| 属性 | 要求 |
|------|------|
| **字体族** | Arial, Helvetica, DejaVu Sans (无衬线) |
| **最小字号** | **5-7 points** (约 1.8-2.5 mm) (Science 要求缩小后 ≥7pt) |
| **轴标签** | 8-9 pt |
| **刻度标签** | 7-8 pt |
| **图例** | 7-8 pt |
| **面板编号** | 10-12 pt，粗体 |

#### 字体规则

- **MUST**：使用无衬线字体（sans-serif），避免衬线字体
- **MUST**：单图内字号变化不宜过大
- **MUST**：避免直接在阴影/纹理区域上叠加文字
- **MUST**：避免使用反色文字（白色字在彩色背景）
- **RECOMMENDED**：文字放在图注而非图中

### 1.4 颜色规范

#### 颜色模式

- **屏幕显示**：使用 **RGB** 模式
- **印刷出版**：使用 **CMYK** 模式（但多数期刊接受 RGB，由出版社转换）

#### 色盲友好硬性要求（MUST）

> **Nature Methods** 等期刊明确要求图表必须对色盲读者友好

- **禁止**仅依靠颜色区分数据组，必须同时使用**形状、线型、纹理**
- **禁止**红绿直接对比（最常见色盲类型）
- **推荐**使用 ColorBrewer、Paul Tol、Okabe-Ito 等色盲友好配色

### 1.5 线条与标记规范

#### 通用安全值

| 属性 | 最小值 | 推荐值 |
|------|--------|--------|
| **线宽** | 0.5 pt | 1.0-1.5 pt |
| **坐标轴线宽** | 0.5 pt | 0.8 pt |
| **标记大小** | - | 4-6 pt |
| **刻度线长度** | - | 3-4 pt |
| **刻度线宽度** | - | 0.8 pt |

#### 边框规则

- **RECOMMENDED**：去除上边框和右边框（仅保留左/下轴线）
- **MUST**：避免使用 3D 效果、阴影、渐变填充
- **MUST**：背景保持纯白色

---

## 二、设计原则（RECOMMENDED 遵守）

### 2.1 数据墨水比原则（Data-Ink Ratio）

> 源自 Edward Tufte 的经典原则：最大化数据墨水比

**去除冗余"墨水"元素**：
- [ ] 去除背景网格，或使用极浅灰色网格（`#EEEEEE`）
- [ ] 去除多余边框（只保留左边框和下边框）
- [ ] 去除 3D 效果、阴影、渐变
- [ ] 去除重复图例（如果可直接标注）
- [ ] 避免装饰性元素

### 2.2 简洁性原则

**应该做的**：
- 合并相似信息
- 使用简洁的标签
- 优先使用小倍数（small multiples）而非复杂图
- 每个面板传达一个明确信息

**不应该做的**：
- 一个图中包含过多数据线（折线图不超过 5-6 条）
- 使用不必要的颜色
- 添加与数据无关的装饰

### 2.3 可读性原则

**关键检验**：将图表缩放到期刊实际印刷尺寸后，所有元素仍应清晰可读

具体要求：
- 缩小到印刷尺寸后，文字 ≥5-7 pt
- 数据点和标记清晰可见
- 图例不遮挡数据
- 坐标轴标签完整（含单位）

### 2.4 无障碍设计（Accessibility）

- **色盲友好**：约 8% 男性、0.5% 女性有色觉缺陷
- **灰度打印友好**：确保黑白打印时仍可区分
- **高对比度**：确保文字与背景对比度 ≥4.5:1

### 2.5 原始数据透明展示原则（Data Transparency）

> 借鉴自 root-analysis 技能的可视化设计：在展示汇总统计（均值/中位数）的同时，必须让原始数据点可见，避免"柱状图陷阱"。

**半透明叠加规范**：

| 元素 | 推荐 alpha | 说明 |
|------|-----------|------|
| 汇总统计柱/箱 | 0.4 - 0.6 | 半透明填充，让底层散点若隐若现 |
| 个体数据点 | 0.7 - 0.9 | 接近不透明，确保每个点可见 |
| 置信区间阴影 | 0.15 - 0.25 | 极浅，不遮挡数据 |

**实施要点**：
- 柱状图：使用 `alpha=0.5` 的柱形 + `alpha=0.8` 的 jittered 散点
- 箱线图/小提琴图：箱体 `alpha=0.3-0.5` + 原始数据点 `alpha=0.6-0.8`
- 散点图：重叠密集区域使用 `alpha=0.3-0.6`
- 配色一致性：散点颜色与汇总统计元素使用同一色系，通过透明度区分层次

**必须避免**：
- 仅用纯色柱形遮挡全部原始数据
- alpha 过低（<0.3）导致个体点无法辨认
- 使用白色填充散点（`edgecolor='black'`），这在打印时可能丢失

---

## 三、配色方案

### 3.1 定性配色（Qualitative）- 用于分类数据

#### 推荐配色 1：Okabe-Ito（色盲友好）
```python
COLORS_OKABE_ITO = [
    '#E69F00',  # 橙
    '#56B4E9',  # 天蓝
    '#009E73',  # 绿
    '#F0E442',  # 黄
    '#0072B2',  # 蓝
    '#D55E00',  # 红
    '#CC79A7',  # 粉
    '#999999',  # 灰
]
```

#### 推荐配色 2：Paul Tol Bright
```python
COLORS_TOL_BRIGHT = [
    '#4477AA',  # 蓝
    '#EE6677',  # 红/粉
    '#228833',  # 绿
    '#CCBB44',  # 黄
    '#66CCEE',  # 青
    '#AA3377',  # 紫
    '#BBBBBB',  # 灰
]
```

#### 推荐配色 3：ColorBrewer Set2
```python
COLORS_SET2 = [
    '#66C2A5',  # 青绿
    '#FC8D62',  # 橙
    '#8DA0CB',  # 蓝
    '#E78AC3',  # 粉
    '#A6D854',  # 绿
    '#FFD92F',  # 黄
    '#E5C494',  # 棕
    '#B3B3B3',  # 灰
]
```

### 3.2 定量连续配色（Sequential）- 用于连续数值

| Colormap | 推荐场景 | 色盲友好 |
|----------|----------|----------|
| **viridis** | 通用连续数据 | ✓ |
| **plasma** | 强调高值 | ✓ |
| **inferno** | 黑色背景友好 | ✓ |
| **magma** | 强调低值 | ✓ |
| **cividis** | 专为色盲优化 | ✓ |

**Matplotlib 使用**：
```python
plt.imshow(data, cmap='viridis')
```

### 3.3 发散型配色（Diverging）- 用于有中心值的数据

| Colormap | 中心值 | 适用场景 |
|----------|--------|----------|
| **RdBu_r** | 白色 | 正负偏差 |
| **coolwarm** | 白色 | 温度类数据 |
| **PuOr** | 米色 | 异常检测 |
| **BrBG** | 米色 | 环境数据 |

### 3.4 生物医学专用配色

#### 火山图配色
```python
COLOR_VOLCANO = {
    'up': '#D73027',      # 上调 - 红
    'down': '#4575B4',    # 下调 - 蓝
    'ns': '#CCCCCC',      # 不显著 - 灰
}
```

#### 生存曲线配色
```python
COLOR_SURVIVAL = [
    '#1F77B4',  # 蓝
    '#FF7F0E',  # 橙
    '#2CA02C',  # 绿
    '#D62728',  # 红
    '#9467BD',  # 紫
]
```

### 3.5 高区分度配色（High-Contrast）

> 适用于样本数较多（>8 组）的分类数据，确保视觉上可区分。源自 root-analysis 技能的配色实践。

```python
COLORS_HIGH_CONTRAST = [
    '#E31A1C', '#1F78B4', '#33A02C', '#6A3D9A',
    '#FF7F00', '#DEDE8B', '#A65628', '#F781BF',
    '#00CED1', '#006400', '#4B0082', '#FF4500',
    '#DC143C', '#4169E1', '#228B22', '#8A2BE2',
    '#FF8C00', '#FFD700', '#8B4513', '#FF1493',
    '#0080FF', '#32CD32', '#9400D3', '#FF6347',
]
```

**使用建议**：
- 前 8 色已针对色盲优化（红/蓝/绿/紫/橙/黄/棕/粉）
- 对照组/基线组固定使用灰色 `#808080`（第 1 位后的补充色）
- 样本数 >24 时，使用 HSV 颜色空间动态生成额外颜色

### 3.6 单色渐变方案（Monotone Gradient）

> 适用于有序分类或剂量梯度数据。源自 root-analysis 技能的连续色彩映射。

#### 蓝色渐变（Blue Gradient）
```python
COLORS_BLUE_GRADIENT = [
    '#DEEBF7', '#C6DBEF', '#9ECAE1', '#6BAED6',
    '#4292C6', '#2171B5', '#08519C', '#08306B',
    '#1E3A8A', '#1E40AF', '#2563EB', '#3B82F6',
    '#60A5FA', '#93C5FD', '#BFDBFE', '#DBEAFE',
]
```

#### 绿色渐变（Green Gradient）
```python
COLORS_GREEN_GRADIENT = [
    '#EDF8E9', '#C7E9C0', '#A1D99B', '#74C476',
    '#41AB5D', '#238B45', '#006D2C', '#00441B',
    '#064E3B', '#065F46', '#047857', '#059669',
    '#10B981', '#34D399', '#6EE7B7', '#A7F3D0',
]
```

**使用建议**：
- 蓝色渐变：适合对照组→处理组的剂量响应（颜色越深 = 剂量越高）
- 绿色渐变：适合生长/阳性指标（颜色越深 = 效应越强）
- 与定性配色混用时，渐变组仅用于有序维度，定性色用于分组维度

### 3.7 配色禁忌

#### 为什么避免彩虹色图（jet/rainbow）

1. **感知非线性**：jet colormap 在绿色/青色区域的感知变化不均匀
2. **色盲不友好**：红绿交界对色盲用户无法区分
3. **误导性**：亮色可能被误读为"更重要"

#### 为什么避免红绿直接对比

- 红绿色盲（deuteranopia/protanopia）影响约 8% 男性
- 在灰度打印时可能无法区分
- 替代方案：蓝-橙、紫-黄对比

---

## 四、各类图表专项规范

### 4.1 柱状图 / 条形图（Bar Chart）

#### MUST 遵守

1. **误差线**：必须包含误差线，并明确标注类型（SD/SEM/95%CI）
2. **基线**：Y轴必须从 **0** 开始（截断Y轴会误导读者）
3. **标签**：每个柱子必须有清晰的类别标签

#### RECOMMENDED

1. **叠加原始数据点**：使用 strip plot 或 swarm plot 叠加显示分布
2. **分组间距**：组内柱子间距 < 组间间距
3. **方向**：分类较多时使用水平条形图

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np

# 数据
categories = ['Control', 'Treatment A', 'Treatment B']
means = [10, 15, 12]
sem = [1.2, 1.5, 1.1]  # 标准误

# 配色：使用高区分度色板（对照组灰色，处理组彩色）
colors = ['#808080', '#4477AA', '#EE6677']

fig, ax = plt.subplots(figsize=(3.54, 2.65))  # 单栏尺寸

# 绘制柱状图 —— 半透明填充（alpha=0.5），让底层散点可见
x = np.arange(len(categories))
bars = ax.bar(x, means, width=0.6, color=colors, edgecolor='black',
              linewidth=0.8, alpha=0.5, zorder=2)

# 添加误差线
ax.errorbar(x, means, yerr=sem, fmt='none', color='black',
            capsize=3, capthick=1, zorder=3)

# 添加原始数据点 —— 同色、高透明度、水平 jitter
np.random.seed(42)
for i, (mean, se) in enumerate(zip(means, sem)):
    # 模拟原始数据（n=10）
    raw_data = np.random.normal(mean, se * np.sqrt(10), 10)
    # 水平 jitter：正态分布，标准差 0.04，与 root-analysis 一致
    jitter = np.random.normal(i, 0.04, size=len(raw_data))
    ax.scatter(jitter, raw_data,
               color=colors[i], edgecolor='black', linewidth=0.5,
               s=20, zorder=4, alpha=0.85)

# 设置标签
ax.set_xticks(x)
ax.set_xticklabels(categories, fontsize=8)
ax.set_ylabel('Value (units)', fontsize=8)
ax.set_xlabel('Group', fontsize=8)

# 设置Y轴从0开始
ax.set_ylim(0, max(means) * 1.4)

# 去除上右边框
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# 添加显著性标记示例
y_sig = max(means) * 1.2
ax.plot([0, 0, 1, 1], [y_sig, y_sig + 0.5, y_sig + 0.5, y_sig],
        'k-', linewidth=0.8)
ax.text(0.5, y_sig + 0.7, '*', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig('bar_chart.pdf', dpi=300, bbox_inches='tight')
```

**关键设计点**：
1. `alpha=0.5` 的柱形填充，确保底层散点可透见
2. 散点使用与柱形同色（`colors[i]`），通过 `alpha=0.85` 区分层次
3. Jitter 采用 `np.random.normal(i, 0.04)`，避免过度分散
4. `zorder` 层级：柱形(2) < 误差线(3) < 散点(4)，确保散点在最上层



### 4.2 折线图 / 时间序列（Line Chart）

#### MUST 遵守

1. **线型区分**：不同组使用不同线型（实线、虚线、点划线）+ 颜色
2. **标记点**：数据点较少时使用不同形状标记
3. **坐标轴**：时间轴必须按实际比例显示

#### RECOMMENDED

1. **置信区间**：用阴影区域表示置信区间（alpha=0.2-0.3）
2. **线条数量**：同一图不超过 5-6 条线
3. **图例位置**：图例放在图外或空白区域，不遮挡数据

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np

# 数据
x = np.linspace(0, 10, 50)
y1 = np.sin(x) + np.random.normal(0, 0.1, 50)
y2 = np.cos(x) + np.random.normal(0, 0.1, 50)

fig, ax = plt.subplots(figsize=(3.54, 2.65))

# 使用不同线型和颜色
ax.plot(x, y1, 'o-', color='#4477AA', linewidth=1.2, markersize=3, 
        markerfacecolor='white', markeredgewidth=0.8, label='Group A')
ax.plot(x, y2, 's--', color='#EE6677', linewidth=1.2, markersize=3,
        markerfacecolor='white', markeredgewidth=0.8, label='Group B')

# 添加置信区间（示例）
confidence1 = 0.2
confidence2 = 0.15
ax.fill_between(x, y1 - confidence1, y1 + confidence1, 
                alpha=0.2, color='#4477AA')
ax.fill_between(x, y2 - confidence2, y2 + confidence2,
                alpha=0.2, color='#EE6677')

ax.set_xlabel('Time (days)', fontsize=8)
ax.set_ylabel('Response', fontsize=8)
ax.legend(loc='upper right', frameon=False, fontsize=7)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig('line_chart.pdf', dpi=300, bbox_inches='tight')
```

### 4.3 散点图（Scatter Plot）

#### MUST 遵守

1. **透明度**：点重叠时使用 alpha（0.3-0.6）
2. **点大小**：根据数据密度调整点大小
3. **坐标轴标签**：包含变量名和单位

#### RECOMMENDED

1. **回归线**：添加线性回归线和 R² 值
2. **边际分布**：添加边际直方图或密度图
3. **密度估计**：高密度数据使用 hexbin 或 2D 密度图

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

# 生成数据
np.random.seed(42)
x = np.random.normal(50, 15, 200)
y = 0.8 * x + np.random.normal(0, 10, 200)

fig, ax = plt.subplots(figsize=(3.54, 3.54))

# 散点图（带透明度）
ax.scatter(x, y, alpha=0.5, s=20, color='#4477AA', edgecolor='none')

# 线性回归
slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
line_x = np.array([x.min(), x.max()])
line_y = slope * line_x + intercept
ax.plot(line_x, line_y, 'r--', linewidth=1.5, label='Linear fit')

# 添加 R² 和 p 值
ax.text(0.05, 0.95, f'R² = {r_value**2:.3f}\np < 0.001',
        transform=ax.transAxes, fontsize=8, verticalalignment='top',
        bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

ax.set_xlabel('Variable X (units)', fontsize=8)
ax.set_ylabel('Variable Y (units)', fontsize=8)
ax.legend(loc='lower right', frameon=False, fontsize=7)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig('scatter_plot.pdf', dpi=300, bbox_inches='tight')
```

### 4.4 箱线图 / 小提琴图（Box Plot / Violin Plot）

#### MUST 遵守

1. **分布展示**：优先使用小提琴图展示数据分布
2. **统计要素**：箱线图必须显示中位数和四分位数
3. **样本量**：在图注中注明每组样本量

#### RECOMMENDED

1. **叠加原始点**：使用 strip plot 或 swarm plot 显示原始数据点
2. **统计检验**：添加组间统计检验标记
3. **缺口**：箱线图使用缺口（notch）显示中位数置信区间

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# 生成数据
np.random.seed(42)
data = {
    'Control': np.random.normal(100, 15, 50),
    'Treatment A': np.random.normal(120, 20, 50),
    'Treatment B': np.random.normal(110, 18, 50),
}

fig, ax = plt.subplots(figsize=(3.54, 3.0))

# 小提琴图
parts = ax.violinplot([data[k] for k in data.keys()], 
                       positions=range(len(data)), showmeans=False, showmedians=False)

# 设置小提琴颜色
colors = ['#4477AA', '#EE6677', '#228833']
for pc, color in zip(parts['bodies'], colors):
    pc.set_facecolor(color)
    pc.set_alpha(0.3)
    pc.set_edgecolor('black')

# 叠加箱线图
bp = ax.boxplot([data[k] for k in data.keys()], positions=range(len(data)),
                widths=0.15, patch_artist=True, showfliers=False,
                medianprops=dict(color='black', linewidth=1.5))

for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

# 叠加散点
for i, (key, values) in enumerate(data.items()):
    y = values
    x = np.random.normal(i, 0.04, size=len(y))
    ax.scatter(x, y, alpha=0.4, s=10, color='black')

ax.set_xticks(range(len(data)))
ax.set_xticklabels(data.keys(), fontsize=8)
ax.set_ylabel('Value (units)', fontsize=8)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig('violin_plot.pdf', dpi=300, bbox_inches='tight')
```

### 4.5 热图（Heatmap）

#### MUST 遵守

1. **色标**：必须包含 colorbar，标注数值范围
2. **聚类**：基因表达数据必须进行行/列聚类
3. **标签可读性**：行列标签过多时旋转或抽样显示

#### RECOMMENDED

1. **标准化**：基因表达数据按行标准化（z-score）
2. **聚类树**：显示聚类树（dendrogram）
3. **注释**：关键区域添加注释

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

# 生成模拟基因表达数据
np.random.seed(42)
data = np.random.randn(20, 10)
row_labels = [f'Gene_{i}' for i in range(1, 21)]
col_labels = [f'Sample_{i}' for i in range(1, 11)]

fig, ax = plt.subplots(figsize=(5.51, 7.48))  # 1.5栏高度

# 热图
sns.heatmap(data, cmap='RdBu_r', center=0, 
            xticklabels=col_labels, yticklabels=row_labels,
            cbar_kws={'label': 'Z-score'}, 
            linewidths=0.5, linecolor='white',
            ax=ax)

# 旋转x轴标签
plt.xticks(rotation=45, ha='right', fontsize=7)
plt.yticks(fontsize=7)

plt.title('Gene Expression Heatmap', fontsize=9, pad=10)
plt.tight_layout()
plt.savefig('heatmap.pdf', dpi=300, bbox_inches='tight')
```

### 4.6 生存曲线 - Kaplan-Meier

#### MUST 遵守

1. **风险表**：必须包含 "number at risk" 表
2. **置信区间**：显示生存率的置信区间（阴影）
3. **删失标记**：标注删失数据点
4. **统计信息**：标注 p 值和 HR（风险比）

#### RECOMMENDED

1. **中位生存期**：标注中位生存时间
2. **生存概率**：标注特定时间点的生存概率

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np
from sksurv.nonparametric import kaplan_meier_estimator

# 模拟生存数据
time_high = np.array([10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
event_high = np.array([1, 1, 0, 1, 1, 0, 1, 1, 0, 1])
time_low = np.array([5, 8, 12, 15, 20, 25, 30, 35, 40, 42])
event_low = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1])

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.51, 5.0), 
                                gridspec_kw={'height_ratios': [4, 1]})

# 计算KM曲线
time_h, surv_h, conf_h = kaplan_meier_estimator(
    event_high.astype(bool), time_high, conf_type='log-log')
time_l, surv_l, conf_l = kaplan_meier_estimator(
    event_low.astype(bool), time_low, conf_type='log-log')

# 绘制生存曲线
ax1.step(time_h, surv_h, where='post', color='#D73027', linewidth=1.5, label='High risk')
ax1.fill_between(time_h, conf_h[0], conf_h[1], alpha=0.2, color='#D73027', step='post')

ax1.step(time_l, surv_l, where='post', color='#4575B4', linewidth=1.5, label='Low risk')
ax1.fill_between(time_l, conf_l[0], conf_l[1], alpha=0.2, color='#4575B4', step='post')

# 添加删失标记
censor_h = time_high[event_high == 0]
surv_censor_h = np.interp(censor_h, time_h, surv_h)
ax1.scatter(censor_h, surv_censor_h, marker='+', s=50, color='#D73027', zorder=5)

# 统计信息
ax1.text(0.95, 0.95, 'p < 0.001\nHR = 2.5 (95% CI: 1.5-4.2)', 
         transform=ax1.transAxes, ha='right', va='top', fontsize=8,
         bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

ax1.set_ylabel('Survival Probability', fontsize=8)
ax1.set_ylim(0, 1.05)
ax1.legend(loc='lower left', frameon=False, fontsize=7)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# 风险表
ax2.axis('off')
time_points = [0, 10, 20, 30, 40, 50]
ax2.text(0, 0.8, 'Number at risk', fontsize=8, fontweight='bold')
ax2.text(0, 0.4, 'High risk', fontsize=8, color='#D73027')
ax2.text(0, 0, 'Low risk', fontsize=8, color='#4575B4')

for i, t in enumerate(time_points):
    n_high = np.sum(time_high >= t)
    n_low = np.sum(time_low >= t)
    x_pos = 0.2 + i * 0.15
    ax2.text(x_pos, 0.4, str(n_high), fontsize=7, ha='center')
    ax2.text(x_pos, 0, str(n_low), fontsize=7, ha='center')
    ax2.text(x_pos, 0.8, str(t), fontsize=7, ha='center')

plt.tight_layout()
plt.savefig('survival_curve.pdf', dpi=300, bbox_inches='tight')
```

### 4.7 火山图（Volcano Plot）

#### MUST 遵守

1. **阈值线**：显示 fold change 和 p-value 阈值线
2. **分类着色**：上调/下调/不显著用不同颜色
3. **显著基因标注**：标注关键基因名称

#### RECOMMENDED

1. **交互性**：电子版图可交互查看基因名称
2. **密度**：点密度高时使用透明度

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np

# 模拟差异表达数据
np.random.seed(42)
n_genes = 2000
log2fc = np.random.normal(0, 2, n_genes)
pval = np.random.uniform(0, 1, n_genes)
pval[log2fc > 2] *= 0.01
pval[log2fc < -2] *= 0.01

log10p = -np.log10(pval)

fig, ax = plt.subplots(figsize=(5.51, 5.0))

# 定义阈值
fc_thresh = 1  # |log2FC| > 1
p_thresh = 0.05  # p < 0.05

# 分类
colors = []
for fc, p in zip(log2fc, log10p):
    if abs(fc) > fc_thresh and p > -np.log10(p_thresh):
        colors.append('#D73027' if fc > 0 else '#4575B4')  # 上调/下调
    else:
        colors.append('#CCCCCC')  # 不显著

ax.scatter(log2fc, log10p, c=colors, s=10, alpha=0.6, edgecolors='none')

# 阈值线
ax.axhline(-np.log10(p_thresh), color='gray', linestyle='--', linewidth=0.8)
ax.axvline(-fc_thresh, color='gray', linestyle='--', linewidth=0.8)
ax.axvline(fc_thresh, color='gray', linestyle='--', linewidth=0.8)

# 标注显著基因（示例）
sig_genes_idx = np.where((np.abs(log2fc) > 2.5) & (log10p > 3))[0][:5]
for idx in sig_genes_idx:
    ax.annotate(f'Gene{idx}', (log2fc[idx], log10p[idx]),
                fontsize=7, ha='center')

ax.set_xlabel('Log2 Fold Change', fontsize=8)
ax.set_ylabel('-Log10 p-value', fontsize=8)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig('volcano_plot.pdf', dpi=300, bbox_inches='tight')
```

### 4.8 多面板组合图（Multi-panel Figure）

#### MUST 遵守

1. **面板编号**：使用小写字母 (a, b, c...) 或大写 (A, B, C...)
2. **编号位置**：左上角或左下角，使用粗体
3. **对齐**：各面板严格对齐，间距一致

#### RECOMMENDED

1. **共享轴标签**：使用 fig.supxlabel/supylabel
2. **统一比例**：相关面板使用相同坐标轴范围
3. **子图标注**：标签使用 10-12 pt，粗体

#### 示例代码

```python
import matplotlib.pyplot as plt
import numpy as np

fig = plt.figure(figsize=(7.48, 5.0))  # 双栏宽度

# 创建子图布局
gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[1, 0])
ax4 = fig.add_subplot(gs[1, 1])

# 绘制示例数据
np.random.seed(42)
x = np.linspace(0, 10, 50)

# Panel a
ax1.plot(x, np.sin(x), color='#4477AA')
ax1.set_title('Experiment 1', fontsize=8)

# Panel b
ax2.plot(x, np.cos(x), color='#EE6677')
ax2.set_title('Experiment 2', fontsize=8)

# Panel c
ax3.bar(['A', 'B', 'C'], [10, 15, 12], color='#228833')

# Panel d
ax4.scatter(np.random.randn(50), np.random.randn(50), alpha=0.5, s=10)

# 添加面板标签
labels = ['a', 'b', 'c', 'd']
axes = [ax1, ax2, ax3, ax4]

for ax, label in zip(axes, labels):
    ax.text(-0.15, 1.05, label, transform=ax.transAxes, 
            fontsize=12, fontweight='bold', va='top')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

# 共享轴标签
fig.supxlabel('Common X label', fontsize=9)
fig.supylabel('Common Y label', fontsize=9)

plt.savefig('multi_panel.pdf', dpi=300, bbox_inches='tight')
```



## 五、图注（Figure Legend）写作规范

### 5.1 标题行

**要求**：简洁描述图表展示的核心发现，一般不超过一句话

**示例**：
```
Figure 1 | Treatment A significantly reduces tumor growth in xenograft models.
```

### 5.2 描述正文

**结构要求**：
1. 每个面板的简要说明
2. 实验条件/时间点
3. 样本量和重复信息

**示例**：
```
a, Tumor volume measurements over 30 days for control (n=10) and 
treatment groups (n=12). b, Representative histological sections 
stained with H&E. Scale bar, 100 μm. c, Quantification of 
proliferation index from histology images.
```

### 5.3 统计信息

**必须包含**：
- 统计检验方法（t-test, ANOVA, log-rank test 等）
- p 值表示方法（精确值或不等式）
- 样本量（n 数）
- 误差线定义（SD/SEM/95% CI）

**示例**：
```
Data are presented as mean ± SEM. Statistical significance was 
determined using two-way ANOVA with Tukey's post-hoc test. 
*p < 0.05, **p < 0.01, ***p < 0.001.
```

### 5.4 缩写说明

**规则**：首次出现的缩写必须在图注中解释

**示例**：
```
DEG, differential expressed gene; HR, hazard ratio; CI, 
confidence interval; NS, not significant.
```

### 5.5 完整图注示例

```
Figure 3 | Drug combination therapy improves survival in metastatic 
melanoma patients.

a, Kaplan-Meier survival curves comparing single-agent (n=45) and 
combination therapy (n=52) groups. b, Progression-free survival 
analysis. c, Waterfall plot showing best percentage change in tumor 
burden. d, Spider plot of individual patient responses over time.

Statistical analysis was performed using the log-rank test for 
survival curves and unpaired t-test for tumor burden. HR, hazard 
ratio; CI, confidence interval; PFS, progression-free survival; 
OS, overall survival. *p < 0.05, **p < 0.01.
```

---

## 六、统计标注规范

### 6.1 显著性标记

#### 星号系统

| 标记 | p 值范围 | 含义 |
|------|---------|------|
| ns | p ≥ 0.05 | 不显著 (not significant) |
| * | p < 0.05 | 显著 |
| ** | p < 0.01 | 极显著 |
| *** | p < 0.001 | 高度显著 |
| **** | p < 0.0001 | 极度显著 |

#### 标注线（Bracket）规范

1. **线宽**：0.5-0.8 pt
2. **线型**：实线
3. **位置**：略高于被比较组的最大值
4. **星号位置**：标注线中点上方

### 6.2 p 值格式

#### 推荐格式

| 情况 | 格式示例 |
|------|---------|
| p < 0.001 | p < 0.001 (推荐) |
| 0.001 ≤ p < 0.01 | p = 0.003 (精确值) |
| p ≥ 0.05 | p = 0.12 或 ns |

#### 注意事项

- **MUST**：不要使用 p = 0.000
- **RECOMMENDED**：p < 0.001 时不再细分
- **OPTIONAL**：提供精确 p 值作为补充数据

### 6.3 效应量

#### 何时标注

- **RECOMMENDED**：临床/生物学意义比统计显著性更重要时
- **MUST**：生存分析中必须提供 HR（风险比）

#### 常用效应量指标

| 领域 | 指标 | 说明 |
|------|------|------|
| 医学 | HR | 风险比 (Hazard Ratio) |
| 医学 | OR | 比值比 (Odds Ratio) |
| 医学 | RR | 相对风险 (Relative Risk) |
| 心理学 | Cohen's d | 标准化均值差 |
| 生物学 | fold change | 倍数变化 |

---

## 七、代码实现

### 7.1 matplotlib 全局配置（rcParams）

```python
import matplotlib as mpl
import matplotlib.pyplot as plt

# === 顶级期刊图表全局配置 ===
publication_rcParams = {
    # 字体设置
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 8,              # 默认字号
    'axes.titlesize': 9,         # 标题字号
    'axes.labelsize': 8,         # 轴标签字号
    'xtick.labelsize': 7,        # X刻度标签
    'ytick.labelsize': 7,        # Y刻度标签
    'legend.fontsize': 7,        # 图例字号
    'figure.titlesize': 9,       # 图标题字号
    
    # 线条设置
    'axes.linewidth': 0.8,       # 坐标轴线宽
    'lines.linewidth': 1.0,      # 数据线线宽
    'lines.markersize': 4,       # 标记大小
    'xtick.major.width': 0.8,    # X主刻度线宽
    'ytick.major.width': 0.8,    # Y主刻度线宽
    'xtick.major.size': 3,       # X主刻度长度
    'ytick.major.size': 3,       # Y主刻度长度
    'xtick.minor.width': 0.6,    # X次刻度线宽
    'ytick.minor.width': 0.6,    # Y次刻度线宽
    
    # 边框设置 - 去除上右边框
    'axes.spines.top': False,
    'axes.spines.right': False,
    
    # 图例设置
    'legend.frameon': False,     # 去除图例边框
    'legend.loc': 'best',
    
    # 分辨率设置
    'figure.dpi': 150,           # 屏幕显示DPI
    'savefig.dpi': 300,          # 保存DPI
    'savefig.bbox': 'tight',     # 去除白边
    'savefig.pad_inches': 0.05,  # 边距
    
    # 矢量格式设置
    'pdf.fonttype': 42,          # 确保PDF字体可编辑
    'ps.fonttype': 42,
    'svg.fonttype': 'none',
    
    # 颜色设置
    'axes.prop_cycle': mpl.cycler(color=[
        '#4477AA', '#EE6677', '#228833', '#CCBB44', 
        '#66CCEE', '#AA3377', '#BBBBBB'
    ]),
}

# 应用配置
mpl.rcParams.update(publication_rcParams)
```

### 7.2 标准尺寸常量

```python
# === 期刊标准图片尺寸（inch）===
FIG_WIDTH = {
    'single': 3.54,      # 单栏 ≈ 89 mm
    'one_half': 5.51,    # 1.5 栏 ≈ 140 mm
    'double': 7.48,      # 双栏 ≈ 190 mm
    'full': 7.48,        # 全页宽
}

# 推荐高度（基于黄金比例 0.618 或标准 0.75）
def fig_height(width, aspect='standard'):
    """
    计算推荐高度
    aspect: 'golden' (0.618), 'standard' (0.75), 'wide' (0.5625)
    """
    ratios = {'golden': 0.618, 'standard': 0.75, 'wide': 0.5625}
    return width * ratios.get(aspect, 0.75)

# 常用尺寸组合
FIG_SIZE_SINGLE = (FIG_WIDTH['single'], fig_height(FIG_WIDTH['single']))
FIG_SIZE_DOUBLE = (FIG_WIDTH['double'], fig_height(FIG_WIDTH['double']))
```

### 7.3 通用保存函数

```python
import matplotlib.pyplot as plt
from pathlib import Path

def save_publication_figure(fig, filename, formats=None, dpi=300, 
                            output_dir='./figures'):
    """
    保存为多种格式的发表级图表
    
    Parameters
    ----------
    fig : matplotlib.figure.Figure
        要保存的图对象
    filename : str
        文件名（不含扩展名）
    formats : list, optional
        保存格式列表，默认 ['pdf', 'png', 'svg']
    dpi : int, optional
        位图格式DPI，默认300
    output_dir : str, optional
        输出目录
    """
    if formats is None:
        formats = ['pdf', 'png', 'svg']
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for fmt in formats:
        filepath = output_path / f"{filename}.{fmt}"
        
        if fmt in ['pdf', 'svg', 'eps']:
            # 矢量格式不需要dpi
            fig.savefig(
                filepath,
                bbox_inches='tight',
                pad_inches=0.05,
                transparent=False,
                facecolor='white',
                format=fmt
            )
        else:
            # 位图格式使用指定dpi
            fig.savefig(
                filepath,
                dpi=dpi,
                bbox_inches='tight',
                pad_inches=0.05,
                transparent=False,
                facecolor='white',
                format=fmt
            )
        print(f"Saved: {filepath}")
    
    plt.close(fig)

# 使用示例
# fig, ax = plt.subplots(figsize=FIG_SIZE_SINGLE)
# ... 绘图代码 ...
# save_publication_figure(fig, 'figure_1', formats=['pdf', 'png', 'svg'])
```

### 7.4 推荐配色常量

```python
# === 色盲友好配色方案 ===

# Okabe-Ito 配色（推荐）
COLORS_OKABE_ITO = [
    '#E69F00',  # 橙色
    '#56B4E9',  # 天蓝色
    '#009E73',  # 绿色
    '#F0E442',  # 黄色
    '#0072B2',  # 蓝色
    '#D55E00',  # 红色
    '#CC79A7',  # 粉色
    '#999999',  # 灰色
]

# Paul Tol Bright 配色
COLORS_TOL_BRIGHT = [
    '#4477AA',  # 蓝色
    '#EE6677',  # 红/粉色
    '#228833',  # 绿色
    '#CCBB44',  # 黄色
    '#66CCEE',  # 青色
    '#AA3377',  # 紫色
    '#BBBBBB',  # 灰色
]

# Paul Tol Vibrant 配色
COLORS_TOL_VIBRANT = [
    '#EE7733',  # 橙
    '#0077BB',  # 蓝
    '#33BBEE',  # 青
    '#EE3377',  # 玫红
    '#CC3311',  # 红
    '#009988',  # 青绿
    '#BBBBBB',  # 灰
]

# 生物医学专用配色
COLORS_BIOMED = {
    'up': '#D73027',           # 上调 - 红
    'down': '#4575B4',         # 下调 - 蓝
    'ns': '#CCCCCC',           # 不显著 - 灰
    'control': '#999999',      # 对照组 - 灰
    'treatment': '#E69F00',    # 治疗组 - 橙
}

# 灰度友好的配色（用于打印）
COLORS_PRINT_FRIENDLY = [
    '#000000',  # 黑
    '#444444',  # 深灰
    '#888888',  # 中灰
    '#CCCCCC',  # 浅灰
    '#FFFFFF',  # 白（填充）
]
```

### 7.5 seaborn 主题配置

```python
import seaborn as sns
import matplotlib.pyplot as plt

def set_publication_theme():
    """
    设置Seaborn发表级主题
    """
    # 使用paper上下文（最紧凑）
    sns.set_theme(
        context='paper',
        style='ticks',  # 仅显示刻度线
        palette='deep',
        font='sans-serif',
        font_scale=0.9,
        rc={
            'axes.spines.top': False,
            'axes.spines.right': False,
            'axes.linewidth': 0.8,
            'xtick.major.width': 0.8,
            'ytick.major.width': 0.8,
            'xtick.major.size': 3,
            'ytick.major.size': 3,
        }
    )

# 使用示例
set_publication_theme()
# ... seaborn绘图代码 ...
```

### 7.6 统计标注辅助函数

```python
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

def add_significance_bar(ax, x1, x2, y, p_value, h=0.02, text_offset=0.01):
    """
    在图中添加显著性标注线和星号
    
    Parameters
    ----------
    ax : matplotlib.axes.Axes
    x1, x2 : 要比较的两组x坐标
    y : 标注线的y坐标
    p_value : p值
    h : 垂线高度（相对坐标）
    text_offset : 文字偏移量
    """
    # 转换到数据坐标
    ylim = ax.get_ylim()
    h_abs = (ylim[1] - ylim[0]) * h
    offset_abs = (ylim[1] - ylim[0]) * text_offset
    
    # 确定标记
    if p_value < 0.0001:
        sig_text = '****'
    elif p_value < 0.001:
        sig_text = '***'
    elif p_value < 0.01:
        sig_text = '**'
    elif p_value < 0.05:
        sig_text = '*'
    else:
        sig_text = 'ns'
    
    # 绘制连接线
    ax.plot([x1, x1, x2, x2], 
            [y, y + h_abs, y + h_abs, y], 
            linewidth=0.8, color='black')
    
    # 添加文字
    ax.text((x1 + x2) / 2, y + h_abs + offset_abs, sig_text,
            ha='center', va='bottom', fontsize=8)

# 使用示例
# add_significance_bar(ax, 0, 1, 18, 0.003)
```



---

## 八、提交前自检清单（Checklist）

### 8.1 技术规范检查

- [ ] **分辨率**：位图 ≥300 DPI，线条图 ≥600 DPI
- [ ] **输出格式**：提供矢量格式（PDF/EPS/SVG）和高分辨率位图（TIFF/PNG）
- [ ] **图片尺寸**：符合目标期刊要求（单栏/双栏）
- [ ] **字体**：使用 Arial/Helvetica，字号 ≥6 pt
- [ ] **可读性测试**：缩放到实际印刷尺寸后所有文字仍可读
- [ ] **文件大小**：不超出期刊投稿系统限制

### 8.2 设计质量检查

- [ ] **边框**：去除上/右边框（仅保留左/下轴线）
- [ ] **3D效果**：无3D效果、阴影、渐变
- [ ] **背景**：纯白色背景
- [ ] **图例**：图例位置不遮挡数据
- [ ] **配色**：颜色方案对色盲友好
- [ ] **区分方式**：不仅靠颜色区分（辅以形状/线型/纹理）
- [ ] **网格**：无网格或极浅灰色网格
- [ ] **原始数据透明展示**：柱状图/箱线图使用半透明填充（alpha=0.4-0.6）叠加个体数据点（alpha=0.7-0.9），避免纯色遮挡

### 8.3 数据完整性检查

- [ ] **误差线**：柱状图/折线图包含误差线
- [ ] **误差类型**：图注明确误差线类型（SD/SEM/95%CI）
- [ ] **统计标注**：显著性标记正确（p值格式、星号系统）
- [ ] **样本量**：图注中注明样本量（n数）
- [ ] **坐标轴标签**：完整且包含单位
- [ ] **坐标轴范围**：合理设置，不误导（柱状图Y轴从0开始）

### 8.4 多面板检查

- [ ] **面板编号**：每个面板有清晰的编号（a, b, c...）
- [ ] **编号格式**：使用粗体、足够大的字号（10-12 pt）
- [ ] **编号位置**：左上角或左下角
- [ ] **对齐**：面板之间对齐整齐
- [ ] **间距**：面板间距一致
- [ ] **共享标签**：共享的坐标轴标签统一

### 8.5 图注检查

- [ ] **标题**：简洁描述核心发现
- [ ] **面板说明**：每个面板有独立说明
- [ ] **统计方法**：注明统计检验方法
- [ ] **样本量**：重复信息完整
- [ ] **缩写**：首次出现的缩写已解释
- [ ] **比例尺**：图像包含比例尺说明

### 8.6 图像完整性

- [ ] **完整性检查**：无拼接痕迹、无异常重复模式
- [ ] **未裁剪**：未不当裁剪数据
- [ ] **调整声明**：所有图像处理步骤在方法中声明
- [ ] **原始数据**：保留所有原始图像文件

---

## 九、常见错误与审稿人关注点

### 9.1 最常导致返修的图表问题

| 排名 | 问题 | 修正方法 |
|------|------|---------|
| 1 | **分辨率不足** | 按期刊要求重新输出，使用矢量格式 |
| 2 | **字体过小** | 字号至少6-7 pt，考虑印刷后尺寸 |
| 3 | **Y轴不从0开始**（柱状图） | 柱状图Y轴必须从0开始，折线图可以截断 |
| 4 | **色盲不友好** | 使用色盲友好配色，不仅靠颜色区分 |
| 5 | **缺少统计信息** | 图注明确检验方法、p值、样本量 |
| 6 | **误差线类型未说明** | 图注明确是SD、SEM还是95%CI |
| 7 | **图例遮挡数据** | 图例放在图外或空白区域 |
| 8 | **过度装饰** | 去除3D效果、阴影、渐变、多余边框 |
| 9 | **坐标轴标签缺失** | 所有轴必须有标签和单位 |
| 10 | **面板编号混乱** | 使用连续字母编号，清晰可读 |

### 9.2 学科特殊注意事项

#### 生物医学/临床医学

- **生存分析**：必须包含风险表（number at risk）
- **免疫组化**：提供染色评分标准
- **Western Blot**：提供完整膜图，标注分子量
- **显微镜图像**：包含比例尺和染色说明

#### 生物信息学/基因组学

- **热图**：必须进行行/列聚类
- **火山图**：明确fold change和p值阈值
- **PCA/t-SNE**：解释方差百分比
- **通路分析**：注明数据库和版本

#### 工程技术

- **电路图**：使用标准IEEE符号
- **流程图**：遵循标准符号规范
- **机械图**：包含尺寸标注和公差
- **算法图**：伪代码与图示一致

#### 社会科学

- **问卷数据**：说明量表类型和评分标准
- **定性数据**：提供编码示例
- **地理数据**：包含地图投影说明

### 9.3 伦理与诚信

- **图像处理**：仅允许亮度/对比度整体调整，不允许局部修改
- **数据完整性**：不得删除"异常值"而不报告
- **重复发表**：同一数据不得在多篇文章中重复发表而不引用
- **第三方图像**：必须获得使用许可并注明来源

---

## 十、推荐工具与资源

### 10.1 Python 库

| 库 | 用途 | 推荐版本 |
|----|------|---------|
| **matplotlib** | 基础绘图 | ≥3.5 |
| **seaborn** | 统计可视化 | ≥0.12 |
| **plotly** | 交互式图表 | ≥5.0 |
| **scipy** | 统计分析 | ≥1.9 |
| **scikit-survival** | 生存分析 | ≥0.19 |
| **statannotations** | 统计标注 | ≥0.5 |

### 10.2 R 包

| 包 | 用途 |
|----|------|
| **ggplot2** | 基础绘图 |
| **ggpubr** | 发表级图表 |
| **survminer** | 生存曲线 |
| **ComplexHeatmap** | 热图 |
| **EnhancedVolcano** | 火山图 |

### 10.3 在线工具

| 工具 | 用途 | 网址 |
|------|------|------|
| **ColorBrewer** | 配色方案 | colorbrewer2.org |
| **Coblis** | 色盲模拟 | coblis.com |
| **BioRender** | 科学插图 | biorender.com |
| **PlotDigitizer** | 数据提取 | plotdigitizer.com |

### 10.4 参考资源

1. **Tufte, E.R.** (2001). *The Visual Display of Quantitative Information*. 2nd Ed.
2. **Cleveland, W.S.** (1994). *The Elements of Graphing Data*. 2nd Ed.
3. **Wilke, C.O.** (2019). *Fundamentals of Data Visualization*. O'Reilly.
4. **Healy, K.** (2018). *Data Visualization: A Practical Introduction*. Princeton.

---

## 十一、快速参考卡（Quick Reference）

### 尺寸速查

```
单栏 (89 mm)    = 3.54 inch ≈ 250 pixels @ 72 DPI
双栏 (183 mm)   = 7.48 inch ≈ 540 pixels @ 72 DPI
最小字号: 6 pt  = 2.1 mm  ≈ 6 pixels @ 300 DPI
```

### DPI速查

```
屏幕显示:     72-96 DPI
网页/演示:    150 DPI
期刊印刷:     300 DPI (彩色/灰度)
线条图:       600-1200 DPI
```

### 字号速查

```
面板编号:     10-12 pt, bold
图表标题:     9-10 pt
轴标签:       8 pt
刻度标签:     7 pt
图例:         7 pt
最小可读:     5-6 pt
```

### 线宽速查

```
数据线:       1.0-1.5 pt
坐标轴:       0.8 pt
误差线:       0.8 pt
显著性标记线:  0.8 pt
边框线:       0.5-1.0 pt
```

### 代码调试速查

| 报错/异常 | 快速诊断 | 修复方案 |
|---------|---------|---------|
| `Font family ['Arial'] not found` | 系统缺少 Arial 字体 | 已配置回退链 `['Arial', 'Helvetica', 'DejaVu Sans', 'Liberation Sans']`；如仍报错，安装 `mscorefonts` 或改用 `DejaVu Sans` |
| `ModuleNotFoundError: No module named 'sksurv'` | 生存分析库未安装 | `pip install scikit-survival`；如安装失败，改用 `lifelines` 库替代 |
| `UserWarning: Glyph missing` / 中文显示为方框 | 当前字体不支持 CJK 字符 | 临时回退 `plt.rcParams['font.sans-serif'] = ['SimHei', 'WenQuanYi Zen Hei', 'Noto Sans CJK']`；提醒用户投稿前替换为期刊要求的英文字体 |
| `PermissionError` 保存失败 | 输出目录无写入权限 | 更换 `output_dir` 到用户有权限的路径，如 `./figures` 或当前工作目录 |
| `ValueError: x and y must have same first dimension` | 数据长度不匹配 | 检查 DataFrame 行列是否与绘图代码一致；确认分组标签与数据点数量相等 |
| `LinAlgError` 在热图聚类时 | 数据中存在 NaN 或常数列 | 先剔除全 NaN 行/列，或对常数列添加微小噪声 (`+ np.random.normal(0, 1e-10)`) |
| 图片保存后文字/标签被截断 | `bbox_inches='tight'` 未生效或面板过多 | 增大 `figsize` 或减小 `fontsize`；多面板图使用 `plt.savefig(..., bbox_inches='tight', pad_inches=0.1)` |

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0 | 2026-02-13 | 初始版本，覆盖 Nature/Science/Cell/Lancet/IEEE/PNAS/NEJM 规范 |

---

## 参考来源

本技能文档基于以下官方指南和权威资源编制。按关联章节索引，便于快速定位：

| 序号 | 来源 | 关联章节 | 用途 |
|------|------|---------|------|
| 1 | **Nature** - Formatting Guide for Authors (nature.com) | 1.1, 1.2 | 分辨率、尺寸、格式规范 |
| 2 | **Science** - Instructions for Preparing Revised Manuscripts (science.org) | 1.1, 1.2, 1.3 | 尺寸、字体、线条规范 |
| 3 | **Cell Press** - Figure Guidelines (cell.com) | 1.1 | 格式兼容性 |
| 4 | **The Lancet** - Artwork Guidelines (thelancet.com) | 1.1, 1.2 | 分辨率与最小尺寸 |
| 5 | **IEEE** - Graphic Preparation Guidelines (ieee.org) | 1.1, 1.2 | 线条图 DPI、单双栏宽度 |
| 6 | **PNAS** - Digital Art Guidelines (pnas.org) | 1.1 | 最终出版尺寸要求 |
| 7 | **NEJM** - Technical Guidelines for Figures (nejm.org) | 1.1 | 高分辨率图形标准 |
| 8 | **Morrison et al.** (2021) - *PLoS Comput Biol* | 2.1, 2.2 | 数据可视化十原则 |
| 9 | **Tufte, E.R.** - *The Visual Display of Quantitative Information* | 2.1, 2.3 | 数据墨水比、可读性原则 |
| 10 | **Paul Tol** - Color Schemes for Scientific Data | 3.1, 3.5 | 色盲友好配色方案 |
| 11 | **Wong, B.** - Nature Methods Points of View | 1.4, 2.4 | 色盲设计考量 |
| 12 | **Matplotlib** - style sheets and rcParams | 7.1, 7.5 | 全局配置与主题设置 |
| 13 | **root-analysis skill** (配色实践) | 2.5, 3.5, 3.6 | 半透明叠加原则、高区分度色板、渐变方案 |

---

*本文档遵循 CC BY 4.0 协议，可自由分享和修改，但需注明来源。*
