## ADDED Requirements

### Requirement: NetworkPlugin 实现
系统 SHALL 提供 `NetworkPlugin`，继承 Plugin 基类，封装网络请求能力的可用性检测。

#### Scenario: 网络可用时返回 True
- **WHEN** 网络连通且必要配置就绪
- **THEN** `is_available()` 返回 True

#### Scenario: 网络不可用时返回 False
- **WHEN** 无网络连接
- **THEN** `is_available()` 返回 False

#### Scenario: 初始化成功
- **WHEN** 调用 `initialize()`
- **THEN** HTTP 客户端初始化完成

### Requirement: NetworkPlugin 降级信息
NetworkPlugin 不可用时 SHALL 返回包含明确原因和替代建议的 DegradationInfo。

#### Scenario: 离线降级信息
- **WHEN** NetworkPlugin 的 is_available() 返回 False
- **THEN** get_degradation_info() 返回 DegradationInfo，reason 包含「网络不可用」，alternatives 包含离线替代建议

### Requirement: NetworkPlugin 配置
NetworkPlugin SHALL 从 Nini 配置系统（`config.py`）读取必要的配置项，如代理设置和超时参数。

#### Scenario: 配置可通过环境变量设置
- **WHEN** 设置 `NINI_NETWORK_TIMEOUT` 环境变量
- **THEN** NetworkPlugin 使用该值作为请求超时时间
