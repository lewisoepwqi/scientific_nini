## Why

代码审查发现测试覆盖的核心缺口：`routes.py`（2137 行、几十个 HTTP 端点）的行为测试覆盖率为 0%，仅有模块导入检查。HTTP API 路由层是用户请求的直接入口，涉及认证、会话管理、文件上传等关键功能，却没有任何端点行为测试。此外，前端缺乏全局 ErrorBoundary，组件渲染异常会导致整个应用白屏崩溃。

当前测试统计：133 个测试文件 / 700+ 后端测试用例 / 180+ 前端 Vitest 用例——总量健康，但**分布不均**：工具层覆盖充分，API 路由层空白。

## What Changes

- **搭建 HTTP API 测试基础设施**：创建 `conftest.py` 中的 `AsyncClient` fixture 和测试工厂
- **编写会话管理端点测试**：CRUD + 认证边界
- **编写文件上传/下载端点测试**：文件上传、工作空间文件下载、路径安全
- **编写工具执行端点测试**：通过 API 触发工具执行、错误响应格式
- **添加前端全局 ErrorBoundary**：捕获组件渲染异常，展示降级 UI 而非白屏

## Capabilities

### New Capabilities

- `api-test-infrastructure`: HTTP API 测试基础设施和端点行为测试

### Modified Capabilities
（无——本次仅添加测试和前端防护，不修改后端 API 行为）

## Impact

- **新增文件**：`tests/test_api_sessions.py`、`tests/test_api_upload.py`、`tests/test_api_tools.py`、`tests/conftest.py`（或合并到已有 conftest）、`web/src/components/ErrorBoundary.tsx`
- **修改文件**：`web/src/App.tsx`（包裹 ErrorBoundary）
- **API 兼容性**：无变更
- **依赖**：无新依赖（httpx 已在 dev 依赖中）
