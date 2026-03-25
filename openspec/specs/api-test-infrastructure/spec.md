# api-test-infrastructure Specification

## Purpose
定义可复用的 HTTP API 测试基础设施，并明确会话、上传、工具目录与前端全局错误边界的最小行为契约。
## Requirements
### Requirement: HTTP API 测试 AsyncClient fixture
系统 SHALL 提供基于已有 `tests/client_utils.py:LocalASGIClient` 的 pytest fixture，支持所有端点的异步测试。

注：`LocalASGIClient`（httpx.AsyncClient + ASGITransport）和 `test_api_auth.py` 已提供可复用的 API 测试基础设施。本需求基于此扩展，不需从零搭建。

#### Scenario: fixture 可用于测试
- **WHEN** 测试函数声明 `async_client` fixture
- **THEN** SHALL 获得一个可发送 HTTP 请求的 `AsyncClient` 实例
- **AND** 应用上下文（临时数据目录、配置隔离）SHALL 在每个测试间独立

### Requirement: 会话管理端点测试覆盖
测试 SHALL 覆盖会话生命周期的核心 HTTP 端点。

#### Scenario: 创建新会话
- **WHEN** POST `/api/sessions` 被调用
- **THEN** SHALL 返回 201 状态码和会话 ID

#### Scenario: 列出会话
- **WHEN** GET `/api/sessions` 被调用
- **THEN** SHALL 返回 200 状态码和会话列表

#### Scenario: 获取不存在的会话返回 404
- **WHEN** GET `/api/sessions/{invalid_id}` 被调用
- **THEN** SHALL 返回 404 状态码

#### Scenario: 删除会话
- **WHEN** DELETE `/api/sessions/{session_id}` 被调用
- **THEN** SHALL 返回 200 状态码且会话不再可访问

### Requirement: 文件上传端点测试覆盖
测试 SHALL 覆盖文件上传和工作空间文件访问的核心路径。

#### Scenario: 上传 CSV 文件成功
- **WHEN** POST 上传端点携带合法 CSV 文件
- **THEN** SHALL 返回 200 状态码和文件元数据

#### Scenario: 上传超大文件被拒绝
- **WHEN** 上传文件大小超过 `max_upload_size` 配置
- **THEN** SHALL 返回 413 或合适的错误状态码

#### Scenario: 下载不存在的工作空间文件返回 404
- **WHEN** GET 请求工作空间中不存在的文件路径
- **THEN** SHALL 返回 404 状态码

### Requirement: 工具列表端点测试覆盖
测试 SHALL 验证工具列表 API 端点的基本可用性。

#### Scenario: 获取工具列表
- **WHEN** GET `/api/tools` 被调用
- **THEN** SHALL 返回 200 状态码和包含工具定义的列表

### Requirement: 前端全局 ErrorBoundary
前端 SHALL 在应用顶层包裹 React ErrorBoundary 组件，捕获组件树中的渲染异常并展示降级 UI。

#### Scenario: 组件渲染错误不导致白屏
- **WHEN** 某子组件在渲染过程中抛出 JavaScript 异常
- **THEN** ErrorBoundary SHALL 捕获该异常
- **AND** SHALL 展示降级 UI（包含错误信息和重试按钮）
- **AND** 应用的其他部分（如侧边栏）SHALL 不受影响

#### Scenario: 错误恢复
- **WHEN** 用户在降级 UI 中点击重试
- **THEN** ErrorBoundary SHALL 尝试重新渲染子组件树
