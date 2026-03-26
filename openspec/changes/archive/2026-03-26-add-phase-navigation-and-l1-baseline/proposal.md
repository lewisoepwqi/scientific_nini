## Why

C6/C7/C8 各自实现了实验设计、文献调研、论文写作三个新阶段的 Skill。但用户在会话中缺少跨阶段的导航能力——无法查看当前所处阶段、可用能力，也无法在阶段间流转。本 change 实现阶段感知的任务路由和 L1 基线验收测试，作为 V1 全流程能力的集成验证。

## What Changes

- **新增阶段检测工具**：在 `tools/` 中新增 `detect_phase` 工具，基于用户消息的关键词和上下文自动检测当前研究阶段。
- **新增阶段导航提示**：在 `context_builder.py` 中注入当前检测到的阶段信息和该阶段可用的 Capability/Skill 列表。
- **新增 L1 基线测试集**：创建端到端测试，验证三个新阶段 Skill 的基本可用性和阶段路由的准确性。

## Non-Goals

- 不实现阶段间自动流转（用户手动切换）。
- 不实现前端阶段导航 UI（仅后端路由和提示词注入）。
- 不实现阶段记忆（跨会话的阶段状态持久化）。

## Capabilities

### New Capabilities

- `phase-detection`: 阶段检测——涵盖基于消息的阶段自动识别、阶段信息注入
- `l1-baseline-validation`: L1 基线验收——涵盖三个新阶段的端到端测试

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/tools/detect_phase.py`（新建）、`src/nini/tools/registry.py`（注册）、`src/nini/agent/components/context_builder.py`（阶段信息注入）、`tests/test_l1_baseline.py`（新建）
- **影响范围**：Agent 运行时上下文构建新增阶段信息；不影响现有数据分析流程
- **API / 依赖**：无新增外部依赖
- **风险**：阶段检测准确性依赖关键词匹配，可能误判——但误判不影响功能（仅影响推荐的 Capability 列表，用户仍可自由使用任何能力）
- **回滚**：删除新建文件 + revert context_builder.py 和 registry.py 即可恢复
- **验证方式**：L1 基线测试集覆盖三个新阶段的基本场景
