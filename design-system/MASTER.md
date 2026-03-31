# Design System MASTER — scientific_nini

> **Design System Version:** 1.2.1
> **Date:** 2026-03-28
> **Style Origin:** Linear.app 设计语言（极致密度、冷色中性、精准间距）
> **Status:** 暗色模式优先，亮色模式对等
> **Changelog:**
> - v1.2.1 — 同步 `index.css` 当前 token：亮色强调色收敛为更深的 Nini Teal（`#0A7E72`），`--text-muted` 双模式对比度修正，补充阴影 token
> - v1.2.0 — 补充完整亮色模式 token、双模式 CSS 实现方案、模式切换规范、功能域 token 化、Plotly 双模式配置
> - v1.1.0 — 补充 DetailPanel 交互模式、功能域 token 化、三栏布局行为规范、页面路由结构、focus ring 例外说明
> - v1.0.0 — 初始版本，暗色模式 token、基础组件规格

---

## 1. Overview

### 产品定位

Nini 是本地优先的科研全流程 AI 研究伙伴。UI 必须传达**专业可信**与**克制精致**，而非花哨的消费级体验。

### 设计原则

1. **极致密度** — 信息以最高效率排列，没有一像素浪费。参考 Linear 的列表密度与面板紧凑度。
2. **冷色中性** — 界面色调冷静、中性，让数据和分析结果成为视觉焦点。强调色仅在关键操作点出现。
3. **精准间距** — 所有间距遵循 4px 基准网格，组件尺寸精确到像素，无模糊的"大约"值。
4. **克制动效** — 0.1s ease 的 hover 过渡，无弹跳、无缩放、无多余动画。
5. **Dual-mode parity** — 暗色模式是首要设计目标，亮色模式需同等质量。亮色模式不是「反色」，而是独立调校的色彩系统。
6. **Consistent color semantics** — 每个功能域固定色彩标识（见功能域 token），用户形成操作直觉。
7. **Professional warmth** — 专业但不冰冷，交互文案有温度，视觉呈现克制可信。
8. **不中断主流程** — 查看详情类操作使用 DetailPanel（推入式），不打断用户当前任务上下文。

### 设计参考

- **Linear.app** — 暗色模式、面板系统、交互细节
- **Notion** — 信息架构、排版层次
- **反参考** — 避免 Vercel 式渐变、Stripe 式插画、消费级产品的视觉噪音

---

## 2. Color Tokens (v1.2.1)

> ⚠️ 所有颜色必须通过 CSS token 引用，**严禁硬编码 hex 值或 Tailwind 原始色彩类名**

### 双模式实现方案

项目使用 Tailwind `darkMode: 'class'`，通过在 `<html>` 元素上切换 `.dark` class 实现模式切换。所有颜色 token 在 `index.css` 中声明，`:root` 为亮色默认值，`.dark` 覆盖为暗色值。

