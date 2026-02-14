## ADDED Requirements

### Requirement: 混合技能发现机制
系统 SHALL 同时支持 Function Skill 与 Markdown Skill 的发现与聚合，形成统一技能视图供 Agent 与前端使用。

#### Scenario: 启动时扫描技能目录
- **WHEN** 服务启动或触发技能刷新
- **THEN** 系统扫描约定目录下的 `SKILL.md` 并解析技能元信息
- **AND** 与已注册 Function Skill 合并为统一技能清单

#### Scenario: 技能定义异常时降级处理
- **WHEN** 某个 `SKILL.md` 缺失必要字段或解析失败
- **THEN** 系统记录告警并跳过该技能
- **AND** 不影响其他技能加载

### Requirement: 技能快照生成与注入
系统 SHALL 生成技能快照文件（如 `SKILLS_SNAPSHOT.md`）并支持注入到对话上下文，提升技能可见性与可审计性。

#### Scenario: 快照文件按刷新周期更新
- **WHEN** 技能列表发生变化（新增、删除、更新）
- **THEN** 系统刷新技能快照文件
- **AND** 快照内容包含技能名称、描述、来源位置和类型

#### Scenario: Prompt 注入使用最新快照
- **WHEN** Agent 构建新一轮对话上下文
- **THEN** 使用最新技能快照作为能力参考信息

### Requirement: Markdown 技能调用协议
系统 SHALL 对 Markdown Skill 执行“先读定义再执行”的协议约束，禁止在未读取技能定义时直接猜测步骤或参数。

#### Scenario: 正常执行 Markdown 技能
- **WHEN** Agent 决定使用某个 Markdown Skill
- **THEN** 首先读取该技能定义文件内容
- **AND** 按定义步骤调用受控工具完成任务

#### Scenario: 缺少定义文件时拒绝执行
- **WHEN** 目标 Markdown Skill 的定义文件不可读或不存在
- **THEN** 系统拒绝执行该技能并返回错误说明

### Requirement: 统一技能查询接口
系统 SHALL 提供统一技能查询 API，返回 Function/Markdown 双类型技能的可见状态与元数据。

#### Scenario: 获取技能列表
- **WHEN** 客户端调用技能列表接口
- **THEN** 返回技能数组，至少包含 `name`、`description`、`type`、`location`、`enabled`

#### Scenario: 按类型过滤技能
- **WHEN** 客户端请求按技能类型过滤（例如仅 `markdown`）
- **THEN** 接口返回匹配类型的技能子集
