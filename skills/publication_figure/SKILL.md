# 顶级期刊图表制作技能 (Publication-Quality Figure Skill)

## 概述

本技能指导大模型生成符合顶级学术期刊（Nature、Science、Cell、The Lancet、NEJM、PNAS、IEEE 等）发表标准的科研图表。

当用户要求绑制任何科研图表时，**必须**遵循本文档中的规范。

## 适用场景

- 用户要求绑制或生成科研数据图表
- 用户要求将数据可视化为论文发表级别的图形
- 用户提到 "论文图"、"发表级图表"、"期刊图表" 等关键词
- 用户要求导出高分辨率或矢量格式图表

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

### 3.5 配色禁忌

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
import seaborn as sns

# 数据
categories = ['Control', 'Treatment A', 'Treatment B']
means = [10, 15, 12]
sem = [1.2, 1.5, 1.1]  # 标准误

fig, ax = plt.subplots(figsize=(3.54, 2.65))  # 单栏尺寸

# 绘制柱状图
x = np.arange(len(categories))
bars = ax.bar(x, means, width=0.6, color='#4477AA', edgecolor='black', linewidth=0.8)

# 添加误差线
ax.errorbar(x, means, yerr=sem, fmt='none', color='black', capsize=3, capthick=1)

# 添加原始数据点（模拟）
np.random.seed(42)
for i, (mean, se) in enumerate(zip(means, sem)):
    # 模拟原始数据
    raw_data = np.random.normal(mean, se * np.sqrt(10), 10)
    jitter = np.random.normal(0, 0.05, 10)
    ax.scatter([i + jitter[j] for j in range(10)], raw_data, 
               color='white', edgecolor='black', s=15, zorder=3, alpha=0.7)

# 设置标签
ax.set_xticks(x)
ax.set_xticklabels(categories, fontsize=8)
ax.set_ylabel('Value (units)', fontsize=8)
ax.set_xlabel('Group', fontsize=8)

# 设置Y轴从0开始
ax.set_ylim(0, max(means) * 1.3)

# 去除上右边框
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# 添加显著性标记示例
ax.plot([0, 0, 1, 1], [17, 18, 18, 17], 'k-', linewidth=0.8)
ax.text(0.5, 18.5, '*', ha='center', fontsize=10)

plt.tight_layout()
plt.savefig('bar_chart.pdf', dpi=300, bbox_inches='tight')
```



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

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0 | 2026-02-13 | 初始版本，覆盖 Nature/Science/Cell/Lancet/IEEE/PNAS/NEJM 规范 |

---

## 参考来源

本技能文档基于以下官方指南和权威资源编制：

1. **Nature** - Formatting Guide for Authors (nature.com)
2. **Science** - Instructions for Preparing Revised Manuscripts (science.org)
3. **Cell Press** - Figure Guidelines (cell.com)
4. **The Lancet** - Artwork Guidelines (thelancet.com)
5. **IEEE** - Graphic Preparation Guidelines (ieee.org)
6. **PNAS** - Digital Art Guidelines (pnas.org)
7. **NEJM** - Technical Guidelines for Figures (nejm.org)
8. **Morrison et al.** (2021) - Ten Principles for Effective Data Visualization. *PLoS Comput Biol*.
9. **Tufte, E.R.** - The Visual Display of Quantitative Information
10. **Paul Tol** - Color Schemes for Scientific Data (personal.sron.nl/~pault/)
11. **Wong, B.** - Color Blindness Considerations (Nature Methods Points of View)
12. **Matplotlib** - Customizing Matplotlib with style sheets and rcParams

---

*本文档遵循 CC BY 4.0 协议，可自由分享和修改，但需注明来源。*
