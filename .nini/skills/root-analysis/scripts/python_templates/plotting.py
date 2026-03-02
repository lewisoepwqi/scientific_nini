"""
绘图模块 - Python版本

使用matplotlib和seaborn生成出版级图表
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path


# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'Arial']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


class RootLengthPlotter:
    """根长度数据绘图器"""

    # 颜色方案定义
    COLOR_SCHEMES = {
        'high_contrast': [
            '#E31A1C', '#1F78B4', '#33A02C', '#6A3D9A',
            '#FF7F00', '#DEDE8B', '#A65628', '#F781BF',
            '#00CED1', '#006400', '#4B0082', '#FF4500',
            '#DC143C', '#4169E1', '#228B22', '#8A2BE2',
            '#FF8C00', '#FFD700', '#8B4513', '#FF1493',
            '#0080FF', '#32CD32', '#9400D3', '#FF6347'
        ],
        'default': [
            '#808080', '#8FB79D', '#DD3125', '#92BEE1',
            '#4C74B1', '#FC8C5A', '#6BAED6', '#969696',
            '#7F432A', '#A6CEE3', '#1F78B4', '#B2DF8A',
            '#E31A1C', '#FF7F00', '#FF6B6B', '#33A02C',
            '#6A3D9A', '#B15928', '#4ECDC4', '#FDBF6F'
        ],
        'blue': [
            '#DEEBF7', '#C6DBEF', '#9ECAE1', '#6BAED6',
            '#4292C6', '#2171B5', '#08519C', '#08306B',
            '#1E3A8A', '#1E40AF', '#2563EB', '#3B82F6',
            '#60A5FA', '#93C5FD', '#BFDBFE', '#DBEAFE'
        ],
        'green': [
            '#EDF8E9', '#C7E9C0', '#A1D99B', '#74C476',
            '#41AB5D', '#238B45', '#006D2C', '#00441B',
            '#064E3B', '#065F46', '#047857', '#059669',
            '#10B981', '#34D399', '#6EE7B7', '#A7F3D0'
        ],
        'qualitative': [
            '#E41A1C', '#377EB8', '#4DAF4A', '#984EA3',
            '#FF7F00', '#FFFF33', '#A65628', '#F781BF',
            '#999999', '#66C2A5', '#FC8D62', '#8DA0CB',
            '#E78AC3', '#A6D854', '#FFD92F', '#E5C494'
        ]
    }

    def __init__(self, color_scheme='high_contrast'):
        """
        初始化绘图器

        Args:
            color_scheme: 颜色方案名称
        """
        self.color_scheme = color_scheme
        self.colors = self.COLOR_SCHEMES.get(color_scheme, self.COLOR_SCHEMES['high_contrast'])

    def create_color_map(self, samples, ordered_samples=None):
        """
        创建样本到颜色的映射

        Args:
            samples: 样本列表
            ordered_samples: 可选的样本排序

        Returns:
            dict: {sample: color}
        """
        # 排序样本
        if ordered_samples is not None:
            sample_order = [s for s in ordered_samples if s in samples]
            missing = [s for s in samples if s not in ordered_samples]
            sample_order.extend(sorted(missing))
        else:
            # 自动排序：Col_0优先，非OE样本，OE样本
            col0 = [s for s in samples if s == 'Col_0']
            oe_samples = [s for s in samples if 'OE' in str(s) and s != 'Col_0']
            other_samples = [s for s in samples if s not in col0 and s not in oe_samples]
            sample_order = col0 + sorted(other_samples) + sorted(oe_samples)

        # 确保有足够的颜色
        if len(sample_order) > len(self.colors):
            # 生成额外颜色
            extra_colors = self._generate_extra_colors(len(sample_order) - len(self.colors))
            colors = self.colors + extra_colors
        else:
            colors = self.colors

        # 创建映射
        color_map = {sample: colors[i] for i, sample in enumerate(sample_order)}

        # Col_0强制使用灰色
        if 'Col_0' in color_map:
            color_map['Col_0'] = '#808080'

        return color_map, sample_order

    def _generate_extra_colors(self, n):
        """生成额外的颜色"""
        colors = []
        for i in range(n):
            hue = i / n
            rgb = plt.cm.hsv(hue)
            hex_color = '#{:02x}{:02x}{:02x}'.format(
                int(rgb[0] * 255),
                int(rgb[1] * 255),
                int(rgb[2] * 255)
            )
            colors.append(hex_color)
        return colors

    def plot_root_length(self, data, summary_stats, color_map, sample_order,
                        output_path, figsize=(10, 6)):
        """
        绘制根长度图（分面柱状图+散点+误差线+显著性字母）

        Args:
            data: 原始数据DataFrame
            summary_stats: 统计摘要DataFrame
            color_map: 颜色映射字典
            sample_order: 样本顺序列表
            output_path: 输出文件路径
            figsize: 图表尺寸
        """
        # 获取处理组
        treatments = sorted(data['treatment'].unique(),
                          key=lambda x: (x != 'Mock', x))  # Mock优先

        n_treatments = len(treatments)

        # 创建子图
        fig, axes = plt.subplots(1, n_treatments, figsize=figsize,
                                sharey=True, squeeze=False)
        axes = axes.flatten()

        for idx, treatment in enumerate(treatments):
            ax = axes[idx]

            # 筛选数据
            treatment_data = data[data['treatment'] == treatment]
            treatment_summary = summary_stats[summary_stats['treatment'] == treatment]

            # 确保样本顺序
            treatment_summary = treatment_summary.set_index('sample').loc[
                [s for s in sample_order if s in treatment_summary['sample'].values]
            ].reset_index()

            x_pos = np.arange(len(treatment_summary))

            # 绘制柱状图
            bars = ax.bar(x_pos, treatment_summary['mean'],
                         color=[color_map[s] for s in treatment_summary['sample']],
                         alpha=0.5, edgecolor='black', linewidth=1.2,
                         label='Mean')

            # 绘制散点
            for i, sample in enumerate(treatment_summary['sample']):
                sample_data = treatment_data[treatment_data['sample'] == sample]
                y_values = sample_data['length'].values
                x_values = np.random.normal(i, 0.04, len(y_values))  # 抖动
                ax.scatter(x_values, y_values,
                          color=color_map[sample], alpha=0.8,
                          s=30, zorder=3, edgecolors='black', linewidth=0.5)

            # 绘制误差线
            ax.errorbar(x_pos, treatment_summary['mean'],
                       yerr=treatment_summary['sem'],
                       fmt='none', ecolor='black', capsize=4,
                       linewidth=1.5, zorder=4)

            # 添加显著性字母
            y_max = (treatment_summary['mean'] + treatment_summary['sem']).max()
            y_pos = y_max * 1.15

            for i, (_, row) in enumerate(treatment_summary.iterrows()):
                if pd.notna(row['letter']) and row['letter']:
                    ax.text(i, y_pos, row['letter'],
                           ha='center', va='bottom',
                           fontsize=14, fontweight='bold')

            # 设置标签和标题
            ax.set_xlabel('Sample', fontsize=12, fontweight='bold')
            if idx == 0:
                ax.set_ylabel('Root length (cm)', fontsize=12, fontweight='bold')
            ax.set_title(treatment, fontsize=14, fontweight='bold')

            # 设置x轴
            ax.set_xticks(x_pos)
            ax.set_xticklabels(treatment_summary['sample'],
                              rotation=45, ha='right')

            # 网格
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_axisbelow(True)

            # 美化
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

        # 调整布局
        plt.tight_layout()

        # 保存
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"根长度图已保存: {output_path}")

    def plot_ratio(self, ratio_df, ratio_letters, color_map, sample_order,
                  output_path, figsize=(8, 6)):
        """
        绘制比率图

        Args:
            ratio_df: 比率数据DataFrame
            ratio_letters: 显著性字母字典
            color_map: 颜色映射
            sample_order: 样本顺序
            output_path: 输出路径
            figsize: 图表尺寸
        """
        if len(ratio_df) == 0:
            print("跳过比率图（无数据）")
            return

        # 计算统计量
        summary = ratio_df.groupby('sample').agg({
            'ratio': ['mean', 'sem', 'max']
        }).reset_index()
        summary.columns = ['sample', 'mean', 'sem', 'max']

        # 添加字母
        summary['letter'] = summary['sample'].map(ratio_letters)

        # 排序
        summary = summary.set_index('sample').loc[
            [s for s in sample_order if s in summary.index]
        ].reset_index()

        # 创建图表
        fig, ax = plt.subplots(figsize=figsize)

        x_pos = np.arange(len(summary))

        # 柱状图
        bars = ax.bar(x_pos, summary['mean'],
                     color=[color_map[s] for s in summary['sample']],
                     alpha=0.5, edgecolor='black', linewidth=1.2)

        # 散点
        for i, sample in enumerate(summary['sample']):
            sample_data = ratio_df[ratio_df['sample'] == sample]
            y_values = sample_data['ratio'].values
            x_values = np.random.normal(i, 0.04, len(y_values))
            ax.scatter(x_values, y_values,
                      color=color_map[sample], alpha=0.8,
                      s=40, zorder=3, edgecolors='black', linewidth=0.5)

        # 误差线
        ax.errorbar(x_pos, summary['mean'], yerr=summary['sem'],
                   fmt='none', ecolor='black', capsize=4,
                   linewidth=1.5, zorder=4)

        # 显著性字母
        y_max = (summary['mean'] + summary['sem']).max()
        y_pos = y_max * 1.15

        for i, (_, row) in enumerate(summary.iterrows()):
            if pd.notna(row['letter']) and row['letter']:
                ax.text(i, y_pos, row['letter'],
                       ha='center', va='bottom',
                       fontsize=14, fontweight='bold')

        # 参考线（ratio=1）
        ax.axhline(y=1.0, color='red', linestyle='--',
                  linewidth=1.5, alpha=0.7, label='Baseline (ratio=1)')

        # 标签
        ax.set_xlabel('Sample', fontsize=12, fontweight='bold')
        ax.set_ylabel('Root length ratio (Treatment/Mock)', fontsize=12, fontweight='bold')
        ax.set_title('Relative Root Length Analysis', fontsize=14, fontweight='bold')

        # x轴
        ax.set_xticks(x_pos)
        ax.set_xticklabels(summary['sample'], rotation=45, ha='right')

        # 网格
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)

        # 美化
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.legend(loc='best', frameon=False)

        # 保存
        plt.tight_layout()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

        print(f"比率图已保存: {output_path}")

    def save_color_mapping(self, color_map, sample_order, output_path):
        """保存颜色映射到CSV"""
        df = pd.DataFrame({
            'sample': sample_order,
            'color': [color_map[s] for s in sample_order]
        })

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

        print(f"颜色映射已保存: {output_path}")

    def save_sample_order(self, sample_order, output_path):
        """保存样本顺序到文本文件"""
        lines = ["样本排列顺序（左→右）:"]
        for i, sample in enumerate(sample_order, 1):
            lines.append(f"{i}. {sample}")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"样本顺序已保存: {output_path}")
