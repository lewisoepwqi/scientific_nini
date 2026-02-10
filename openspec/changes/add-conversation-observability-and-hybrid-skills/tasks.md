# 任务清单：对话可观测性与混合技能体系

## 1. 对话系统（P0）

- [x] 1.1 在 `src/nini/agent/runner.py` 增加 `retrieval` 事件数据结构与产出路径（含 `turn_id`）。
- [x] 1.2 在 `src/nini/api/websocket.py` 转发 `retrieval` 事件并保持 JSON 安全序列化。
- [x] 1.3 在 `web/src/store.ts` 增加 `retrieval` 事件消费逻辑与消息绑定策略。
- [x] 1.4 增加会话压缩服务（归档旧消息、生成摘要、写入压缩上下文）。
- [x] 1.5 增加会话压缩 API（建议：`POST /api/sessions/{id}/compress`）。
- [x] 1.6 定义压缩后的上下文注入规则（仅注入摘要，不回放归档正文）。
- [x] 1.7 更新会话存储读写逻辑，支持压缩上下文字段与归档目录。

## 2. 提示词组件化（P0）

- [x] 2.1 新建 Prompt 组件装配器（替代单体 `SYSTEM_PROMPT` 直出）。
- [x] 2.2 定义组件装配顺序与长度上限（超长截断并标记）。
- [x] 2.3 增加“动态组件刷新”策略：下一轮请求自动生效，无需重启。
- [x] 2.4 增加提示词安全策略单测（注入与越权文本过滤保持有效）。

## 3. 混合技能体系（P0）

- [x] 3.1 新增 Markdown 技能扫描器：扫描 `skills/*/SKILL.md` 并解析元信息。
- [x] 3.2 生成技能快照文件（`SKILLS_SNAPSHOT.md`），供 Prompt 注入与审计。
- [x] 3.3 扩展技能数据模型，统一表示 Function Skill 与 Markdown Skill。
- [x] 3.4 新增技能聚合接口（建议：`GET /api/skills`）。
- [x] 3.5 在 Agent 调用协议中加入“先读技能定义再执行”的约束。
- [x] 3.6 对同名技能冲突增加策略（优先级/警告/禁用其一）。

## 4. 前端与可观测性（P1）

- [x] 4.1 前端增加检索卡片展示（查询词、命中片段、来源）。
- [x] 4.2 前端增加技能清单展示（按类型区分 Function/Markdown）。
- [x] 4.3 前端增加会话压缩入口与结果反馈。
- [x] 4.4 保证现有 `tool_call/tool_result/chart/data/artifact` 展示不回归。

## 5. 测试与验收（P0）

- [x] 5.1 后端单测：`retrieval` 事件、压缩逻辑、技能扫描与快照。
- [x] 5.2 WebSocket 集成测试：事件顺序与字段完整性。
- [x] 5.3 API 测试：`/api/skills` 与会话压缩端点。
- [x] 5.4 前端测试：事件消费、技能列表渲染、压缩交互。
- [x] 5.5 最小回归：`pytest -q` 与 `cd web && npm run build` 通过。
