<!-- keywords: t检验, 比较, 差异, 均值, 两组, 多组, anova, 方差分析, 独立样本, 配对, mann-whitney, 组间, 显著性 -->
<!-- priority: high -->
# 组间比较方法选择指南

## 两组比较

| 条件 | 推荐方法 |
|------|---------|
| 正态分布 + 方差齐性 | 独立样本 t 检验 |
| 正态分布 + 方差不齐 | Welch's t 检验（默认推荐） |
| 非正态分布 | Mann-Whitney U 检验 |
| 配对/重复测量数据 | 配对 t 检验 |
| 配对 + 非正态 | Wilcoxon 符号秩检验 |

## 多组比较

| 条件 | 推荐方法 |
|------|---------|
| 正态 + 方差齐性 | 单因素 ANOVA |
| 正态 + 方差不齐 | Welch's ANOVA |
| 非正态 | Kruskal-Wallis 检验 |
| 重复测量 | 重复测量 ANOVA |

## 事后检验（Post-hoc）

- ANOVA 显著后 → Tukey HSD（最常用）
- 方差不齐 → Games-Howell
- Kruskal-Wallis 显著后 → Dunn's test（Bonferroni 校正）
- 与对照组比较 → Dunnett's test

## 关键检查步骤

1. **正态性检验**：Shapiro-Wilk（n < 50）或 Kolmogorov-Smirnov（n >= 50）
2. **方差齐性检验**：Levene's test
3. **样本量评估**：每组至少 20-30 个观测值以保证检验力
4. **效应量报告**：Cohen's d（两组）或 η²（ANOVA）
