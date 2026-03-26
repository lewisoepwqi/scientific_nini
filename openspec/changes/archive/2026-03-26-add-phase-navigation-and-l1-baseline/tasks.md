## 1. 阶段检测工具

- [x] 1.1 创建 `src/nini/tools/detect_phase.py`，继承 Tool 基类，实现关键词匹配阶段检测
- [x] 1.2 定义关键词 → ResearchPhase 映射表
- [x] 1.3 在 `tools/registry.py` 中注册 detect_phase 工具

## 2. 上下文注入

- [x] 2.1 在 `src/nini/agent/components/context_builder.py` 中集成阶段检测，注入 current_phase 和阶段匹配的推荐列表

## 3. L1 基线测试

- [x] 3.1 编写 `tests/test_l1_baseline.py`：三个新 Skill 可用性、contract 有效性、阶段检测准确性（20 条典型消息）、阶段路由集成
- [x] 3.2 运行 `pytest -q` 确认全部测试通过且无回归
