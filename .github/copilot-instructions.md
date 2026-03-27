# Copilot Instructions

> Design context for GitHub Copilot to follow when generating or reviewing UI code.

## Design Context

### Users
- 科研人员（研究生、博士后、教授、数据分析师），桌面端长时间工作场景
- 核心任务：通过对话完成数据分析、可视化、代码执行和报告生成

### Brand Personality
- **专业可信 · 简洁高效 · 现代智能**
- 专业但不冷淡，像一个靠谱的科研搭档
- 不是花哨的消费级应用，不是冰冷的企业软件

### Aesthetic Direction
- 精致的产品感（Notion/Linear 级别），克制的装饰，注重排版和间距
- 亮色 + 深色双主题（`darkMode: 'class'`，已配置）
- 避免花哨渐变、过度圆角/阴影、卡通化图标

### Color Semantics
- `purple-600`: 分析能力 | `emerald-600`: 报告/文章 | `amber-600`: 成本统计
- `sky-600`: 研究画像 | `blue-600`: 工作区 | `indigo-600`: 知识库
- 状态色: emerald(连接) / sky(连接中) / amber(警告) / red(断开)

### Design Principles
1. **Clarity over decoration** — UI 不干扰思考，视觉噪音最小化
2. **Dense but breathable** — 信息密度适中，通过留白保持呼吸感
3. **Consistent color semantics** — 功能域固定色彩标识
4. **Dual-mode parity** — 亮色和深色同等质量
5. **Professional warmth** — 专业但不过于冰冷

### Tech Constraints
- React 18 + TypeScript + Tailwind CSS 3 + Zustand（无组件库）
- Lucide React icons, Plotly.js charts
- 中文优先 UI，术语保留英文
