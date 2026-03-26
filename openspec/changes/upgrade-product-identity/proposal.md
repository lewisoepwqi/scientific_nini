## Why

Nini 的产品定位正在从「科研数据分析 AI 助手」升级为「科研全流程 AI 伙伴」（见 `docs/nini-vision-charter.md` v2.0）。当前 `identity.md` 仍将 Nini 定义为"科研数据分析 AI 助手"，`strategy.md` 仅包含数据分析的 7 步流程，无法引导 Agent 在文献调研、实验设计、论文写作等新阶段提供适当的交互。这是 V1 迭代的第一个 change（C1），为后续所有能力扩展奠定身份与策略基础。

## What Changes

- **升级 `data/prompt_components/identity.md`**：从"科研数据分析 AI 助手"升级为"贯穿科研全流程的 AI 研究伙伴"，明确覆盖八大研究阶段，声明核心优势仍在数据分析，并加入"人类最终负责"的责任边界声明。
- **升级 `data/prompt_components/strategy.md`**：在保留现有数据分析 7 步流程的基础上，新增阶段感知的策略路由结构——包含通用策略（任务规划、输出规范、风险提示、降级行为）和三个新阶段策略（文献调研、实验设计、论文写作）。
- **更新 `CLAUDE.md` 项目概述段落**：将"科研数据分析 AI Agent"的定位描述同步更新为全流程定位，确保开发者指引与产品定位一致。

## Non-Goals

- 不修改任何 Python/TypeScript 代码逻辑。
- 不新增 Tool、Capability 或 Skill。
- 不改变前端 UI。
- 不引入新依赖。

## Capabilities

### New Capabilities

- `product-identity`: 产品身份定义——涵盖 identity.md 的愿景、使命、阶段覆盖声明和责任边界
- `phase-aware-strategy`: 阶段感知策略路由——涵盖 strategy.md 的通用策略 + 多阶段策略结构

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`data/prompt_components/identity.md`、`data/prompt_components/strategy.md`、`CLAUDE.md`
- **影响范围**：Agent 的系统提示词层（System Prompt），影响所有新会话的 Agent 行为基调
- **API / 依赖**：无变化
- **风险**：提示词变更可能影响数据分析阶段的现有行为质量。需通过回归测试验证分析链路无退化。
- **回滚**：直接 revert 提示词文件即可恢复，零代码侵入。
- **验证方式**：对比升级前后，在数据分析场景下 Agent 行为是否保持一致；在新阶段场景下 Agent 是否能识别并给出适当的阶段性回应。
