# Nini 可视化指南

> 科研级数据可视化最佳实践与规范

## 概述

Nini 提供了两种绘图方式：
1. **`create_chart` 技能**：快速标准图表，支持 7 种期刊风格
2. **`run_code` 技能**：自定义代码，完全控制

本指南帮助您选择合适的方法并遵循最佳实践。

---

## 快速选择决策树

```
用户需求
├─ 简单标准图表（散点、折线、柱状、箱线图等）
│  └─ 使用 create_chart ✅
│     ├─ 支持 7 种期刊风格（Nature, Science, Cell 等）
│     └─ 自动应用中文字体
│
├─ 复杂自定义需求（多子图、统计标注、特殊布局）
│  └─ 使用 run_code ✅
│     ├─ 完全控制 Matplotlib/Plotly/Seaborn
│     └─ 需要手动设置中文字体
│
└─ 用户明确指定工具
   └─ 遵循用户要求 ✅
```

---

## 图表类型与适用场景

### 散点图 (Scatter Plot)
**适用场景**：
- 展示两个连续变量的关系
- 相关性分析可视化
- 异常值检测

**示例**：
```python
# create_chart 方式
create_chart(
    chart_type="scatter",
    x_column="height",
    y_column="weight",
    title="身高与体重的关系",
    journal_style="nature"
)

# run_code 方式（带回归线）
import matplotlib.pyplot as plt
import numpy as np

plt.figure(figsize=(10, 6))
plt.scatter(df['height'], df['weight'], alpha=0.6)

# 添加回归线
z = np.polyfit(df['height'], df['weight'], 1)
p = np.poly1d(z)
plt.plot(df['height'], p(df['height']), "r--", alpha=0.8)

plt.xlabel('身高 (cm)')
plt.ylabel('体重 (kg)')
plt.title('身高与体重的关系（含回归线）')
plt.show()
```

---

### 箱线图 (Box Plot)
**适用场景**：
- 展示数据分布和异常值
- 组间比较
- 统计检验结果可视化

**示例**：
```python
# create_chart 方式
create_chart(
    chart_type="box",
    x_column="group",
    y_column="blood_pressure",
    title="各组血压分布对比",
    journal_style="science"
)

# run_code 方式（带统计标注）
import matplotlib.pyplot as plt
import seaborn as sns

fig, ax = plt.subplots(figsize=(10, 6))
sns.boxplot(data=df, x='group', y='blood_pressure', ax=ax)

# 添加统计显著性标注
from statannotations.Annotator import Annotator
pairs = [("control", "treatment")]
annotator = Annotator(ax, pairs, data=df, x='group', y='blood_pressure')
annotator.configure(test='t-test_ind', text_format='star')
annotator.apply_and_annotate()

plt.title('各组血压分布对比（含显著性检验）')
plt.show()
```

---

### 折线图 (Line Plot)
**适用场景**：
- 时间序列数据
- 趋势变化展示
- 多组对比

**示例**：
```python
# create_chart 方式
create_chart(
    chart_type="line",
    x_column="time",
    y_column="value",
    title="血压变化趋势",
    journal_style="cell"
)

# run_code 方式（多条线 + 置信区间）
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 6))

for group in df['group'].unique():
    group_data = df[df['group'] == group]
    ax.plot(group_data['time'], group_data['value'], label=group, linewidth=2)

    # 添加置信区间
    ax.fill_between(
        group_data['time'],
        group_data['value'] - group_data['std'],
        group_data['value'] + group_data['std'],
        alpha=0.2
    )

ax.set_xlabel('时间 (天)')
ax.set_ylabel('血压 (mmHg)')
ax.set_title('各组血压变化趋势（含 95% 置信区间）')
ax.legend()
plt.show()
```

---

### 柱状图 (Bar Plot)
**适用场景**：
- 分类数据对比
- 频数统计
- 组间均值比较

