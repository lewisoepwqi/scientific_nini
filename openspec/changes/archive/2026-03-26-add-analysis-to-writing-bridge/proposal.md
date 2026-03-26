## Why

现有 `article_draft` Capability 和 `.nini/skills/article-draft/` Skill 已提供论文初稿生成能力，但缺少从数据分析结果到论文写作的结构化桥接。用户完成数据分析后，需要手动整理统计结果、图表引用、方法描述才能开始写作。本 change 创建一个写作引导 Skill（带 contract），自动收集当前会话的分析产物（统计结果、图表、方法记录），生成结构化的写作素材包，并引导用户按章节撰写论文。

## What Changes

- **新建写作引导 Skill**：在 `.nini/skills/writing-guide/SKILL.md` 中创建论文写作引导 Skill，包含 contract 段声明步骤（收集素材→结构规划→分节撰写→修订）、trust_ceiling=t1。
- **新增会话产物收集工具**：在 `tools/` 中新增 `collect_artifacts` 工具，自动从当前会话中收集统计结果、图表、方法记录等产物，生成结构化写作素材包。
- **扩展现有 article-draft Skill**：更新 `.nini/skills/article-draft/SKILL.md` 的 frontmatter，新增 contract 段（可选，保持向后兼容）。

## Non-Goals

- 不实现完整的论文自动生成（仅引导和辅助）。
- 不实现与 LaTeX 或 Word 模板的格式化集成。
- 不替代现有 article_draft Skill（而是补充结构化引导层）。

## Capabilities

### New Capabilities

- `writing-guide-skill`: 论文写作引导 Skill——涵盖素材收集、结构规划、分节撰写引导、修订建议
- `artifact-collection`: 会话产物收集——涵盖统计结果/图表/方法记录的自动收集和结构化输出

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`.nini/skills/writing-guide/SKILL.md`（新建）、`src/nini/tools/collect_artifacts.py`（新建）、`src/nini/tools/registry.py`（注册）、`.nini/skills/article-draft/SKILL.md`（可选扩展）
- **影响范围**：新增 Skill 和 Tool，不影响现有功能
- **API / 依赖**：无新增外部依赖
- **风险**：素材收集依赖会话中已有的分析产物，若会话中无分析结果则退化为纯引导模式
- **回滚**：删除新建文件 + revert registry.py 即可恢复
- **验证方式**：单元测试验证 collect_artifacts 工具；Skill contract 解析和步骤验证