```css
/* index.css — 完整双模式 token 声明 */

:root {
  /* === 亮色模式（Light Mode）=== */

  /* 背景层级 */
  --bg-app:      #EDF2FA;
  --bg-base:     #FFFFFF;
  --bg-elevated: #F5F9FF;
  --bg-overlay:  #E0E8F4;
  --bg-hover:    rgba(10, 126, 114, 0.08);

  /* 卡片层级 */
  --card:        #F5F9FF;

  /* 边框 */
  --border-subtle:  #C8D8EE;
  --border-default: #A8C0DE;
  --border-strong:  #8AAAC8;

  /* 文字 */
  --text-primary:   #0B1830;
  --text-secondary: #3D5878;
  --text-muted:     #5F7692;
  --text-disabled:  #A8B8CC;

  /* 强调色 */
  --accent:        #0A7E72;
  --accent-hover:  #086E63;
  --accent-subtle: rgba(10, 126, 114, 0.08);

  /* 功能色（亮色模式加深以保证对比度） */
  --success: #2D7A52;
  --warning: #A06030;
  --error:   #A03838;

  /* 功能域色标（亮色模式加深） */
  --domain-analysis:  #6D28D9;
  --domain-report:    #047857;
  --domain-cost:      #B45309;
  --domain-profile:   #0369A1;
  --domain-workspace: #1D4ED8;
  --domain-knowledge: #4338CA;

  /* Scrollbar */
  --scrollbar-thumb:       #C8D8EE;
  --scrollbar-thumb-hover: #A8C0DE;

  /* 阴影 */
  --shadow-sm: 0 1px 3px rgba(11, 24, 48, 0.08);
  --shadow-md: 0 6px 18px rgba(11, 24, 48, 0.10);
  --shadow-lg: 0 12px 28px rgba(11, 24, 48, 0.14);
}

.dark {
  /* === 暗色模式（Dark Mode）=== */

  /* 背景层级 */
  --bg-app:      #000000;
  --bg-base:     #000000;
  --bg-elevated: #0A0A0A;
  --bg-overlay:  #121212;
  --bg-hover:    #18181B;

  /* 卡片层级 */
  --card:        #0A0A0A;

  /* 边框 */
  --border-subtle:  #18181B;
  --border-default: #27272A;
  --border-strong:  #3F3F46;

  /* 文字 */
  --text-primary:   #FAFAFA;
  --text-secondary: #A3A3A3;
  --text-muted:     #7A7A84;
  --text-disabled:  #52525B;

  /* 强调色 */
  --accent:        #0DBCAA;
  --accent-hover:  #10D4BA;
  --accent-subtle: rgba(13, 188, 170, 0.10);

  /* 功能色 */
  --success: #4D9A6A;
  --warning: #C4874A;
  --error:   #C45A5A;

  /* 功能域色标 */
  --domain-analysis:  #7C3AED;
  --domain-report:    #059669;
  --domain-cost:      #D97706;
  --domain-profile:   #0284C7;
  --domain-workspace: #2563EB;
  --domain-knowledge: #4F46E5;

  /* Scrollbar */
  --scrollbar-thumb:       #27272A;
  --scrollbar-thumb-hover: #3F3F46;

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.32);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.40);
  --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.48);
}

/* 双模式 Scrollbar 规范 */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}
```

---

### Token 双模式对照表

#### 背景层级

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--bg-app` | `#EDF2FA` | `#000000` | 应用最底层背景 |
| `--bg-base` | `#FFFFFF` | `#000000` | 面板/卡片默认背景 |
| `--bg-elevated` | `#F5F9FF` | `#0A0A0A` | 浮层/弹出内容背景 |
| `--bg-overlay` | `#E0E8F4` | `#121212` | 遮罩层背景 |
| `--bg-hover` | `rgba(10,126,114,0.08)` | `#18181B` | hover 状态背景 |

#### 边框

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--border-subtle` | `#C8D8EE` | `#18181B` | 面板内分割线、微弱分隔 |
| `--border-default` | `#A8C0DE` | `#27272A` | 组件默认边框 |
| `--border-strong` | `#8AAAC8` | `#3F3F46` | 强调边框、active 状态 |

#### 文字

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--text-primary` | `#0B1830` | `#FAFAFA` | 正文、标题 |
| `--text-secondary` | `#3D5878` | `#A3A3A3` | 辅助说明、标签 |
| `--text-muted` | `#5F7692` | `#7A7A84` | 占位符、禁用文字 |
| `--text-disabled` | `#A8B8CC` | `#52525B` | 不可交互文字 |

#### 强调色

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--accent` | `#0A7E72` | `#0DBCAA` | 主操作按钮、选中态、链接 |
| `--accent-hover` | `#086E63` | `#10D4BA` | hover 态（亮色加深，暗色提亮） |
| `--accent-subtle` | `rgba(10,126,114,0.08)` | `rgba(13,188,170,0.10)` | 选中背景、tag 背景 |

#### 功能色