**示例**：
```python
# create_chart 方式
create_chart(
    chart_type="bar",
    x_column="category",
    y_column="count",
    title="各类别样本分布",
    journal_style="plos"
)

# run_code 方式（分组柱状图）
import matplotlib.pyplot as plt
import numpy as np

categories = df['category'].unique()
groups = df['group'].unique()

x = np.arange(len(categories))
width = 0.35

fig, ax = plt.subplots(figsize=(10, 6))

for i, group in enumerate(groups):
    values = [df[(df['category'] == cat) & (df['group'] == group)]['value'].mean()
              for cat in categories]
    ax.bar(x + i * width, values, width, label=group)

ax.set_xlabel('类别')
ax.set_ylabel('平均值')
ax.set_title('各组在不同类别下的均值对比')
ax.set_xticks(x + width / 2)
ax.set_xticklabels(categories)
ax.legend()
plt.show()
```

---

### 直方图 (Histogram)
**适用场景**：
- 数据分布可视化
- 正态性检查
- 频率分析

**示例**：
```python
# create_chart 方式
create_chart(
    chart_type="histogram",
    x_column="value",
    title="数据分布直方图",
    journal_style="nature"
)

# run_code 方式（带正态分布拟合）
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

fig, ax = plt.subplots(figsize=(10, 6))

# 绘制直方图
n, bins, patches = ax.hist(df['value'], bins=30, density=True, alpha=0.7, edgecolor='black')

# 拟合正态分布
mu, sigma = stats.norm.fit(df['value'])
x = np.linspace(df['value'].min(), df['value'].max(), 100)
ax.plot(x, stats.norm.pdf(x, mu, sigma), 'r-', linewidth=2,
        label=f'正态分布拟合\nμ={mu:.2f}, σ={sigma:.2f}')

ax.set_xlabel('数值')
ax.set_ylabel('概率密度')
ax.set_title('数据分布直方图（含正态分布拟合）')
ax.legend()
plt.show()
```

---

### 热图 (Heatmap)
**适用场景**：
- 相关矩阵可视化
- 多变量关系展示
- 聚类结果展示

**示例**：
```python
# run_code 方式（推荐，热图通常需要自定义）
import matplotlib.pyplot as plt
import seaborn as sns

# 计算相关矩阵
corr = df[numeric_cols].corr()

# 绘制热图
fig, ax = plt.subplots(figsize=(10, 8))
sns.heatmap(
    corr,
    annot=True,  # 显示数值
    fmt='.2f',   # 数值格式
    cmap='coolwarm',  # 色板
    center=0,    # 颜色中心
    square=True, # 正方形单元格
    linewidths=0.5,
    cbar_kws={"shrink": 0.8},
    ax=ax
)
ax.set_title('变量相关性热图')
plt.tight_layout()
plt.show()
```

---

### 小提琴图 (Violin Plot)
**适用场景**：
- 展示数据分布密度
- 组间分布对比
- 结合箱线图优势

**示例**：
```python
# run_code 方式
import matplotlib.pyplot as plt
import seaborn as sns

fig, ax = plt.subplots(figsize=(10, 6))
sns.violinplot(data=df, x='group', y='value', ax=ax)

# 叠加箱线图（可选）
sns.boxplot(
    data=df, x='group', y='value',
    width=0.3,
    boxprops=dict(alpha=0.7),
    ax=ax
)

ax.set_title('各组数据分布对比（小提琴图）')
plt.show()
```

---

## 期刊风格指南

Nini 支持 7 种期刊风格，自动应用配色方案和字体：

| 风格 | 特点 | 适用场景 |
|------|------|----------|
| **Nature** | 经典、简洁、高对比度 | 综合性研究、高影响力期刊 |
| **Science** | 现代、清晰、专业 | 基础科学研究 |
| **Cell** | 鲜艳、饱和度高 | 生物医学研究 |
| **PLOS** | 明亮、友好、开放 | 开放获取期刊 |
| **BMC** | 专业、医学风格 | 临床医学研究 |
| **Lancet** | 严谨、保守、医学权威 | 高水平临床研究 |
| **NEJM** | 经典医学期刊风格 | 顶级临床医学期刊 |

**使用示例**：
```python
create_chart(
    chart_type="scatter",
    x_column="x",
    y_column="y",
    title="相关性分析",
    journal_style="nature"  # 使用 Nature 风格
)
```

---

## 中文字体设置规范

