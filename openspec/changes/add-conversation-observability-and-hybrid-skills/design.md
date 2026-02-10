## Context

Nini 当前以 Function Skill + ReAct 循环为核心，已经具备稳定的科研分析执行能力。
本次变更目标不是替换现有架构，而是在不破坏主链路的前提下补齐三类能力：

1. 对话可观测性：让“检索、工具、分段响应、压缩摘要”可被前端与运维审计。
2. 提示词治理：从单体模板升级为可组合组件，降低维护成本。
3. 技能扩展性：在保留 Python 技能的同时，支持文件型技能发现与管理。

## Goals / Non-Goals

### Goals

- 定义稳定的对话事件契约：支持 `retrieval`，并保持 `turn_id/tool_call_id` 关联。
- 引入会话压缩：控制长会话上下文成本，保留历史可追溯性。
- 引入 Prompt 组件化装配：支持组件级更新与截断治理。
- 引入混合技能发现与快照：Function Skill + Markdown Skill 共存。
- 提供统一技能查询接口：供前端展示与调试。

### Non-Goals

- 不移除或重写现有 Function Skill 执行链路。
- 不引入高风险通用终端工具作为默认能力。
- 不在本次变更中完成完整的多租户权限体系。

## Decisions

### 决策 1：事件模型增量扩展，不改动现有事件语义

- 做法：新增 `retrieval` 事件；保留现有 `iteration_start/text/tool_call/tool_result/done`。
- 原因：前端已有事件消费逻辑，增量扩展风险最低。

### 决策 2：压缩采用“归档 + 摘要注入”而非“直接删除历史”

- 做法：将旧消息写入归档文件；会话主上下文仅注入摘要文本。
- 原因：兼顾成本控制与审计可追溯。

### 决策 3：技能体系采用双轨并存

- 做法：
  - Function Skill 继续通过 `SkillRegistry` 暴露给模型工具调用。
  - Markdown Skill 通过扫描器发现，并写入 `SKILLS_SNAPSHOT.md`。
- 原因：保留强类型执行能力，同时提升技能扩展灵活性。

### 决策 4：Prompt 采用组件装配器

- 做法：按固定顺序装配多个文本组件，统一做长度限制与安全清洗。
- 原因：避免单文件 prompt 膨胀，支持运维快速迭代。

## Data Model

### 会话压缩元数据（建议）

- 会话目录新增：`archive/`（保存被压缩消息）
- 会话元数据新增字段（可选）：
  - `compressed_context`: `string`
  - `compressed_rounds`: `int`
  - `last_compressed_at`: `datetime`

### 技能聚合模型（建议）

- `type`: `function | markdown`
- `name`: 技能标识
- `description`: 描述
- `location`: 定义来源（Python 模块路径或 `SKILL.md` 路径）
- `enabled`: 是否可用
- `metadata`: 可选扩展（参数 schema、分类、示例等）

## Risks / Trade-offs

- 风险 1：新增压缩逻辑可能影响历史回放一致性。
  - 缓解：保留归档文件并增加回归测试覆盖。
- 风险 2：Markdown 技能描述质量不稳定，可能导致执行偏差。
  - 缓解：强制“先读定义再执行”协议，并限制可调用工具集合。
- 风险 3：Prompt 组件化引入更多配置文件，可能增加运维复杂度。
  - 缓解：提供默认模板与组件缺失降级策略。

## Migration Plan

1. 第一步上线事件扩展与前端兼容（`retrieval` 可选渲染）。
2. 第二步上线会话压缩 API 与归档机制（默认关闭，灰度开启）。
3. 第三步上线技能扫描与快照（只读模式，不参与执行决策）。
4. 第四步将 Markdown 技能纳入 Agent 规划上下文（受开关控制）。

## Rollback Plan

- 若出现异常，可通过配置关闭：
  - `retrieval` 事件发送
  - 会话压缩注入
  - Markdown 技能扫描与快照注入
- 回滚时不删除归档数据与快照文件，避免数据损失。

## Open Questions

- Markdown Skill 与同名 Function Skill 冲突时，默认优先级如何定义？
- 会话压缩触发策略采用手动触发、阈值自动触发，还是混合策略？
- 前端是否需要提供“查看归档摘要版本历史”入口？
