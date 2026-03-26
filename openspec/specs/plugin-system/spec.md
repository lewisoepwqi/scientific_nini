# Plugin System Spec

## Purpose

定义插件系统的核心抽象层，包括插件基类接口、注册中心、生命周期管理和降级通知机制，为可扩展的插件化架构提供基础支撑。

## Requirements

### Requirement: Plugin 基类接口
系统 SHALL 定义 `Plugin` 抽象基类，包含 name、version、description 属性和 is_available()、initialize()、shutdown()、get_degradation_info() 方法。

#### Scenario: 子类必须实现抽象方法
- **WHEN** 创建未实现 is_available() 和 initialize() 的 Plugin 子类
- **THEN** 实例化时抛出 TypeError

#### Scenario: shutdown 有默认实现
- **WHEN** Plugin 子类未覆写 shutdown()
- **THEN** 调用 shutdown() 不报错（默认空操作）

### Requirement: DegradationInfo 模型
系统 SHALL 定义 `DegradationInfo` Pydantic 模型，包含 plugin_name、reason、impact、alternatives 字段。

#### Scenario: 模型可实例化
- **WHEN** 创建 `DegradationInfo(plugin_name="network", reason="无网络连接", impact="无法在线检索文献")`
- **THEN** 实例创建成功，alternatives 默认为空列表

### Requirement: PluginRegistry 注册与查询
系统 SHALL 提供 `PluginRegistry`，支持 register()、get()、list_available()、list_unavailable() 方法。

#### Scenario: 注册插件
- **WHEN** 调用 `registry.register(plugin)`
- **THEN** 插件可通过 `registry.get(plugin.name)` 查询到

#### Scenario: 查询可用插件
- **WHEN** 已注册 2 个插件，其中 1 个 is_available() 返回 True
- **THEN** `list_available()` 返回 1 个插件

#### Scenario: 查询不可用插件及降级信息
- **WHEN** 已注册插件 is_available() 返回 False
- **THEN** `list_unavailable()` 返回该插件及其 DegradationInfo

### Requirement: 插件生命周期管理
PluginRegistry SHALL 提供 initialize_all() 和 shutdown_all() 方法管理所有插件的生命周期。

#### Scenario: 单个插件初始化失败不阻断其他插件
- **WHEN** 插件 A 的 initialize() 抛出异常
- **THEN** 插件 B 仍被正常初始化，应用启动不中断

#### Scenario: 初始化超时视为不可用
- **WHEN** 插件的 initialize() 超过 5 秒未完成
- **THEN** 该插件被标记为不可用，记录警告日志

### Requirement: 降级通知机制
当 Plugin 不可用时，系统 SHALL 提供结构化的降级信息，供 Agent 提示词和事件系统消费。

#### Scenario: Agent 可查询降级信息
- **WHEN** Agent 运行时需要使用某插件的功能
- **THEN** 可通过 PluginRegistry 查询该插件是否可用及降级信息

#### Scenario: 降级信息包含替代建议
- **WHEN** NetworkPlugin 不可用
- **THEN** DegradationInfo 的 alternatives 包含「手动上传文献 PDF」等替代建议
