<!-- keywords: 多重比较, 校正, bonferroni, 事后检验, fdr, holm, 多次检验, 假阳性, p值校正, tukey -->
<!-- priority: normal -->
# 多重比较校正方法指南

## 为什么需要多重比较校正

进行多次统计检验时，假阳性率（I 类错误）会膨胀：
- 1 次检验：α = 0.05（5% 假阳性）
- 10 次检验：1 - (1-0.05)^10 ≈ 40% 假阳性
- 20 次检验：1 - (1-0.05)^20 ≈ 64% 假阳性

## 常用校正方法

| 方法 | 控制类型 | 严格程度 | 适用场景 |
|------|---------|---------|---------|
| Bonferroni | FWER | 最严格 | 检验次数少（< 10） |
| Holm | FWER | 较严格 | Bonferroni 的改进，推荐优先使用 |
| Benjamini-Hochberg | FDR | 适中 | 检验次数多（探索性分析） |
| Tukey HSD | FWER | 适中 | ANOVA 事后两两比较 |
| Dunnett | FWER | 适中 | 多组与对照组比较 |

## 选择建议

- **验证性研究**（预设假设）→ Bonferroni 或 Holm
- **探索性研究**（筛选候选）→ Benjamini-Hochberg (FDR)
- **ANOVA 事后比较** → Tukey HSD
- **与对照组比较** → Dunnett
- **检验次数 > 20** → 避免 Bonferroni（过于保守），用 FDR

## FWER vs FDR

- **FWER**（族错误率）：控制至少一个假阳性的概率，更保守
- **FDR**（假发现率）：控制假阳性在所有"显著"结果中的比例，统计效力更高
