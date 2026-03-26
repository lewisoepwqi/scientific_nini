## 1. 升级 identity.md

- [x] 1.1 将 `data/prompt_components/identity.md` 从单行文本扩展为结构化多段落身份声明：身份定位（全流程 AI 研究伙伴）、八大阶段覆盖声明（标注数据分析为核心优势）、责任边界声明（协助不替代、高风险需人工复核）
- [x] 1.2 Review：确认 identity.md 内容覆盖 specs/product-identity/spec.md 中所有 Requirement

## 2. 升级 strategy.md

- [x] 2.1 在 `data/prompt_components/strategy.md` 现有内容末尾添加分隔标记，追加通用策略：输出等级标注规范（O1/O2/O3/O4）、风险提示触发规则、降级行为规范
- [x] 2.2 追加文献调研阶段策略：检索 → 筛选 → 综合 → 输出流程、证据溯源要求、离线降级提示、条件触发说明
- [x] 2.3 追加实验设计阶段策略：问题定义 → 设计选择 → 参数计算 → 方案生成流程、伦理提示、人工复核提醒、条件触发说明
- [x] 2.4 追加论文写作阶段策略：结构规划 → 分节撰写 → 修订 → 格式化流程、引用规范、草稿级标注、条件触发说明
- [x] 2.5 Review：确认现有内容（第 1 行到报告生成决策末尾）完全未被修改；确认新增内容覆盖 specs/phase-aware-strategy/spec.md 中所有 Requirement

## 3. 更新 CLAUDE.md

- [x] 3.1 将 `CLAUDE.md` 项目概述段落中的「科研数据分析 AI Agent」更新为与 identity.md 一致的全流程定位描述
- [x] 3.2 Review：确认仅修改了项目概述的定位描述，未改动其他内容

## 4. 验证

- [x] 4.1 运行 `pytest -q` 确认无测试回归
- [x] 4.2 对比升级前后 strategy.md 的现有内容部分，确认无 diff（仅末尾追加）
