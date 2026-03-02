"""
统计分析模块 - Python版本

使用scipy和statsmodels进行ANOVA和Tukey HSD分析
"""

import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.libqsturng import psturng
import warnings


class RootLengthAnalyzer:
    """根长度统计分析器"""

    def __init__(self, data):
        """
        初始化分析器

        Args:
            data: pandas DataFrame，包含sample, treatment, length列
        """
        self.data = data.copy()
        self.anova_results = {}
        self.tukey_results = {}
        self.ratio_analysis = None

    def perform_anova(self):
        """
        对每个处理组执行ANOVA分析

        Returns:
            dict: 每个处理组的ANOVA结果
        """
        print("\n=== 执行ANOVA分析 ===\n")

        results = {}

        for treatment in self.data['treatment'].unique():
            treatment_data = self.data[self.data['treatment'] == treatment]

            # 按样本分组
            groups = [
                group['length'].values
                for name, group in treatment_data.groupby('sample')
            ]

            # 执行ANOVA
            f_stat, p_value = stats.f_oneway(*groups)

            # Tukey HSD事后检验
            tukey_result = pairwise_tukeyhsd(
                endog=treatment_data['length'],
                groups=treatment_data['sample'],
                alpha=0.05
            )

            # 生成显著性字母
            letters = self._generate_significance_letters(tukey_result)

            results[treatment] = {
                'f_statistic': f_stat,
                'p_value': p_value,
                'tukey': tukey_result,
                'letters': letters,
                'n_groups': len(groups),
                'n_observations': len(treatment_data)
            }

            # 打印结果
            print(f"处理组: {treatment}")
            print(f"  F统计量: {f_stat:.4f}")
            print(f"  p值: {p_value:.6f}")
            if p_value < 0.05:
                print(f"  结论: 样本间存在显著差异 (p < 0.05)")
            else:
                print(f"  结论: 样本间无显著差异 (p >= 0.05)")
            print(f"\n  显著性字母:")
            for sample, letter in sorted(letters.items()):
                print(f"    {sample}: {letter}")
            print()

        self.anova_results = results
        return results

    def _generate_significance_letters(self, tukey_result):
        """
        从Tukey HSD结果生成显著性字母

        Args:
            tukey_result: statsmodels TukeyHSD结果

        Returns:
            dict: {sample: letter}
        """
        # 获取所有样本
        groups = tukey_result.groupsunique

        # 创建显著性矩阵
        n_groups = len(groups)
        sig_matrix = np.zeros((n_groups, n_groups), dtype=bool)

        # 填充矩阵（True表示无显著差异）
        for i in range(n_groups):
            sig_matrix[i, i] = True

        # 从Tukey结果填充
        summary_df = pd.DataFrame(data=tukey_result.summary().data[1:],
                                  columns=tukey_result.summary().data[0])

        for _, row in summary_df.iterrows():
            group1 = row['group1']
            group2 = row['group2']
            reject = row['reject']

            idx1 = np.where(groups == group1)[0][0]
            idx2 = np.where(groups == group2)[0][0]

            if not reject:  # 不拒绝H0，即无显著差异
                sig_matrix[idx1, idx2] = True
                sig_matrix[idx2, idx1] = True

        # 生成字母
        letters = self._matrix_to_letters(groups, sig_matrix)

        return dict(zip(groups, letters))

    def _matrix_to_letters(self, groups, sig_matrix):
        """
        将显著性矩阵转换为字母标记

        Args:
            groups: 样本名称数组
            sig_matrix: 显著性矩阵（True=无显著差异）

        Returns:
            list: 每个样本的字母标记
        """
        n = len(groups)
        letters = [''] * n
        current_letter = 0
        alphabet = 'abcdefghijklmnopqrstuvwxyz'

        # 按平均值排序
        group_indices = list(range(n))

        # 分配字母
        assigned = [False] * n

        for i in group_indices:
            if not assigned[i]:
                # 找到所有与i无显著差异的组
                similar_groups = [i]
                for j in range(n):
                    if sig_matrix[i, j] and i != j:
                        similar_groups.append(j)

                # 分配相同字母
                letter = alphabet[current_letter % 26]
                for idx in similar_groups:
                    if letters[idx]:
                        letters[idx] += letter
                    else:
                        letters[idx] = letter
                    assigned[idx] = True

                current_letter += 1

        return letters

    def calculate_summary_statistics(self):
        """
        计算描述性统计量

        Returns:
            pandas DataFrame: 包含均值、标准误等统计量
        """
        summary = self.data.groupby(['treatment', 'sample']).agg({
            'length': ['count', 'mean', 'std', 'sem', 'min', 'max']
        }).reset_index()

        summary.columns = ['treatment', 'sample', 'n', 'mean', 'std', 'sem', 'min', 'max']

        # 添加显著性字母
        letter_list = []
        for _, row in summary.iterrows():
            treatment = row['treatment']
            sample = row['sample']
            if treatment in self.anova_results:
                letter = self.anova_results[treatment]['letters'].get(sample, '')
            else:
                letter = ''
            letter_list.append(letter)

        summary['letter'] = letter_list

        return summary

    def calculate_ratios(self, baseline_treatment='Mock'):
        """
        计算相对于基线处理组的比率

        Args:
            baseline_treatment: 基线处理组名称

        Returns:
            pandas DataFrame: 比率数据
        """
        print(f"\n=== 计算比率 (基线: {baseline_treatment}) ===\n")

        if baseline_treatment not in self.data['treatment'].unique():
            raise ValueError(f"基线处理组 '{baseline_treatment}' 不存在")

        # 计算基线组的均值
        baseline_means = self.data[
            self.data['treatment'] == baseline_treatment
        ].groupby('sample')['length'].mean().to_dict()

        # 计算非基线组的比率
        ratio_data = []

        for treatment in self.data['treatment'].unique():
            if treatment == baseline_treatment:
                continue

            treatment_data = self.data[self.data['treatment'] == treatment]

            for _, row in treatment_data.iterrows():
                sample = row['sample']
                length = row['length']
                baseline_mean = baseline_means.get(sample, np.nan)

                if pd.notna(baseline_mean) and baseline_mean > 0:
                    ratio = length / baseline_mean
                    ratio_data.append({
                        'sample': sample,
                        'treatment': treatment,
                        'length': length,
                        'baseline_mean': baseline_mean,
                        'ratio': ratio
                    })

        ratio_df = pd.DataFrame(ratio_data)

        if len(ratio_df) > 0:
            print(f"计算了 {len(ratio_df)} 个比率值")
            print(f"比率范围: {ratio_df['ratio'].min():.3f} - {ratio_df['ratio'].max():.3f}")
        else:
            print("警告: 没有计算出任何比率值")

        return ratio_df

    def analyze_ratios(self, ratio_df):
        """
        对比率数据执行ANOVA分析

        Args:
            ratio_df: 比率数据DataFrame

        Returns:
            dict: 比率分析结果
        """
        if len(ratio_df) == 0:
            return None

        print("\n=== 比率ANOVA分析 ===\n")

        # 按样本分组
        groups = [
            group['ratio'].values
            for name, group in ratio_df.groupby('sample')
        ]

        # ANOVA
        f_stat, p_value = stats.f_oneway(*groups)

        # Tukey HSD
        tukey_result = pairwise_tukeyhsd(
            endog=ratio_df['ratio'],
            groups=ratio_df['sample'],
            alpha=0.05
        )

        # 显著性字母
        letters = self._generate_significance_letters(tukey_result)

        result = {
            'f_statistic': f_stat,
            'p_value': p_value,
            'tukey': tukey_result,
            'letters': letters
        }

        # 打印结果
        print(f"F统计量: {f_stat:.4f}")
        print(f"p值: {p_value:.6f}")
        if p_value < 0.05:
            print("结论: 样本对处理的响应存在显著差异 (p < 0.05)")
        else:
            print("结论: 样本对处理的响应无显著差异 (p >= 0.05)")
        print(f"\n显著性字母:")
        for sample, letter in sorted(letters.items()):
            print(f"  {sample}: {letter}")
        print()

        self.ratio_analysis = result
        return result

    def get_anova_summary_text(self):
        """
        生成ANOVA结果的文本摘要

        Returns:
            str: 文本摘要
        """
        lines = []
        lines.append("=" * 60)
        lines.append("ANOVA 分析结果摘要")
        lines.append("=" * 60)

        for treatment, result in self.anova_results.items():
            lines.append(f"\n处理组: {treatment}")
            lines.append(f"  样本数: {result['n_groups']}")
            lines.append(f"  观测值总数: {result['n_observations']}")
            lines.append(f"  F统计量: {result['f_statistic']:.4f}")
            lines.append(f"  p值: {result['p_value']:.6f}")

            if result['p_value'] < 0.001:
                sig = "***"
            elif result['p_value'] < 0.01:
                sig = "**"
            elif result['p_value'] < 0.05:
                sig = "*"
            else:
                sig = "ns"

            lines.append(f"  显著性: {sig}")
            lines.append(f"\n  显著性字母:")

            for sample, letter in sorted(result['letters'].items()):
                lines.append(f"    {sample}: {letter}")

        if self.ratio_analysis:
            lines.append(f"\n{'=' * 60}")
            lines.append("比率分析结果")
            lines.append("=" * 60)
            lines.append(f"F统计量: {self.ratio_analysis['f_statistic']:.4f}")
            lines.append(f"p值: {self.ratio_analysis['p_value']:.6f}")
            lines.append(f"\n显著性字母:")
            for sample, letter in sorted(self.ratio_analysis['letters'].items()):
                lines.append(f"  {sample}: {letter}")

        return '\n'.join(lines)
