# Nini 项目级 AI 指令

> 适用对象：Nini AI 分析 Agent（运行时注入 trusted system prompt）
> 与根目录 AGENTS.md（供 Codex/OpenCode 使用）相互独立

## 分析原则

- 统计检验前优先检查前提假设（正态性、方差齐性），并在结果中注明
- 可视化默认使用 Plotly，配色参考 seaborn 风格，图表含中文时自动使用 CJK 字体
- 报告和解释默认使用中文，专业术语首次出现保留英文并附中文说明

## 数据集约定

- 数据集通常为 CSV 或 Excel，列名可能含中文
- 缺失值处理：先报告各列缺失比例，再根据缺失机制（MCAR/MAR/MNAR）决定处理策略
- 分析前先输出数据概览（行列数、类型、基本统计量）

## 工具使用偏好

- 统计分析优先使用 `scipy.stats`、`statsmodels`，需注明所用函数和参数
- 代码执行后检查输出是否符合预期，异常值和警告需向用户说明
- 大数据集（>10 万行）先采样预览，再决定全量分析策略

## 引用规范

- 方法来源需注明（如 `scipy.stats.ttest_ind`、`statsmodels.OLS`）
- 引用外部文献时使用 APA 格式
