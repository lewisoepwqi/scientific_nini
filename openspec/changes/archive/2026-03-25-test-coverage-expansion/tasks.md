## 1. API 测试基础设施

- [x] 1.1 基于已有 `tests/client_utils.py:LocalASGIClient` 在 `tests/conftest.py` 中添加 `async_client` fixture（复用已有模式 + 数据隔离）
- [x] 1.2 验证 fixture 可正常创建 app 并发送请求（参考 `tests/test_api_auth.py` 的使用方式）

## 2. 会话管理端点测试

- [x] 2.1 创建 `tests/test_api_sessions.py`
- [x] 2.2 测试创建会话（POST /api/sessions → 201）
- [x] 2.3 测试列出会话（GET /api/sessions → 200 + list）
- [x] 2.4 测试获取不存在的会话（GET /api/sessions/{invalid} → 404）
- [x] 2.5 测试删除会话（DELETE /api/sessions/{id} → 200 + 不再可访问）

## 3. 文件上传/下载端点测试

- [x] 3.1 创建 `tests/test_api_upload.py`
- [x] 3.2 测试上传 CSV 文件成功（→ 200 + 文件元数据）
- [x] 3.3 测试下载不存在的工作空间文件（→ 404）
- [x] 3.4 测试上传超大文件被拒绝（→ 413 或错误响应）

## 4. 工具执行端点测试

- [x] 4.1 创建 `tests/test_api_tools.py`
- [x] 4.2 测试获取工具列表（GET /api/tools → 200 + tool list）
- [x] 4.3 测试工具执行错误响应格式符合预期

## 5. 前端 ErrorBoundary

- [x] 5.1 创建 `web/src/components/ErrorBoundary.tsx`（class component + 降级 UI）
- [x] 5.2 在 `web/src/App.tsx` 顶层包裹 ErrorBoundary
- [x] 5.3 添加 ErrorBoundary 单元测试（验证捕获渲染异常、展示降级 UI）

## 6. 验证

- [x] 6.1 运行 `pytest tests/test_api_*.py -q` 确认新测试通过
- [x] 6.2 运行 `pytest -q` 确认全量测试通过
- [x] 6.3 运行 `cd web && npm run build` 确认前端构建通过
