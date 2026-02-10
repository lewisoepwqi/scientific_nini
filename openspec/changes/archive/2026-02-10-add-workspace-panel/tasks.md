# 工作区面板实施任务清单

## Phase 1：基础面板与三栏布局（P0）

### 1.1 后端基础扩展
- [x] 1.1.1 WorkspaceManager 新增 `delete_file(file_id)` 方法
- [x] 1.1.2 WorkspaceManager 新增 `rename_file(file_id, new_name)` 方法
- [x] 1.1.3 WorkspaceManager 新增 `get_file_preview(file_id)` 方法（图片 base64 / 文本前 50 行）
- [x] 1.1.4 WorkspaceManager 新增 `search_files(query)` 方法（文件名模糊搜索）
- [x] 1.1.5 API 新增 `DELETE /api/sessions/{sid}/workspace/files/{fid}` 端点
- [x] 1.1.6 API 新增 `PATCH /api/sessions/{sid}/workspace/files/{fid}` 端点（重命名）
- [x] 1.1.7 API 新增 `GET /api/sessions/{sid}/workspace/files/{fid}/preview` 端点
- [x] 1.1.8 API 修改 `GET /api/sessions/{sid}/workspace/files` 增加 `?q=` 搜索参数
- [x] 1.1.9 编写后端单元测试

### 1.2 前端三栏布局
- [x] 1.2.1 App.tsx 重构为三栏布局（左侧会话列表 + 中间对话 + 右侧工作区面板）
- [x] 1.2.2 store.ts 新增面板状态：`workspacePanelOpen`、`workspacePanelTab`、`fileSearchQuery`
- [x] 1.2.3 新建 WorkspaceSidebar.tsx 组件（面板容器，含 Tab 切换头部）
- [x] 1.2.4 新建 FileListItem.tsx 组件（文件列表项：图标 + 名称 + 大小 + 操作按钮）
- [x] 1.2.5 实现文件类型图标映射（CSV/Excel/PNG/PDF/MD/JSON 等）
- [x] 1.2.6 实现文件搜索输入框与过滤逻辑
- [x] 1.2.7 实现文件删除确认对话框与 API 调用
- [x] 1.2.8 实现文件重命名内联编辑与 API 调用
- [x] 1.2.9 顶栏新增工作区面板开关按钮
- [x] 1.2.10 移动端响应式：小屏幕下右侧面板改为抽屉式覆盖
- [x] 1.2.11 ChatPanel.tsx 移除内嵌的 WorkspacePanel 引用

## Phase 2：文件预览与目录树（P1）

### 2.1 文件预览
- [x] 2.1.1 新建 FilePreviewModal.tsx 组件（弹窗式预览）
- [x] 2.1.2 实现图片预览（PNG/JPEG/SVG 直接渲染）
- [x] 2.1.3 实现文本预览（TXT/CSV 前 50 行 + 语法高亮）
- [x] 2.1.4 实现 JSON 预览（格式化 + 折叠）
- [x] 2.1.5 实现 HTML 预览（iframe 沙箱渲染，用于 Plotly 图表）
- [x] 2.1.6 实现 PDF 预览（使用 react-pdf 或 iframe 渲染 PDF 文件）
- [x] 2.1.7 实现 Markdown 预览（使用 react-markdown 渲染，支持 GFM 语法和代码高亮）
- [x] 2.1.8 store.ts 新增 `previewFile` 状态和 `openPreview`/`closePreview` 方法

### 2.2 目录树导航
- [x] 2.2.1 新建 FileTreeView.tsx 组件（树状目录结构）
- [x] 2.2.2 实现默认三分类目录（📁 数据集 / 📁 产物 / 📁 笔记）
- [x] 2.2.3 实现文件夹展开/收起动画
- [x] 2.2.4 实现文件夹内文件计数显示
- [x] 2.2.5 视图切换：列表视图 ↔ 树状视图

### 2.3 WebSocket 实时更新
- [x] 2.3.1 后端 websocket.py 新增 `workspace_update` 事件发送逻辑
- [x] 2.3.2 前端 store.ts 处理 `workspace_update` 事件，自动刷新文件列表
- [x] 2.3.3 产物生成后自动推送到文件面板（无需手动刷新）

## Phase 3：代码执行面板（P1）