### ⚠️ 常见错误

```python
# ❌ 错误 1：单一西文字体（中文显示为方框）
plt.rcParams['font.sans-serif'] = ['Arial']

# ❌ 错误 2：单一中文字体（某些系统无此字体）
plt.rcParams['font.sans-serif'] = ['SimHei']

# ❌ 错误 3：忘记设置负号
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
# 负号显示为方框
```

### ✅ 正确做法

```python
# ✅ 使用 fallback 字体链（推荐）
font_list = [
    'Noto Sans CJK SC',      # Linux 常用
    'Source Han Sans SC',    # Adobe 开源字体
    'Microsoft YaHei',       # Windows 常用
    'PingFang SC',           # macOS 常用
    'SimHei',                # 备选
    'Arial Unicode MS',      # 备选
    'DejaVu Sans'            # 最终备选
]
plt.rcParams['font.sans-serif'] = font_list
plt.rcParams['axes.unicode_minus'] = False  # ⚠️ 关键：解决负号显示问题
```

### Plotly 中文字体

```python
# ✅ Plotly 字体设置
fig.update_layout(
    font=dict(
        family="Noto Sans CJK SC, Source Han Sans SC, Microsoft YaHei, PingFang SC, SimHei",
        size=12
    )
)
```

---

## 图表尺寸与分辨率

### 推荐尺寸

| 用途 | 尺寸 (英寸) | DPI | 说明 |
|------|------------|-----|------|
| **在线预览** | (10, 6) | 100 | 默认，适合屏幕查看 |
| **报告插图** | (12, 7) | 150 | 清晰度更高 |
| **期刊投稿（单栏）** | (3.5, 2.5) | 300 | 满足期刊要求 |
| **期刊投稿（双栏）** | (7, 5) | 300 | 满足期刊要求 |
| **PPT 演示** | (10, 6) | 150 | 适合大屏幕 |
| **多子图（2×2）** | (12, 10) | 150 | 保持单图清晰度 |

### 代码示例

```python
# 单图
fig, ax = plt.subplots(figsize=(10, 6))

# 多子图（2×2）
fig, axes = plt.subplots(2, 2, figsize=(12, 10))

# 保存高分辨率图片
plt.savefig('figure.png', dpi=300, bbox_inches='tight')

# Plotly 导出
fig.write_image('figure.png', width=1400, height=900, scale=2.0)
```

---

## 常见陷阱与解决方案

### 陷阱 1：忘记设置 `purpose` 和 `label`

```python
# ❌ 错误：图表无法被识别和保存
await run_code(code="...", intent="绘制箱线图")

# ✅ 正确
await run_code(
    code="...",
    intent="绘制血压分组箱线图",
    purpose='visualization',  # 关键：标记为可视化
    label="血压分组对比箱线图"  # 关键：图表标题
)
```

### 陷阱 2：图表太小，文字难以阅读

```python
# ❌ 错误
fig, ax = plt.subplots(figsize=(4, 3))

# ✅ 正确
fig, ax = plt.subplots(figsize=(10, 6))
```

### 陷阱 3：颜色选择不当（色盲不友好）

```python
# ❌ 错误：红绿色盲无法区分
colors = ['red', 'green', 'blue']

# ✅ 正确：使用色盲友好色板
import seaborn as sns
colors = sns.color_palette("colorblind", 3)
# 或使用 Matplotlib 色板
colors = plt.cm.tab10.colors
```

### 陷阱 4：不检查数据就绘图

```python
# ❌ 错误：未处理缺失值和异常值
plt.scatter(df['x'], df['y'])

# ✅ 正确：先清洗数据
clean_df = df[['x', 'y']].dropna()

# 检查并处理异常值（可选）
Q1 = clean_df.quantile(0.25)
Q3 = clean_df.quantile(0.75)
IQR = Q3 - Q1
clean_df = clean_df[~((clean_df < (Q1 - 1.5 * IQR)) |
                       (clean_df > (Q3 + 1.5 * IQR))).any(axis=1)]

plt.scatter(clean_df['x'], clean_df['y'])
```

### 陷阱 5：子图布局混乱

