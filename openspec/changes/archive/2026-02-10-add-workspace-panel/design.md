## Context

Nini 当前工作区是嵌入在对话输入区上方的紧凑卡片，功能有限。需要升级为独立的右侧面板，参考 Kimi（计算环境面板）和 MiniMax（文件管理面板）的混合模式设计。

### 约束条件
- 单进程架构，本地优先（SQLite + 文件系统）
- WebSocket 流式通信
- 前端 React + Zustand + Tailwind
- 后端 FastAPI + aiosqlite

## Goals / Non-Goals

### Goals
- 提供独立的右侧工作区面板，支持展开/收起
- 混合模式 Tab 切换：文件管理 + 代码执行历史
- 文件管理：搜索、删除、重命名、预览、目录树导航
- 产物画廊：网格缩略图 + 类型筛选
- 代码执行面板：显示 Agent 的代码执行 Request/Response 历史
- 文件版本控制：同一产物多次生成保留历史
- Agent 自定义文件夹：由 Agent 分析决定文件组织方式
- 移动端响应式适配

### Non-Goals
- 跨会话文件管理（保持每会话独立）
- 在线文件编辑器（仅预览，不做编辑）
- 实时协作编辑
- 文件权限管理

## Decisions

### 1. 三栏布局方案
- **决策**：App.tsx 升级为三栏布局，右侧面板默认 360px 宽，可收起为 0
- **替代方案**：抽屉式覆盖面板 → 拒绝，因为会遮挡对话内容
- **理由**：三栏布局是 Kimi/MiniMax 的标准模式，用户可同时查看对话和文件

### 2. 混合模式 Tab 设计
- **决策**：面板顶部两个 Tab —「文件」和「执行历史」
- 「文件」Tab：目录树 + 文件列表 + 搜索 + 产物画廊切换
- 「执行历史」Tab：按时间倒序显示 Agent 的代码执行记录（Request/Response）
- **理由**：满足用户同时需要文件管理和代码审查的需求

### 3. 文件版本控制
- **决策**：在 index.json 中为每个文件维护 `versions` 数组，记录历史版本路径和时间戳
- **替代方案**：Git 版本控制 → 拒绝，过于复杂
- **理由**：轻量级，与现有 JSON 索引一致

### 4. Agent 自定义文件夹
- **决策**：WorkspaceManager 新增 `create_folder` 和 `move_file` 方法，Agent 通过 skill 调用
- **存储**：index.json 新增 `folders` 字段，记录文件夹结构
- **理由**：让 Agent 根据分析内容自动组织文件，比固定分类更灵活

### 5. 产物缩略图
- **决策**：图表产物（PNG/JPEG/SVG）直接使用原文件作为缩略图（前端 CSS 缩放）
- **替代方案**：后端生成缩略图 → 拒绝，增加复杂度
- **理由**：图表文件通常不大，前端缩放足够

### 6. WebSocket 实时更新
- **决策**：新增 `workspace_update` 事件类型，产物生成/文件变更后推送
- **数据格式**：`{ type: "workspace_update", action: "add|delete|rename", file: {...} }`
- **理由**：避免前端轮询，保持实时性

## Risks / Trade-offs

- **三栏布局在小屏幕上的体验** → 移动端自动收起右侧面板，通过按钮触发抽屉式展开
- **index.json 并发写入** → 单进程架构下无并发问题，但需注意异步操作的原子性
- **文件版本积累导致磁盘占用** → 可设置最大版本数（默认 10），超出自动清理最旧版本
- **Agent 自定义文件夹可能混乱** → 提供默认分类（uploads/artifacts/notes）作为 fallback

## Migration Plan

1. Phase 1-2 不破坏现有功能，WorkspacePanel 保留但标记为 deprecated
2. Phase 3 完成后移除旧 WorkspacePanel，切换到新面板
3. index.json 向后兼容：新字段使用 `setdefault` 初始化

## Open Questions

- 产物画廊需要支持批量下载（ZIP 打包）
- 代码执行历史需要持久化到磁盘
- 文件预览需要支持 PDF 和 markdown渲染