| Token | Light | Dark | 语义 |
|-------|-------|------|------|
| `--success` | `#2D7A52` | `#4D9A6A` | 成功、连接正常、分析完成 |
| `--warning` | `#A06030` | `#C4874A` | 警告、注意事项、成本提示 |
| `--error` | `#A03838` | `#C45A5A` | 错误、断开连接、操作失败 |

#### 功能域色标

> ⚠️ 必须使用 `var(--domain-*)` token，禁止硬编码 hex 或使用 Tailwind 原始类名（如 `text-purple-600`）
> 亮色模式下所有域色均加深约 10% 以保证白底可读性

| Token | Light | Dark | 域 | 图标（Lucide） |
|-------|-------|------|----|---------------|
| `--domain-analysis` | `#6D28D9` | `#7C3AED` | 分析能力 | `Sparkles` |
| `--domain-report` | `#047857` | `#059669` | 报告/文章 | `FileText` |
| `--domain-cost` | `#B45309` | `#D97706` | 成本统计 | `Coins` |
| `--domain-profile` | `#0369A1` | `#0284C7` | 研究画像 | `User` |
| `--domain-workspace` | `#1D4ED8` | `#2563EB` | 工作区面板 | `PanelRight` |
| `--domain-knowledge` | `#4338CA` | `#4F46E5` | 知识库 | `Library` |

---

## 3. Typography

### 字体栈

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
--font-mono: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, 'Courier New', monospace;
```

### 字号规范

| Token | Size | Line Height | Weight | 用途 |
|-------|------|-------------|--------|------|
| `--text-xs` | 11px | 16px | 400 | 标签、badge、时间戳 |
| `--text-sm` | 12px | 16px | 400 | 按钮、工具栏文字、辅助说明 |
| `--text-base` | 13px | 20px | 400 | 正文、输入框、列表项 |
| `--text-md` | 14px | 20px | 500 | 小标题、面板标题 |
| `--text-lg` | 16px | 24px | 600 | 区块标题 |
| `--text-xl` | 18px | 28px | 600 | 页面标题 |
| `--text-2xl` | 22px | 28px | 700 | 主标题 |

### 代码块

- 字体：`var(--font-mono)`
- 字号：`12px`
- 背景：`var(--bg-elevated)`
- 文字：`var(--text-primary)`
- 行号：`var(--text-muted)`
- Markdown 渲染：自定义样式（见 `index.css`）

### Markdown 渲染

- 标题层级：`h1` 20px → `h2` 16px → `h3` 14px
- 段落间距：`8px`
- 列表缩进：`16px`
- 代码行内：`var(--bg-elevated)` 背景 + `2px 4px` padding + `4px` 圆角

---

## 4. Spacing

### 基准网格：4px

| Token | Value | 用途 |
|-------|-------|------|
| `--space-1` | 4px | 紧凑内边距、图标间距 |
| `--space-2` | 8px | 元素间最小间距 |
| `--space-3` | 12px | 组件内 padding、列表项间距 |
| `--space-4` | 16px | 标准 padding、卡片内边距 |
| `--space-5` | 20px | 区块间距 |
| `--space-6` | 24px | 大区块 padding |
| `--space-8` | 32px | 区块分隔 |
| `--space-10` | 40px | 页面级间距 |

### 圆角

| Token | Value | 用途 |
|-------|-------|------|
| `--radius-sm` | 4px | 小元素（badge、tag） |
| `--radius-md` | 6px | 按钮、输入框 |
| `--radius-lg` | 8px | 卡片、面板 |
| `--radius-xl` | 12px | 弹窗、大型容器 |

### 阴影（慎用，暗色模式下尽量用边框代替）

| Token | Value | 用途 |
|-------|-------|------|
| `--shadow-sm` | Light `0 1px 3px rgba(11,24,48,0.08)` / Dark `0 1px 2px rgba(0,0,0,0.32)` | 微浮起 |
| `--shadow-md` | Light `0 6px 18px rgba(11,24,48,0.10)` / Dark `0 4px 12px rgba(0,0,0,0.40)` | 弹出面板 |
| `--shadow-lg` | Light `0 12px 28px rgba(11,24,48,0.14)` / Dark `0 8px 24px rgba(0,0,0,0.48)` | Sheet 弹窗 |

### 亮色模式特有处理

| 场景 | 暗色模式 | 亮色模式处理 |
|------|---------|------------|
| 卡片投影 | 无阴影（靠边框区分层级） | 可添加 `box-shadow: 0 1px 3px rgba(0,0,0,0.08)` |
| 代码块背景 | `--bg-elevated` `#1A1A1C` | `--bg-elevated` `#F0F0F2`，需确保代码可读 |
| 遮罩层 | `rgba(0,0,0,0.5)` | `rgba(0,0,0,0.3)`（亮色下遮罩不需要那么深） |

