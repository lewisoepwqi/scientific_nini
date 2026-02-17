## 1. CLI 模板与诊断实现

- [x] 1.1 在 `src/nini/__main__.py` 提取 Markdown Skill 默认模板构建函数并替换 TODO 占位内容
- [x] 1.2 在 `src/nini/__main__.py` 提取 kaleido + Chrome 检测辅助函数，细分异常分支并更新 doctor 输出

## 2. 沙箱可观测性实现

- [x] 2.1 在 `src/nini/sandbox/executor.py` 增加模块 logger
- [x] 2.2 为 Matplotlib/Plotly 默认配置降级路径补充日志输出，保持原有降级行为

## 3. 回归验证

- [x] 3.1 在 `tests/test_phase7_cli.py` 增加 Markdown 模板与 doctor 诊断分支测试
- [x] 3.2 新增或更新 sandbox 相关测试，覆盖图表默认配置异常日志分支
- [x] 3.3 运行相关 pytest 子集并根据结果修正
