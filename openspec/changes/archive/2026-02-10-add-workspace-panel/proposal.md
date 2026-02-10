# Change: 新增独立工作区面板

## Why

当前 Nini 的工作区仅是对话输入框上方的一个 96px 高的紧凑卡片（WorkspacePanel），用户难以发现和管理会话文件与产物。参考 Kimi/MiniMax Agent 的工作区设计，需要升级为独立的右侧面板，提供完整的文件管理、代码执行历史查看和产物画廊功能。

## What Changes

### 后端变更
- **WorkspaceManager 扩展**：新增文件删除、重命名、预览、搜索、自定义文件夹、版本控制能力
- **WorkspaceManager 扩展**：新增代码执行历史持久化（`workspace/executions/` 目录）
- **WorkspaceManager 扩展**：新增批量下载（ZIP 打包）能力
- **API 端点新增**：DELETE/PATCH/GET preview 等文件操作端点
- **API 端点新增**：`POST /api/sessions/{sid}/workspace/batch-download` 批量下载端点
- **API 端点新增**：`GET /api/sessions/{sid}/workspace/executions` 执行历史端点
- **WebSocket 事件扩展**：新增 `workspace_update` 事件，产物生成后实时通知面板刷新
- **WebSocket 事件扩展**：新增 `code_execution` 事件，代码执行完成后推送到执行历史面板

### 前端变更 **BREAKING**
- **布局升级**：从两栏（会话列表 + 对话面板）升级为三栏（+ 右侧工作区面板）
- **新增组件**：WorkspaceSidebar（混合模式 Tab 切换：文件管理 + 代码执行历史）
- **新增组件**：FileTreeView（目录树导航，支持 Agent 自定义文件夹）
- **新增组件**：FilePreviewModal（文件预览弹窗，支持图片/文本/HTML/PDF/Markdown 渲染）
- **新增组件**：ArtifactGallery（产物画廊视图，网格缩略图 + 筛选 + 批量下载 ZIP）
- **新增组件**：CodeExecutionPanel（代码执行历史面板，显示 Request/Response）
- **移除旧组件**：ChatPanel 中内嵌的 WorkspacePanel 迁移到独立面板
- **状态管理扩展**：面板开关、搜索、预览、执行历史等状态

### 数据模型变更
- **index.json 扩展**：新增 `folders` 字段（Agent 自定义文件夹）、`version_history` 字段（文件版本记录）
- **产物记录扩展**：新增 `thumbnail_url`、`version`、`folder` 字段
- **新增存储目录**：`workspace/executions/` 用于持久化代码执行历史（JSON 格式）

## Impact

- 受影响代码：
  - `src/nini/workspace/manager.py` — 核心扩展
  - `src/nini/api/routes.py` — 新增 API 端点
  - `src/nini/api/websocket.py` — 新增事件类型
  - `web/src/App.tsx` — 布局重构
  - `web/src/components/ChatPanel.tsx` — 移除内嵌 WorkspacePanel
  - `web/src/components/WorkspacePanel.tsx` — 重构为 WorkspaceSidebar
  - `web/src/store.ts` — 状态管理扩展
  - `tests/` — 新增/更新测试