---

## 5. Layout Structure (v1.1.0)

### 三栏结构总览

```
┌─────────────┬──────────────────────────────┬───────────────┐
│  Sidebar    │       Main Workspace         │  DetailPanel  │
│  240px      │       flex-1                 │  320px        │
│  固定宽度    │  ┌────────────────────────┐  │  按需显示      │
│  overflow-y │  │  Toolbar    44px       │  │  推入式（中栏  │
│  : auto     │  ├────────────────────────┤  │  相应收缩）    │
│             │  │  ContentArea           │  │               │
│             │  │  flex-1                │  │               │
│             │  │  overflow-y: auto      │  │               │
│             │  ├────────────────────────┤  │               │
│             │  │  InputArea             │  │               │
│             │  │  sticky bottom         │  │               │
│             │  │  （仅对话页）           │  │               │
│             │  └────────────────────────┘  │               │
└─────────────┴──────────────────────────────┴───────────────┘
```

### 各区域行为规范

#### Sidebar（左栏）
- 宽度：`240px` 固定，不可调整
- 高度：`100vh`，`overflow-y: auto`
- 背景：`var(--bg-base)`
- 右边框：`1px solid var(--border-subtle)`
- 折叠：移动端隐藏（`< 768px`），通过 hamburger 触发

#### Main Workspace（中栏）
- 宽度：`flex: 1`，最小宽度 `480px`
- 高度：`100vh`，内部三层各自独立处理溢出
- **Toolbar**（固定层）
  - 高度：`44px`，`flex-shrink: 0`
  - 背景：`var(--bg-base)`
  - 下边框：`1px solid var(--border-subtle)`
  - 左侧：面包屑或页面标题（`text-md font-medium text-primary`）
  - 右侧：操作按钮组（ghost button，`28×28px`）
  - 禁止放入：搜索框、大型 Tab、状态信息
- **ContentArea**（滚动层）
  - `flex: 1`，`overflow-y: auto`
  - `padding: 0`（内部组件自行管理 padding）
  - 列表页：每行 item `height: 36px`，hover `var(--bg-hover)`
  - 卡片页：`gap: 12px`，卡片 `padding: 16px`
- **InputArea**（仅对话页，吸底层）
  - `position: sticky; bottom: 0`
  - 背景：`var(--bg-base)`
  - 上边框：`1px solid var(--border-subtle)`
  - padding：`12px 16px`
  - 输入框最大高度 `200px`，超出内部滚动

#### DetailPanel（右栏）
- 宽度：`320px`，按需展示
- 展示方式：**推入式**——DetailPanel 出现时中栏宽度相应收缩，不覆盖主内容
- 高度：`100vh`，`overflow-y: auto`
- 背景：`var(--bg-base)`
- 左边框：`1px solid var(--border-subtle)`
- 顶部 header：`44px`（与 Toolbar 对齐），含标题 + close button
- **无背景遮罩**，不阻断主区域交互
- 内部 section 用 `border-top: 1px solid var(--border-subtle)` + 小标题区隔

#### 工作区分隔条
- 中栏与右栏之间可拖拽调整
- 拖拽范围：右栏宽度 `240px–480px`
- 拖拽手柄：`4px` 宽，hover 时显示 `var(--accent)` 色