```python
# ❌ 错误：子图重叠
fig, axes = plt.subplots(2, 2, figsize=(10, 8))
# ... 绘图代码 ...
plt.show()  # 子图可能重叠

# ✅ 正确：调整布局
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
# ... 绘图代码 ...
plt.tight_layout()  # 自动调整布局
plt.show()
```

---

## 最佳实践清单

### 绘图前

- [ ] 确认数据已清洗（无缺失值、异常值）
- [ ] 选择合适的图表类型
- [ ] 确定使用 `create_chart` 还是 `run_code`

### 绘图中

- [ ] 设置合适的图表尺寸（≥ 10×6 英寸）
- [ ] 配置中文字体 fallback 链
- [ ] 设置清晰的标题、坐标轴标签
- [ ] 使用色盲友好色板
- [ ] 设置 `purpose='visualization'` 和 `label`（run_code）

### 绘图后

- [ ] 检查中文是否正常显示
- [ ] 检查负号是否正常显示
- [ ] 验证图例和标签清晰可读
- [ ] 确认图表已保存到工作区
- [ ] （可选）导出高分辨率版本（DPI ≥ 300）

---

## 完整示例：发表级图表

```python
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from scipy import stats

# 1. 设置中文字体
font_list = ['Noto Sans CJK SC', 'Source Han Sans SC', 'Microsoft YaHei',
             'PingFang SC', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['font.sans-serif'] = font_list
plt.rcParams['axes.unicode_minus'] = False

# 2. 设置期刊风格
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.5)

# 3. 创建图表
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# 子图 1：散点图 + 回归线
ax1 = axes[0, 0]
ax1.scatter(df['x'], df['y'], alpha=0.6, s=50)
z = np.polyfit(df['x'], df['y'], 1)
p = np.poly1d(z)
ax1.plot(df['x'], p(df['x']), "r--", alpha=0.8, linewidth=2)
ax1.set_xlabel('变量 X')
ax1.set_ylabel('变量 Y')
ax1.set_title('(A) 相关性分析')

# 子图 2：箱线图
ax2 = axes[0, 1]
sns.boxplot(data=df, x='group', y='value', ax=ax2)
ax2.set_xlabel('分组')
ax2.set_ylabel('数值')
ax2.set_title('(B) 组间对比')

# 子图 3：直方图 + 正态拟合
ax3 = axes[1, 0]
ax3.hist(df['value'], bins=30, density=True, alpha=0.7, edgecolor='black')
mu, sigma = stats.norm.fit(df['value'])
x = np.linspace(df['value'].min(), df['value'].max(), 100)
ax3.plot(x, stats.norm.pdf(x, mu, sigma), 'r-', linewidth=2)
ax3.set_xlabel('数值')
ax3.set_ylabel('概率密度')
ax3.set_title('(C) 分布拟合')

# 子图 4：热图
ax4 = axes[1, 1]
corr = df[numeric_cols].corr()
sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm',
            center=0, square=True, linewidths=0.5, ax=ax4)
ax4.set_title('(D) 相关矩阵')

# 4. 调整布局
plt.tight_layout()

# 5. 显示和保存
plt.show()
plt.savefig('figure.png', dpi=300, bbox_inches='tight')
```

---

## 参考资源

- [Matplotlib 官方文档](https://matplotlib.org/stable/contents.html)
- [Seaborn 图库](https://seaborn.pydata.org/examples/index.html)
- [Plotly Python 文档](https://plotly.com/python/)
- [色盲友好色板工具](https://colorbrewer2.org/)
- [期刊投稿图表要求指南](https://www.nature.com/nature/for-authors/final-submission)

---

## 总结

选择合适的绘图方法和遵循最佳实践，可以显著提升图表质量和科研效率：

1. **简单图表** → `create_chart`（快速、风格统一）
2. **复杂需求** → `run_code`（灵活、完全控制）
3. **中文字体** → 使用 fallback 链 + 负号修复
4. **图表尺寸** → ≥ 10×6 英寸，DPI ≥ 300（投稿）
5. **色板选择** → 色盲友好、符合期刊要求

遵循这些规范，您的图表将达到发表级标准！🎨
