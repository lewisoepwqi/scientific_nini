# generative-ui Specification

## Purpose
TBD - created by archiving change generative-ui. Update Purpose after archive.

## Requirements
### Requirement: GenerateWidgetTool 工具定义
系统 SHALL 提供 `generate_widget` 工具，参数包含必填的 `title`（字符串）和 `html`（自包含 HTML 字符串），以及可选的 `description`（字符串）。工具执行 SHALL 直接返回成功结果，result data 中包含 `title`、`html`、`description` 三个字段原样透传，不对 HTML 内容做任何处理。

#### Scenario: 工具调用返回 HTML 数据
- **WHEN** LLM 调用 `generate_widget`，传入 title 和合法的 HTML 字符串
- **THEN** 工具返回 `success=True`，result data 包含 `{"title": ..., "html": ..., "description": ...}`

#### Scenario: 缺少必填参数时返回错误
- **WHEN** LLM 调用 `generate_widget` 时未提供 `html` 参数
- **THEN** 工具返回 `success=False`，message 说明缺少必填参数

### Requirement: WidgetRenderer 在 iframe 中渲染 HTML
前端 `WidgetRenderer` 组件 SHALL 接收 `html` 字符串，将其与科研主题 CSS 和 Bridge JS 组合后，写入 iframe 的 `srcdoc` 属性。iframe SHALL 设置 `sandbox="allow-scripts"` 属性。

#### Scenario: HTML 内容在 iframe 中渲染
- **WHEN** `WidgetRenderer` 接收到非空 `html` 字符串
- **THEN** iframe 的 srcdoc 被设置为注入了主题 CSS 和 Bridge JS 的完整 HTML 文档
- **THEN** iframe 以 `sandbox="allow-scripts"` 属性渲染

### Requirement: 命令式写入防止 React 重渲染重置 iframe
`WidgetRenderer` SHALL 使用 `useRef` 追踪最近一次写入 iframe 的 HTML 内容。当 `html` prop 未变化时（引用相等或内容相等），SHALL 跳过 iframe 重载，保留 iframe 内部 JS 状态。

#### Scenario: 相同 HTML 内容不触发 iframe 重载
- **WHEN** 父组件 re-render 但 `html` prop 内容未变化
- **THEN** `WidgetRenderer` 不重载 iframe
- **THEN** iframe 内部 JS 状态（动画、Three.js 场景等）得以保留

#### Scenario: HTML 内容变化时更新 iframe
- **WHEN** `html` prop 内容发生变化
- **THEN** iframe 的 srcdoc 被更新为新内容

### Requirement: CSP 限制 iframe 网络请求
注入到 iframe 的 HTML 文档 SHALL 包含 Content-Security-Policy meta 标签，限制脚本来源为主流 CDN 白名单（`cdnjs.cloudflare.com`、`esm.sh`、`cdn.jsdelivr.net`、`unpkg.com`），禁止 connect-src 访问非 self 域名。

#### Scenario: 非白名单 CDN 脚本被阻止
- **WHEN** iframe 内 HTML 尝试加载非白名单域名的脚本
- **THEN** 浏览器 CSP 阻止该请求

### Requirement: Bridge JS 支持高度自适应
注入的 Bridge JS SHALL 使用 ResizeObserver 监听 iframe 内 `body` 或指定容器的尺寸变化，通过 `window.parent.postMessage({type: 'iframe-height', height: N}, '*')` 上报高度。`WidgetRenderer` 宿主组件 SHALL 监听该消息并动态调整 iframe 元素高度。

#### Scenario: iframe 内容高度变化时自动调整
- **WHEN** iframe 内容渲染完成或内容高度变化
- **THEN** `WidgetRenderer` 调整 iframe 元素高度以完整展示内容，不出现滚动条

### Requirement: Bridge JS 支持从 iframe 内触发新对话
注入的 Bridge JS SHALL 在 iframe 全局作用域提供 `window.sendPrompt(text: string)` 函数，调用时向宿主发送 `{type: 'send-prompt', text}` postMessage。`WidgetRenderer` 宿主 SHALL 监听该消息，并通过现有消息发送接口触发新的 Agent 对话轮次。

#### Scenario: iframe 内按钮触发新对话
- **WHEN** iframe 内 JS 调用 `window.sendPrompt("分析这个变量")`
- **THEN** 宿主对话界面产生新的用户消息"分析这个变量"，触发 Agent 响应

### Requirement: 科研主题 CSS 注入
注入的主题 CSS SHALL 包含以下科研专属 CSS 变量：
- `--color-significant`：统计显著（p < 0.05）颜色
- `--color-marginal`：边缘显著（0.05 ≤ p < 0.10）颜色
- `--color-not-significant`：不显著颜色
- `--color-positive-effect`：正效应颜色
- `--color-negative-effect`：负效应颜色
主题 CSS SHALL 支持 `@media (prefers-color-scheme: dark)` 深色模式适配。

#### Scenario: 使用主题颜色变量的 HTML 自动适配深色模式
- **WHEN** iframe 内 HTML 使用 `var(--color-significant)` 等主题变量
- **THEN** 系统深色模式下变量值自动切换为深色模式对应颜色