---

## 6. Page Structure (v1.1.0)

### 路由清单

| 路由 | 页面名 | 布局模式 | DetailPanel 使用 |
|------|--------|----------|-----------------|
| `/` | 首页/欢迎页 | 单栏居中 | 无 |
| `/chat/:id` | 对话工作区 | 三栏完整 | Agent 信息、工具详情 |
| `/chat/new` | 新建对话 | 三栏完整 | 无 |
| `/agents` | Agent 管理列表 | 左栏 + 主栏 | Agent 配置详情 |
| `/tools` | 工具清单 | 左栏 + 主栏 | 工具详情（替换原弹窗） |
| `/profile` | 研究画像 | 左栏 + 主栏 | 无（整页展示） |
| `/knowledge` | 知识库 | 左栏 + 主栏 | 文档详情 |
| `/settings` | 设置 | 左栏 + 主栏 | 无 |

### 各页面关键组件

**`/chat/:id` 对话工作区**
- 左栏：会话列表，搜索框置顶，`+ 新建对话` button
- 中栏 Toolbar：当前 Agent 名称 + 模型标签 + 工具栏按钮组
- 中栏 ContentArea：消息列表，流式输出，Tool call 折叠卡片
- 中栏 InputArea：多行输入框 + 发送按钮 + 附件/模型切换
- 右栏 DetailPanel：按需展示 Agent 信息或 Tool 执行详情

**`/tools` 工具清单**
- 左栏：工具分类导航
- 中栏：工具卡片列表（36px 行高，紧凑列表模式）
- 右栏 DetailPanel：点击工具后展示详情（替换原有弹窗，**不再使用 Modal**）

**`/profile` 研究画像**
- 整页布局，无 DetailPanel
- 分区展示用户研究方向、常用工具、历史分析偏好
- 编辑态：CommandSheet 右侧滑入

---

## 7. Components (v1.1.0)

### 关键尺寸（强制）

| 组件 | 尺寸 | 字号 |
|------|------|------|
| Button | 高 28px | 12px |
| Input | 高 28px | 13px |
| Toolbar | 高 44px | — |
| Sidebar | 宽 240px | — |
| Detail Panel | 宽 320px（默认） | — |

### Button

```
高度：28px（固定）
字号：12px / var(--text-sm)
内边距：0 12px
圆角：var(--radius-md) = 6px
字重：500
transition: background 0.1s ease, color 0.1s ease
```

| 变体 | 背景 | 文字 | 边框 |
|------|------|------|------|
| Primary | `var(--accent)` | `#FFFFFF` | none |
| Primary hover | `var(--accent-hover)` | `#FFFFFF` | none |
| Secondary | transparent | `var(--text-primary)` | `var(--border-default)` |
| Ghost | transparent | `var(--text-secondary)` | none |
| Danger | `var(--error)` | `#FFFFFF` | none |

- Ghost hover：`var(--bg-hover)` 背景 + `var(--text-primary)` 文字
- Icon Button（Ghost 变体）：`28×28px`，`padding: 0`，图标居中

### Input

```
高度：28px（固定）
字号：13px / var(--text-base)
内边距：0 8px
圆角：var(--radius-md) = 6px
边框：1px solid var(--border-default)
背景：var(--bg-base)
文字：var(--text-primary)
placeholder：var(--text-muted)

focus：
  border-color: var(--accent)
  box-shadow: 0 0 0 1px var(--accent)
```

> ✅ **例外说明**：Input focus 的 `box-shadow` 为 focus ring，不属于 Anti-patterns 中「彩色阴影」的限制范围。focus ring 是无障碍必须项，不得删除。

### Toolbar

```
高度：44px（固定）
内边距：0 12px
背景：var(--bg-base)
底边框：1px solid var(--border-subtle)
元素间距：8px
左侧：面包屑或页面标题（text-md font-medium text-primary）
右侧：操作按钮组（ghost button，28×28px）
禁止放入：搜索框、大型 Tab、状态信息
```