### 3.1 执行历史收集与持久化
- [x] 3.1.1 后端：Agent 执行 `run_code` skill 时记录 Request/Response 到会话
- [x] 3.1.2 WebSocket 新增 `code_execution` 事件类型（包含代码和输出）
- [x] 3.1.3 store.ts 新增 `codeExecutions` 状态数组
- [x] 3.1.4 WorkspaceManager 新增 `save_code_execution(code, output, status)` 方法，将执行记录持久化到 `workspace/executions/` 目录
- [x] 3.1.5 WorkspaceManager 新增 `list_code_executions()` 方法，从磁盘加载执行历史
- [x] 3.1.6 API 新增 `GET /api/sessions/{sid}/workspace/executions` 端点，返回持久化的执行历史
- [x] 3.1.7 会话恢复时自动加载历史执行记录到前端

### 3.2 执行历史面板
- [x] 3.2.1 新建 CodeExecutionPanel.tsx 组件
- [x] 3.2.2 实现 Request 区域（代码块 + 语法高亮）
- [x] 3.2.3 实现 Response 区域（输出文本 + 错误高亮）
- [x] 3.2.4 实现执行记录时间线（按时间倒序）
- [x] 3.2.5 实现代码复制按钮
- [x] 3.2.6 Tab 切换集成到 WorkspaceSidebar

## Phase 4：产物画廊与版本控制（P2）

### 4.1 产物画廊
- [x] 4.1.1 新建 ArtifactGallery.tsx 组件（网格缩略图视图）
- [x] 4.1.2 实现图表缩略图渲染（CSS 缩放原图）
- [x] 4.1.3 实现类型筛选（全部 / 图表 / 报告 / 数据快照）
- [x] 4.1.4 实现点击缩略图打开预览
- [x] 4.1.5 视图切换：文件列表 ↔ 画廊视图
- [x] 4.1.6 实现批量选择功能（复选框多选产物）
- [x] 4.1.7 后端 WorkspaceManager 新增 `batch_download(file_ids)` 方法，将选中文件打包为 ZIP
- [x] 4.1.8 API 新增 `POST /api/sessions/{sid}/workspace/batch-download` 端点，接收文件 ID 列表，返回 ZIP 文件流
- [x] 4.1.9 前端实现"批量下载"按钮，调用批量下载 API 并触发浏览器下载

### 4.2 文件版本控制
- [x] 4.2.1 WorkspaceManager 新增 `add_version(file_id, new_path)` 方法
- [x] 4.2.2 index.json 扩展：每个文件记录增加 `versions` 数组
- [x] 4.2.3 产物重新生成时自动创建新版本（保留旧版本）
- [x] 4.2.4 前端文件详情显示版本历史列表
- [x] 4.2.5 支持查看/下载历史版本
- [x] 4.2.6 版本数量上限（默认 10），超出自动清理

## Phase 5：Agent 自定义文件夹与高级功能（P2）

### 5.1 Agent 自定义文件夹
- [x] 5.1.1 WorkspaceManager 新增 `create_folder(name, parent?)` 方法
- [x] 5.1.2 WorkspaceManager 新增 `move_file(file_id, folder_id)` 方法
- [x] 5.1.3 index.json 扩展：新增 `folders` 字段
- [x] 5.1.4 新增 `organize_workspace` skill，Agent 可调用来组织文件
- [x] 5.1.5 前端 FileTreeView 支持显示自定义文件夹
- [x] 5.1.6 前端支持拖拽文件到文件夹

### 5.2 文件创建与编辑
- [x] 5.2.1 API 新增 `POST /api/sessions/{sid}/workspace/files` 创建文件端点
- [x] 5.2.2 前端"新建文件"按钮与创建对话框
- [x] 5.2.3 简单的文本编辑器（Markdown/纯文本）

### 5.3 拖拽上传增强
- [x] 5.3.1 右侧面板支持拖拽上传文件
- [x] 5.3.2 上传进度条显示
- [x] 5.3.3 批量上传支持

## Phase 6：测试与验收

### 6.1 后端测试
- [x] 6.1.1 WorkspaceManager 新方法单元测试（delete/rename/preview/search/folder/version）
- [x] 6.1.2 新 API 端点集成测试
- [x] 6.1.3 WebSocket 事件测试

### 6.2 前端测试
- [x] 6.2.1 前端构建验证 `npm run build`
- [x] 6.2.2 三栏布局响应式验证
- [x] 6.2.3 文件操作端到端验证

### 6.3 回归测试
- [x] 6.3.1 `pytest -q` 全量通过（104 tests passed）
- [x] 6.3.2 现有上传/下载/产物流程不受影响
- [x] 6.3.3 WebSocket 连接稳定性验证
