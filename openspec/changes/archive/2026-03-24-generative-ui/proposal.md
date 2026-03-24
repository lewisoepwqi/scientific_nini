## Why

nini 当前的可视化能力固定在 Plotly/Matplotlib 图表上，所有展示形式都由后端工具预定义。科研分析中有大量"特定结果的专属展示需求"（统计结果摘要卡、交互式参数调整、多变量对比面板），这些需求无法用预定义图表类型覆盖。OpenGenerativeUI 验证了一种可行范式：Agent 直接生成自包含 HTML 组件，在前端 iframe 沙箱中渲染，无需预定义组件类型。

## What Changes

**后端：**
- 新增 `src/nini/tools/generate_widget.py`：`GenerateWidgetTool`，接收 `title`、`html`（自包含 HTML 片段）、可选 `description`，将 HTML 透传至前端
- 在 `tools/registry.py` 中注册该工具

**前端：**
- 新增 `web/src/components/WidgetRenderer.tsx`：接收 HTML 字符串，注入科研主题 CSS + Bridge JS，命令式写入 iframe srcdoc（防止 React 重渲染重置 iframe 状态）
- 新增科研主题 CSS 常量（统计显著性颜色、效应方向颜色、数据类型颜色）
- 新增 Bridge JS：支持 iframe 内触发新提问（`window.sendPrompt`）和高度自适应（ResizeObserver + postMessage）
- 在消息渲染流中识别 `generate_widget` 工具结果事件，渲染 `WidgetRenderer` 组件

## Capabilities

### New Capabilities

- `generative-ui`：Agent 生成可交互 HTML 组件并在聊天界面内嵌渲染的能力

### Modified Capabilities

（无现有规格变更）

## Impact

- **新增文件**：`src/nini/tools/generate_widget.py`、`web/src/components/WidgetRenderer.tsx`
- **修改文件**：`src/nini/tools/registry.py`（注册工具）、前端消息渲染组件（识别新工具结果类型）
- **安全边界**：iframe 使用 `sandbox="allow-scripts"`（不加 `allow-same-origin`，防止 iframe 访问宿主 DOM/localStorage）+ CSP 白名单（只允许主流 CDN）
- **无新后端依赖**：`GenerateWidgetTool` 只做透传，不处理 HTML 内容