### 侧边栏（Sidebar）

```
宽度：240px（固定）
背景：var(--bg-base)
右边框：1px solid var(--border-subtle)
内边距：8px 0
列表项高度：28px
列表项内边距：0 12px
列表项 hover：var(--bg-hover)
列表项 active：var(--accent-subtle) 背景 + 左侧 2px accent 指示条
```

### Detail Panel

```
宽度：320px（默认），可拖拽至 240px–480px
背景：var(--bg-base)
左边框：1px solid var(--border-subtle)
顶部 header：44px（与 Toolbar 对齐），含标题 + close button
展示方式：推入式（中栏相应收缩），无背景遮罩
```

### Toast

```
位置：屏幕右下角，距边缘 16px
最大宽度：360px
圆角：var(--radius-md) = 6px
内边距：12px 16px
字号：13px
背景：var(--bg-elevated)
边框：1px solid var(--border-default)

变体：
  success：左侧 3px var(--success) 色条，自动消失 3s
  warning：左侧 3px var(--warning) 色条，自动消失 5s
  error：左侧 3px var(--error) 色条，需手动关闭
```

### Empty State

```
居中布局
图标：24px，var(--text-muted) 色
标题：14px，var(--text-secondary) 色，字重 500
描述：13px，var(--text-muted) 色
操作按钮（可选）：标准 Button Primary
整体垂直间距：8px
```

### Card

```
背景：var(--bg-base)
边框：1px solid var(--border-subtle)
圆角：var(--radius-lg) = 8px
内边距：16px
hover：边框变 var(--border-default)，无 transform
```

### Badge / Tag

```
高度：20px
内边距：0 6px
字号：11px / var(--text-xs)
圆角：var(--radius-sm) = 4px
背景：var(--accent-subtle)
文字：var(--accent)
```

### Tooltip

```
背景：var(--bg-overlay)
文字：var(--text-primary)
字号：12px
内边距：4px 8px
圆角：var(--radius-sm) = 4px
延迟：300ms
```

---

## 8. Interaction Patterns (v1.1.0)

### 弹窗系统

| 类型 | 宽度 | 位置 | 遮罩 | 适用场景 |
|------|------|------|------|---------|
| **DetailPanel** | 320px（默认） | 右侧固定，推入式 | ❌ 无 | 详情查看、属性面板；不中断主区操作 |
| **CommandSheet** | 40vw（min 480px） | 右侧滑入 | ✅ 半透明 | 表单操作、新建/编辑 |
| **ConfirmDialog** | ≤ 400px | 居中 | ✅ 半透明 | 删除确认、不可逆操作确认 |

### 弹窗使用决策树

```
用户触发操作
    │
    ├─ 只是「查看」信息？
    │       └─ DetailPanel（推入式，无遮罩）
    │
    ├─ 需要「填写表单」或「配置」？
    │       └─ CommandSheet（右侧滑入，有遮罩）
    │
    └─ 需要「二次确认」不可逆操作？
            └─ ConfirmDialog（居中，有遮罩，≤400px）
```

### 弹窗动画规范

| 类型 | 进入动画 | 时长 |
|------|---------|------|
| DetailPanel | `transform: translateX(100%) → 0` | 150ms ease |
| CommandSheet | `transform: translateX(100%) → 0` | 200ms ease |
| ConfirmDialog | `opacity: 0 → 1` + `scale: 0.96 → 1` | 150ms ease |

### 禁止使用的弹窗模式

- **全屏 Modal** — 禁止
- **左侧 Drawer** — 禁止
- **底部 Drawer** — 禁止
- **原生 Alert/Confirm** — 禁止

### 错误处理

- 所有错误通过 **Toast** 通知，不使用 `window.alert()`
- 网络断开使用顶部 Banner 提示，非 Toast

### Loading 状态

- 所有操作必须有 loading 状态
- 按钮加载：文字替换为 spinner + 禁用交互
- 内容加载：骨架屏（Skeleton）而非空白
- 页面加载：顶部 2px accent 色进度条

