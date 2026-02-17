# skills Specification

## Purpose
TBD - created by archiving change add-conversation-observability-and-hybrid-skills. Update Purpose after archive.
## Requirements
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

### Requirement: 报告内容分层与默认边界
系统 SHALL 将业务分析报告与系统观测信息分层管理，默认生成的报告正文不得混入性能监控类统计信息。

#### Scenario: 默认生成业务报告
- **WHEN** 用户调用 `generate_report` 且未显式开启观测附录
- **THEN** 报告仅包含业务分析章节（如方法、摘要、结论、图表）
- **AND** 不包含 `分析统计` 类系统监控章节

#### Scenario: 显式开启观测附录
- **WHEN** 用户调用 `generate_report` 并开启观测附录参数
- **THEN** 系统将观测信息写入单独附录章节
- **AND** 不影响正文结论章节结构

### Requirement: 关键发现来源结构化
系统 SHALL 基于结构化执行记录提取“关键发现”，过滤中间失败步骤、过期步骤或被回滚步骤，避免噪声写入正式报告。

#### Scenario: 过滤无效中间步骤
- **WHEN** 同一分析流程中出现后续纠正步骤（如先错误清洗后手动修正）
- **THEN** 报告关键发现不包含被替代的错误中间结果

#### Scenario: 过滤技术噪声
- **WHEN** 工具输出包含运行日志或环境噪声文本
- **THEN** 关键发现提取流程自动排除该类文本

### Requirement: 图表预览去重规则
系统 SHALL 对同一图表的多格式产物执行聚合去重，预览区仅展示一个主格式，其他格式保留下载入口。

#### Scenario: 同图存在 PNG 与 SVG
- **WHEN** 报告生成时检测到同一图表基名对应多个格式
- **THEN** 预览区仅展示优先级最高的一个格式
- **AND** 图表清单保留全部格式下载链接

#### Scenario: 仅有 PDF 图表
- **WHEN** 某图表仅导出为 PDF
- **THEN** 报告预览区展示可访问链接
- **AND** 不生成重复预览条目

### Requirement: Markdown 技能脚手架默认内容可执行
系统 MUST 在执行 `nini skills create --type markdown` 时生成可直接编辑的技能模板，避免输出泛化 TODO 占位内容。

#### Scenario: 生成模板时包含结构化章节
- **WHEN** 用户创建 Markdown 技能脚手架
- **THEN** 生成文件包含 `适用场景`、`步骤`、`注意事项` 三个章节
- **AND** 每个章节包含可执行的填写指引文本

#### Scenario: 生成模板时不包含 TODO 占位
- **WHEN** 用户查看新生成的 `SKILL.md`
- **THEN** 文件内容不包含 `TODO` 关键词
- **AND** frontmatter 中 `name`、`description`、`category` 与输入参数一致

### Requirement: 图片识别技能使用用途路由模型
系统 SHALL 让 `image_analysis` 技能通过统一模型路由器调用视觉模型，并使用 `image_analysis` 用途对应的首选模型配置。

#### Scenario: 图片识别使用用途配置
- **WHEN** 用户在用途路由中为 `image_analysis` 设置了首选提供商
- **THEN** 图片识别技能调用模型时优先使用该提供商
- **AND** 不再硬编码固定提供商/模型

#### Scenario: 图片识别在无用途配置时可回退
- **WHEN** 用户未设置 `image_analysis` 用途首选提供商
- **THEN** 图片识别技能按全局首选与默认优先级回退
- **AND** 在无可用模型时返回清晰错误信息

### Requirement: run_r_code 技能可用性与降级
系统 SHALL 在 R 环境可用且配置启用时注册 `run_r_code`，并在不可用时自动降级为不暴露该技能。

#### Scenario: R 可用时注册
- **WHEN** `settings.r_enabled=true` 且检测到 `Rscript` 可执行
- **THEN** 技能注册中心包含 `run_r_code`

#### Scenario: R 不可用时降级
- **WHEN** 未检测到 `Rscript` 或 `settings.r_enabled=false`
- **THEN** 技能注册中心不注册 `run_r_code`
- **AND** 现有 `run_code` 等技能行为不受影响

### Requirement: run_r_code 执行契约
系统 SHALL 让 `run_r_code` 提供与 `run_code` 对齐的核心结果契约，包括标准输出、结构化结果、DataFrame 预览与图表产物。

#### Scenario: 返回标量结果
- **WHEN** R 代码设置 `result` 为可序列化标量/列表
- **THEN** 技能返回 `success=true`
- **AND** `data.result` 包含结构化结果

#### Scenario: 返回数据框结果
- **WHEN** R 代码设置 `output_df` 为 data.frame
- **THEN** 技能返回 `has_dataframe=true` 与预览
- **AND** 在设置 `save_as` 时写入会话数据集

#### Scenario: 生成图表产物
- **WHEN** R 代码生成可导出的图表文件
- **THEN** 技能返回 `artifacts` 列表
- **AND** 产物可在工作区下载与预览

### Requirement: R 代码执行安全策略
系统 SHALL 对 `run_r_code` 的输入进行静态策略校验，禁止高风险调用与非白名单包使用。

#### Scenario: 拦截危险函数
- **WHEN** R 代码包含 `system()`、`source()` 或 `eval(parse())` 等危险调用
- **THEN** 系统拒绝执行并返回策略错误

#### Scenario: 拦截非白名单包
- **WHEN** R 代码通过 `library()/require()` 引用非白名单包
- **THEN** 系统拒绝执行并说明包名

### Requirement: 代码执行历史一致性
系统 SHALL 将 `run_r_code` 纳入代码执行历史链路，与 `run_code` 保持一致的工具调用追踪能力。

#### Scenario: WebSocket 记录 run_r_code
- **WHEN** Agent 通过 WebSocket 调用 `run_r_code`
- **THEN** 服务端推送 `tool_call` 与 `tool_result` 事件
- **AND** 持久化执行记录包含 `tool_name=run_r_code` 与 `language=r`
