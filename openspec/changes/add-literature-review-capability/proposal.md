## Why

C1 在提示词层面定义了文献调研阶段策略（检索→筛选→综合→输出），C5 提供了插件系统和 NetworkPlugin 骨架。但目前缺少实际的文献调研 Skill 和文献检索工具。本 change 创建 `literature-review` Skill（带 contract）和 `search_literature` 工具，实现 L1 级别的文献调研引导能力。离线时通过 C5 的降级机制明确告知用户。

## What Changes

- **新建 Markdown Skill**：在 `.nini/skills/literature-review/SKILL.md` 中创建文献调研 Skill，包含 contract 段声明四步 DAG（检索→筛选→综合→输出）、trust_ceiling=t1、证据溯源要求。
- **新增文献检索工具**：在 `tools/` 中新增 `search_literature` 工具，通过 NetworkPlugin 调用外部学术搜索 API（如 Semantic Scholar、CrossRef），支持关键词检索和基本筛选。
- **扩展 NetworkPlugin**：在 C5 的 NetworkPlugin 中集成学术搜索 API 的可用性检测。
- **离线模式支持**：当 NetworkPlugin 不可用时，Skill 的检索步骤自动降级为引导用户手动上传文献 PDF 或提供引用列表。

## Non-Goals

- 不实现全文下载功能。
- 不实现引文网络分析（属于更高级别能力）。
- 不实现文献管理数据库（仅在会话级存储）。
- 不实现 L2/L3 级别的自动化综述撰写。

## Capabilities

### New Capabilities

- `literature-review-skill`: 文献调研引导 Skill——涵盖四步工作流、contract 契约、离线降级、证据溯源
- `literature-search-tool`: 文献检索工具——涵盖学术 API 集成、关键词检索、结果筛选

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`.nini/skills/literature-review/SKILL.md`（新建）、`src/nini/tools/search_literature.py`（新建）、`src/nini/tools/registry.py`（注册）、`src/nini/plugins/network.py`（扩展 API 检测）
- **影响范围**：新增 Skill 和 Tool，扩展 NetworkPlugin
- **API / 依赖**：依赖外部学术 API（Semantic Scholar 免费 API、CrossRef），通过 NetworkPlugin 管理；`httpx`（已是现有依赖）
- **风险**：外部 API 可用性不确定，通过降级机制缓解；文献检索结果质量依赖 API，通过 trust_ceiling=t1 限制输出等级
- **回滚**：删除新建文件 + revert registry.py 和 network.py 的扩展即可恢复
- **验证方式**：单元测试验证 search_literature 工具（mock API）、Skill contract 解析；集成测试验证离线降级路径