### Hover / Focus

- hover transition：`0.1s ease`
- focus：`box-shadow: 0 0 0 1px var(--accent)`
- active（鼠标按下）：背景加深一层（如 `var(--bg-base)` → `var(--bg-elevated)`）

### 键盘导航

- `Tab` / `Shift+Tab` 在可交互元素间切换
- `Enter` / `Space` 触发按钮
- `Esc` 关闭 Sheet / Confirm / Dropdown，焦点回到触发元素
- 列表支持方向键导航

### 拖拽

- 工作区分隔条：DetailPanel 宽度 `240px–480px` 可拖拽
- 拖拽时显示 `col-resize` 光标
- 拖拽过程不触发内容 reflow，释放后才更新布局

---

## 9. Theme Switching (v1.2.0)

### 模式切换机制

```tsx
// src/stores/themeStore.ts
type Theme = 'light' | 'dark' | 'system'

// 切换逻辑
function applyTheme(theme: Theme) {
  const isDark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  document.documentElement.classList.toggle('dark', isDark)
  localStorage.setItem('theme', theme)
}

// 初始化（防止 FOUC，必须在 <head> 内联执行）
const saved = localStorage.getItem('theme') ?? 'system'
applyTheme(saved as Theme)
```

### 防止 FOUC

在 `index.html` 的 `<head>` 中**内联**以下脚本，必须在任何 CSS 加载之前执行：

```html
<script>
  (function() {
    var theme = localStorage.getItem('theme') || 'system';
    var isDark = theme === 'dark' ||
      (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (isDark) document.documentElement.classList.add('dark');
  })();
</script>
```

### Tailwind 双模式写法规范

```tsx
// ✅ 正确：使用 CSS token（自动响应模式切换）
<div className="bg-[var(--bg-base)] text-[var(--text-primary)] border border-[var(--border-default)]">

// ✅ 正确：Tailwind dark 修饰符（仅用于无法 token 化的场景）
<div className="bg-white dark:bg-[#141415]">

// ❌ 错误：硬编码颜色（模式切换无效）
<div className="bg-[#141415] text-[#E8E8EA]">

// ❌ 错误：Tailwind 原始色彩类（不走 token，双模式失效）
<div className="bg-gray-950 text-gray-100">
```

### 模式切换 UI 规范

- 切换开关位置：Sidebar 底部或 Settings 页
- 支持三态：`light` / `dark` / `system`（跟随系统，默认值）
- 切换动画：无需过渡动画（Linear 也是瞬切）
- 图标：`Sun`（亮色）/ `Moon`（暗色）/ `Monitor`（系统）

### Plotly 图表双模式配置

Plotly 不感知 CSS token，需要在渲染时动态传入主题配置：

```tsx
// src/utils/plotlyTheme.ts
export function getPlotlyLayout(isDark: boolean) {
  return {
    paper_bgcolor: isDark ? '#141415' : '#FFFFFF',
    plot_bgcolor:  isDark ? '#141415' : '#FFFFFF',
    font: {
      color:  isDark ? '#8A8A8F' : '#6A6A6F',
      size: 12,
    },
    xaxis: {
      gridcolor:    isDark ? '#2A2A2C' : '#E8E8EA',
      linecolor:    isDark ? '#27272A' : '#A8C0DE',
      tickcolor:    isDark ? '#7A7A84' : '#5F7692',
      zerolinecolor: isDark ? '#3F3F46' : '#8AAAC8',
    },
    yaxis: {
      gridcolor:    isDark ? '#2A2A2C' : '#E8E8EA',
      linecolor:    isDark ? '#2A2A2C' : '#DCDCE0',
      tickcolor:    isDark ? '#5A5A5F' : '#9A9AA0',
      zerolinecolor: isDark ? '#3A3A3D' : '#C8C8CE',
    },
  }
}

// 色盲友好的图表数据系列颜色（双模式通用）
export const CHART_COLORS = [
  '#0A7E72', // accent teal
  '#4D9A6A', // success green
  '#C4874A', // warning orange
  '#C45A5A', // error red
  '#7C3AED', // purple
  '#0284C7', // sky blue
]
```

