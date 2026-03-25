## Context

当前后端测试集中在 Agent 循环、工具执行、会话持久化等内核，对 HTTP API 路由层（`routes.py` 2137 行）几乎无覆盖。前端缺乏全局异常兜底。

## Goals / Non-Goals

**Goals:**
- 建立可复用的 API 测试基础设施
- 覆盖会话 CRUD、文件上传/下载、工具执行的核心正常/异常路径
- 添加前端 ErrorBoundary 防止白屏

**Non-Goals:**
- 不追求 100% 行覆盖率（目标 >60% 的 `nini.api` 模块覆盖率）
- 不添加前端 E2E 测试（Playwright E2E 已存在基础框架）
- 不添加性能/负载测试
- 不测试 WebSocket 交互（已有 `test_phase4_websocket_run_code.py` 等覆盖）

## Decisions

### D1: 复用已有测试基础设施

项目中已有 `tests/client_utils.py` 提供 `LocalASGIClient`（httpx.AsyncClient + ASGITransport），且 `tests/test_api_auth.py` 已展示完整的 API 测试范例。本次基于此扩展，不需从零搭建。

fixture 使用 `tmp_path` + `monkeypatch` 确保测试间数据隔离，参考 `test_api_auth.py` 的模式。

### D2: 测试组织

- `tests/test_api_sessions.py` — 会话 CRUD（4-6 个测试）
- `tests/test_api_upload.py` — 文件上传/下载（3-4 个测试）
- `tests/test_api_tools.py` — 工具列表/执行（2-3 个测试）

每个文件包含正常路径 + 至少 1 个异常路径（404/400/413）。

### D3: ErrorBoundary 实现

创建 `web/src/components/ErrorBoundary.tsx`：
- 使用 React class component（ErrorBoundary 必须是 class component）
- `componentDidCatch` 记录错误到 console
- 降级 UI 显示错误信息 + "重新加载" 按钮
- 在 `App.tsx` 的最外层包裹

### D4: 认证测试策略

当前认证基于可选 API Key。测试策略：
- 无认证配置时：所有端点应可访问
- 有认证配置时（`NINI_API_KEY` 设置）：未携带 key 的请求应返回 401
- 不在本次深入测试认证边界——已有 `test_auth.py` 前端测试覆盖

## Risks / Trade-offs

- **[测试与生产代码耦合]** → API 测试直接依赖路由实现细节（URL 路径、响应格式）。Mitigation：仅测试公开 API 契约，不测试内部实现。
- **[fixture 启动耗时]** → `create_app()` 包含初始化逻辑。Mitigation：使用 `scope="module"` 共享 app 实例。
