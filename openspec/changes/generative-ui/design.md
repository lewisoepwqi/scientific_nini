## Context

OpenGenerativeUI 的 `WidgetRenderer` 组件（`widget-renderer.tsx`）验证了核心技术：LLM 生成自包含 HTML → 注入主题 CSS + Bridge JS → 命令式写入 iframe srcdoc → ResizeObserver 自适应高度 + postMessage 双向通信。

nini 的前端是 React 18 + Vite + TypeScript + Tailwind CSS，与 OpenGenerativeUI 的 Next.js 技术栈兼容，核心组件可直接移植。

nini 已有工具结果渲染逻辑：前端通过 WebSocket 接收 `tool_result` 事件，根据工具名分发到不同渲染组件（如 `ChartViewer`、`DataViewer`）。新增 `WidgetRenderer` 作为 `generate_widget` 工具结果的渲染器，符合现有模式。

## Goals / Non-Goals

**Goals:**
- `GenerateWidgetTool` 作为后端工具，LLM 可调用生成自包含 HTML 组件
- `WidgetRenderer` 在前端 iframe 沙箱中安全渲染 AI 生成的 HTML
- 科研主题 CSS 使 AI 生成的 HTML 自动具备领域视觉规范（显著性颜色、效应方向等）
- Bridge JS 支持 iframe 内触发新对话和高度自适应

**Non-Goals:**
- 不预定义科研组件模板（由 LLM 自由生成 HTML，本期不做组件库）
- 不支持 iframe 内访问宿主页面数据（数据应通过 AI 生成时内嵌到 HTML）
- 不对 AI 生成的 HTML 做语义校验（依赖 CSP + sandbox 做安全隔离）

## Decisions

### 决策 1：命令式写入 iframe srcdoc，而非 React srcDoc prop
React 的 srcDoc prop 在父组件 re-render 时会重置 iframe（Three.js 场景、动画帧等状态丢失）。CopilotKit 流式更新、WebSocket 消息到达都会触发 re-render。命令式写入（`iframeRef.current.srcdoc = ...`）配合 `useRef` 追踪已提交的 HTML，仅在内容真正变化时重载 iframe。

### 决策 2：iframe sandbox 属性只设 `allow-scripts`，不加 `allow-same-origin`
- `allow-scripts`：允许 iframe 内 JS 执行（AI 生成的交互逻辑需要）
- `postMessage` 通信（高度上报和 sendPrompt）不需要 `allow-same-origin`，跨源 postMessage 天然可用
- 不加 `allow-same-origin`：一旦加上，iframe 内 JS 可访问宿主页面的 DOM、localStorage、Cookie，破坏隔离性
- 不加 `allow-forms`、`allow-top-navigation`：防止 iframe 提交表单或跳转宿主页面

### 决策 3：CSP 只允许主流科研可视化 CDN
允许：`cdnjs.cloudflare.com`、`esm.sh`、`cdn.jsdelivr.net`、`unpkg.com`（覆盖 Chart.js、D3、Plotly、Three.js 等主流库）。拒绝其他外联请求。`connect-src 'self'` 防止 iframe 内发起任意 HTTP 请求。

### 决策 4：GenerateWidgetTool 纯透传，不处理 HTML
后端不解析、不修改、不校验 HTML 内容。工具只封装参数并通过工具结果事件将 HTML 字符串传给前端，安全控制完全在前端 CSP + sandbox 层实现。这保持后端工具的简单性，也避免 HTML 解析引入安全风险。

### 决策 5：Bridge JS 的 sendPrompt 使用 postMessage，宿主监听后触发对话
iframe 内调用 `window.sendPrompt(text)` → `postMessage({type: 'send-prompt', text})` → 宿主 `WidgetRenderer` 组件监听并调用现有的消息发送函数。这样 iframe 内的按钮可以触发 Agent 新一轮对话（如"深入分析这个变量"）。

## Risks / Trade-offs

- **[风险] AI 生成恶意 HTML** → 缓解：sandbox + CSP 双重隔离，iframe 无法访问宿主 DOM、localStorage、Cookie；connect-src 限制网络请求
- **[风险] 大量 iframe 内存占用** → 缓解：本期不做懒加载/卸载，先观测实际使用中的数量；Phase 3 按需优化
- **[风险] iframe 高度计算错误导致内容截断** → 缓解：ResizeObserver 监听 body，内容变化时重新上报；设置最小高度兜底

## Migration Plan

- `generate_widget` 工具注册为普通工具，不影响现有工具调用
- 前端新增组件，不修改现有渲染路径，渐进可用
- 回滚：注销工具注册 + 删除 `WidgetRenderer.tsx`

## Open Questions

（无）
