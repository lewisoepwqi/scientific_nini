# Change: 增强对话可观测性与混合技能体系

## Why

当前 Nini 的对话与技能能力已经可用，但在以下方面仍有改进空间：

1. 对话可观测性不足：前端能看到 `text/tool_call/tool_result`，但缺少检索上下文可视化与标准化会话压缩能力，长会话成本与可审计性受限。
2. 提示词治理可维护性不足：系统提示词目前集中在单文件模板，缺少可组合组件与运行时治理策略。
3. 技能扩展路径单一：当前以 Python Function Skill 为主，缺少“文件型技能（Markdown 指令）”的可发现与可管理能力。
4. 前后端技能可见性不足：没有统一的技能快照与查询接口，不利于前端展示、调试与运维审计。

本变更参考 Mini-OpenClaw 的可借鉴实践，但保持 Nini 现有科研技能执行优势（结构化 function calling + 强类型结果）。

## What Changes

### 1) 对话系统增强（Conversation）
- 新增可观测检索事件：在 WebSocket 事件流中增加 `retrieval` 事件，向前端明确输出检索来源、片段与分数（可脱敏）。
- 新增会话压缩机制：提供会话压缩接口，支持“归档旧消息 + 摘要注入上下文 + 历史可追溯”。
- 新增提示词组件化：将系统提示词从单体模板升级为可组合组件（如策略/身份/用户画像/代理操作协议/长期记忆），并定义截断与安全治理规则。
- 统一事件契约：明确 `turn_id`、`tool_call_id` 的关联规则，保证多段响应和工具链路可追踪。

### 2) 技能系统增强（Skills）
- 新增混合技能发现：保留 Python 技能注册中心，同时新增 Markdown 技能扫描器（`skills/*/SKILL.md`）。
- 新增技能快照：启动或刷新时生成技能快照（如 `SKILLS_SNAPSHOT.md`），用于提示词注入与调试。
- 新增技能查询接口：提供统一 `/api/skills`，返回 Function Skill + Markdown Skill 的聚合视图（名称、描述、类型、来源、可见状态）。
- 定义技能调用协议：当 Agent 计划使用 Markdown 技能时，必须先读取技能定义，再执行受控工具步骤，禁止直接臆测参数。

### 3) 兼容性与迁移
- 默认保持现有 Function Skill 行为不变。
- 本次变更以“增量能力”方式交付，不移除既有接口。
- 新增能力默认可配置开关，便于灰度启用与回滚。

## Impact

- Affected specs:
  - `conversation`（新增）
  - `skills`（新增）
- Affected code:
  - `src/nini/agent/runner.py`
  - `src/nini/api/websocket.py`
  - `src/nini/api/routes.py`
  - `src/nini/agent/prompts/`
  - `src/nini/skills/registry.py`
  - `src/nini/skills/manifest.py`
  - `web/src/store.ts`
  - `tests/`（新增/更新协议与回归测试）