---

## 10. Anti-patterns

### 绝对禁止

- ❌ **全屏 Modal** — 用 DetailPanel 或 CommandSheet 替代
- ❌ **左侧 Drawer** — 用右侧 DetailPanel 或 CommandSheet 替代
- ❌ **原生 Alert / Confirm / Prompt** — 用自定义 Toast 和 ConfirmDialog 替代
- ❌ **Emoji 作为图标** — 使用 Lucide React SVG 图标
- ❌ **弹跳/缩放/旋转动画** — 仅允许 `0.1s ease` 的颜色/背景/边框过渡
- ❌ **渐变背景** — 使用纯色 `var(--bg-*)` token
- ❌ **大于 8px 的圆角用于小组件** — 按钮 6px，卡片 8px，仅弹窗允许 12px
- ❌ **彩色 `box-shadow`** — **例外：Input focus ring** 使用 `box-shadow: 0 0 0 1px var(--accent)` 是合法的无障碍实践
- ❌ **硬编码 hex 颜色值或 Tailwind 原始色彩类** — 必须使用 token
- ❌ **功能域颜色使用 Tailwind 类名**（如 `text-sky-600`）— 必须使用 `var(--domain-*)` token
- ❌ **在亮色模式下使用暗色模式的 hex 值** — 必须通过 token 自动切换
- ❌ **Plotly 图表硬编码颜色** — 必须使用 `getPlotlyLayout(isDark)` 动态配置

### 高度警惕

- ⚠️ **布局偏移型 hover** — hover 不应改变元素尺寸或位置（无 translateY、scale）
- ⚠️ **非 4px 倍数的间距** — 所有间距必须是 4 的倍数
- ⚠️ **非 28px 高度的按钮/输入框** — 统一 28px
- ⚠️ **非 44px 高度的 Toolbar** — 统一 44px
- ⚠️ **非 240px 宽度的侧边栏** — 统一 240px
- ⚠️ **无 loading 状态的异步操作** — 必须有 loading 反馈
- ⚠️ **DetailPanel 与 CommandSheet 场景混用** — 查看类必须用 DetailPanel，不用 CommandSheet
- ⚠️ **prefers-reduced-motion 未尊重** — 所有动画必须在此 media query 下禁用
- ⚠️ **亮色模式下对比度不足** — 文字对比度需 ≥ 4.5:1，使用加深后的功能域色标
- ⚠️ **模式切换时出现 FOUC** — 必须在 `<head>` 内联防闪烁脚本

---

## Pre-Delivery Checklist

每次 UI 交付前验证：

- [ ] 所有颜色使用 CSS 变量（`var(--*)`），无硬编码 hex
- [ ] 功能域颜色使用 `var(--domain-*)` token，无 Tailwind 原始类名
- [ ] 按钮 28px / 输入框 28px / Toolbar 44px / 侧边栏 240px
- [ ] hover transition 为 `0.1s ease`，无多余动画
- [ ] 弹窗使用 DetailPanel / CommandSheet / ConfirmDialog，按决策树选择
- [ ] 错误用 Toast，无 `window.alert()`
- [ ] 空状态有专属 empty state 组件
- [ ] 异步操作有 loading 状态
- [ ] 所有可交互元素有 `cursor: pointer`
- [ ] Focus 状态可见（keyboard a11y），focus ring 不可删除
- [ ] 间距为 4px 倍数
- [ ] Lucide React 图标，无 emoji
- [ ] 双模式对比度达标（Light ≥ 4.5:1）
- [ ] Plotly 图表使用 `getPlotlyLayout(isDark)` 动态配置
- [ ] `prefers-reduced-motion` 已尊重
- [ ] FOUC 防闪烁脚本在 `<head>` 内联
