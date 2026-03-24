## 1. 后端工具

- [x] 1.1 新建 `src/nini/tools/generate_widget.py`，实现 `GenerateWidgetTool`：参数 `title`（必填）、`html`（必填）、`description`（可选），`execute()` 直接返回成功结果并透传三个字段
- [x] 1.2 在 `src/nini/tools/registry.py` 的 `create_default_tool_registry()` 中注册 `GenerateWidgetTool`

## 2. 前端主题与 Bridge

- [x] 2.1 新建 `web/src/components/widget-renderer/theme.ts`：定义科研主题 CSS 字符串常量，包含 `--color-significant`、`--color-marginal`、`--color-not-significant`、`--color-positive-effect`、`--color-negative-effect` 变量，及深色模式 `@media` 覆盖
- [x] 2.2 新建 `web/src/components/widget-renderer/bridge.ts`：定义 Bridge JS 字符串常量，包含 `window.sendPrompt` 函数和 ResizeObserver 高度上报逻辑
- [x] 2.3 新建 `web/src/components/widget-renderer/assemble.ts`：`assembleDocument(html, themeCSS, bridgeJS) -> string`，将三者组合为完整 HTML 文档并注入 CSP meta 标签

## 3. WidgetRenderer 组件

- [x] 3.1 新建 `web/src/components/WidgetRenderer.tsx`：接收 `title`、`html`、`description` props
- [x] 3.2 实现命令式 iframe 写入：`useRef` 追踪已提交 HTML，`useEffect` 仅在内容变化时调用 `iframeRef.current.srcdoc = assembleDocument(html)`
- [x] 3.3 实现 iframe 高度自适应：监听 `message` 事件中 `type: 'iframe-height'`，动态设置 iframe 元素 height 样式
- [x] 3.4 实现 sendPrompt 转发：监听 `message` 事件中 `type: 'send-prompt'`，调用现有消息发送函数
- [x] 3.5 设置 iframe 属性：`sandbox="allow-scripts"`，初始 height 设默认值（如 200px）

## 4. 消息渲染集成

- [x] 4.1 在前端工具结果渲染逻辑中，识别工具名为 `generate_widget` 的结果事件
- [x] 4.2 从工具结果 data 中提取 `title`、`html`、`description`，渲染 `<WidgetRenderer>` 组件

## 5. 测试与验收

- [x] 5.1 后端：为 `GenerateWidgetTool` 写单元测试，验证 `execute()` 透传 html/title/description，缺少必填参数返回 success=False
- [x] 5.2 前端：手动验证 Agent 调用 `generate_widget` 后聊天界面出现内嵌 HTML 组件
- [x] 5.3 前端：手动验证 iframe 内使用 `var(--color-significant)` 颜色变量渲染正常
- [x] 5.4 前端：手动验证 iframe 内调用 `window.sendPrompt("test")` 后对话界面产生新消息
- [x] 5.5 前端：验证父组件 re-render 时（如 WebSocket 新消息到达），已渲染的 WidgetRenderer iframe 不重载
- [x] 5.6 运行 `pytest -q` 确认全量测试无回归
- [x] 5.7 运行 `cd web && npm run build` 确认前端 TypeScript 无编译错误
