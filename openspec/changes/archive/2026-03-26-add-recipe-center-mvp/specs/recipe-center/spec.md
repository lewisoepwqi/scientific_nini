## ADDED Requirements

### Requirement: Recipe Center 必须提供首批高频科研模板入口

系统 SHALL 在首页或首屏入口提供 `Recipe Center`，至少展示 3 个高频科研任务模板，并保留进入通用会话的入口。

#### Scenario: 用户进入首页查看模板入口
- **WHEN** 用户打开应用首页
- **THEN** 系统展示 `Recipe Center`
- **AND** 至少包含 3 个可直接启动的 Recipe 卡片
- **AND** 页面仍保留通用自由输入入口

#### Scenario: Recipe 卡片展示基础信息
- **WHEN** 用户查看任一 Recipe 卡片
- **THEN** 卡片展示标题、适用场景、必填输入说明与示例输入
- **AND** 卡片展示该 Recipe 的预期输出类型

### Requirement: Recipe 元数据必须使用结构化契约

系统 SHALL 为每个 Recipe 提供结构化元数据契约，至少包含 `recipe_id`、显示名称、输入参数定义、步骤 DAG、默认输出模板、失败回退策略与推荐触发词。

#### Scenario: 后端加载合法 Recipe 配置
- **WHEN** 系统启动并读取 Recipe 配置
- **THEN** 每个 Recipe 都包含完整必填元数据字段
- **AND** 缺失关键字段的配置不得进入可执行列表

#### Scenario: 前端基于元数据渲染输入提示
- **WHEN** 前端拉取 Recipe 列表
- **THEN** 前端可直接依据元数据渲染输入表单或示例提示
- **AND** 不要求前端硬编码单个 Recipe 的字段结构

### Requirement: Recipe Center 必须支持默认推荐与显式启动

系统 SHALL 同时支持显式点击 Recipe 卡片启动，以及根据用户首句意图推荐匹配的 Recipe，但推荐不得强制覆盖用户的通用会话选择。

#### Scenario: 用户点击卡片直接启动 Recipe
- **WHEN** 用户点击某个 Recipe 卡片并提交必要输入
- **THEN** 系统以该 Recipe 创建新任务
- **AND** 会话中记录所选 `recipe_id`

#### Scenario: 首句命中推荐触发词
- **WHEN** 用户输入命中某个 Recipe 的推荐触发词
- **THEN** 系统在发送前提供可见的 Recipe 推荐
- **AND** 用户可以接受推荐或继续以普通会话执行
