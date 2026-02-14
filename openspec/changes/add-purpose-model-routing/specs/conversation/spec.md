## ADDED Requirements

### Requirement: 支持按用途选择模型提供商
系统 SHALL 支持对至少 `chat`、`title_generation`、`image_analysis` 三种用途独立配置首选模型提供商，并在运行时按用途应用。

#### Scenario: 用途首选优先于全局首选
- **WHEN** 用户为 `title_generation` 设置了用途首选提供商，且同时存在全局首选
- **THEN** 标题生成请求优先使用 `title_generation` 的首选提供商
- **AND** 仅在该提供商不可用时才按故障转移顺序降级

#### Scenario: 用途未配置时回退全局首选
- **WHEN** 用户未配置 `chat` 用途首选提供商，但配置了全局首选
- **THEN** 对话请求使用全局首选提供商
- **AND** 若全局首选不可用，继续按默认优先级降级

### Requirement: 用途路由配置可通过 API 查询与保存
系统 SHALL 提供用途路由配置 API，支持读取当前用途配置与保存更新，并在保存后即时生效。

#### Scenario: 查询用途路由
- **WHEN** 客户端请求用途路由查询接口
- **THEN** 返回全局首选提供商、各用途首选提供商
- **AND** 返回每个用途当前生效的模型信息

#### Scenario: 保存用途路由
- **WHEN** 客户端提交用途到提供商的映射更新
- **THEN** 服务端完成合法性校验并持久化到数据库
- **AND** 更新内存路由器并立即生效
