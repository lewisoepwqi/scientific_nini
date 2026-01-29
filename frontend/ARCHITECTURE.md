# 前端架构文档

## 项目概述

科研数据分析 Web 工具的前端架构，使用 React + TypeScript + Tailwind CSS 构建。

## 架构设计原则

1. **组件化**: 高内聚、低耦合的组件设计
2. **类型安全**: 全面的 TypeScript 类型覆盖
3. **状态管理**: 使用 Zustand 进行轻量级状态管理
4. **可维护性**: 清晰的目录结构和命名规范
5. **可扩展性**: 预留 AI 助手等功能扩展点

## 目录结构

```
frontend/
├── public/                    # 静态资源
├── src/
│   ├── components/            # React 组件
│   │   ├── common/            # 通用组件
│   │   │   ├── Sidebar.tsx   # 侧边栏导航
│   │   │   ├── Header.tsx    # 顶部导航
│   │   │   └── Notification.tsx  # 通知组件
│   │   ├── upload/            # 上传相关组件
│   │   │   ├── FileUpload.tsx    # 文件上传组件
│   │   │   └── FilePreview.tsx   # 文件预览组件
│   │   ├── chart/             # 图表相关组件
│   │   │   ├── ChartConfigPanel.tsx  # 图表配置面板
│   │   │   └── ChartDisplay.tsx      # 图表展示组件
│   │   └── chat/              # AI 聊天组件
│   │       └── AIChat.tsx
│   ├── hooks/                 # 自定义 React Hooks
│   │   ├── useFileUpload.ts   # 文件上传 Hook
│   │   ├── useChart.ts        # 图表生成 Hook
│   │   └── useAIChat.ts       # AI 聊天 Hook
│   ├── pages/                 # 页面组件
│   │   ├── UploadPage.tsx     # 上传页面
│   │   ├── PreviewPage.tsx    # 预览页面
│   │   ├── ChartPage.tsx      # 图表页面
│   │   ├── AnalysisPage.tsx   # 分析页面
│   │   └── ChatPage.tsx       # 聊天页面
│   ├── services/              # API 服务
│   │   └── api.ts             # API 封装
│   ├── store/                 # 状态管理
│   │   └── index.ts           # Zustand stores
│   ├── styles/                # 样式文件
│   │   └── index.css          # 全局样式
│   ├── types/                 # TypeScript 类型
│   │   └── index.ts           # 类型定义
│   ├── utils/                 # 工具函数
│   │   └── helpers.ts         # 辅助函数
│   ├── App.tsx                # 主应用组件
│   ├── main.tsx               # 应用入口
│   └── vite-env.d.ts          # Vite 类型声明
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── postcss.config.js
```

## 状态管理

使用 Zustand 进行状态管理，分为以下几个 Store：

### 1. DatasetStore
管理数据集相关状态：
- `currentDataset`: 当前选中的数据集
- `datasets`: 所有数据集列表
- `uploadProgress`: 上传进度

### 2. ChartStore
管理图表相关状态：
- `config`: 图表配置
- `savedCharts`: 保存的图表列表
- `currentChart`: 当前图表
- `isGenerating`: 是否正在生成

### 3. AnalysisStore
管理统计分析状态：
- `results`: 分析结果列表
- `isAnalyzing`: 是否正在分析
- `selectedResult`: 选中的结果

### 4. AIChatStore
管理 AI 聊天状态：
- `messages`: 消息列表
- `isStreaming`: 是否正在流式响应
- `suggestions`: 分析建议

### 5. UIStore
管理 UI 状态：
- `currentPage`: 当前页面
- `sidebarCollapsed`: 侧边栏是否折叠
- `notifications`: 通知列表
- `theme`: 主题

## API 架构

### 模块划分

```typescript
api.upload    // 文件上传相关
api.chart     // 图表相关
api.analysis  // 统计分析相关
api.ai        // AI 助手相关
```

### 请求拦截器
- 自动添加认证 Token
- 统一错误处理

### 响应格式
```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
  meta?: {
    page?: number;
    pageSize?: number;
    total?: number;
  };
}
```

## 组件设计

### 文件上传组件 (FileUpload)
- 使用 react-dropzone 实现拖拽上传
- 支持进度显示
- 文件类型验证
- 错误处理

### 数据预览组件 (FilePreview)
- 展示文件信息
- 列类型识别
- 数据统计信息
- 数据表格预览

### 图表配置面板 (ChartConfigPanel)
- 图表类型选择
- 数据列选择
- 期刊样式选择
- 统计选项配置
- 外观设置

### 图表展示组件 (ChartDisplay)
- 使用 react-plotly.js
- 支持交互式图表
- 导出功能
- 保存功能

### AI 聊天组件 (AIChat)
- 消息列表展示
- 流式响应支持
- 建议芯片
- 输入框

## 路由设计

使用状态管理实现页面切换：
- `/upload` - 文件上传
- `/preview` - 数据预览
- `/chart` - 图表生成
- `/analysis` - 统计分析
- `/chat` - AI 助手

## 样式方案

### Tailwind CSS 配置
- 自定义颜色（科研主题、期刊配色）
- 自定义字体
- 自定义动画
- 自定义工具类

### CSS 变量
```css
:root {
  --color-primary: #0ea5e9;
  --color-nature: #E31837;
  --color-science: #8B0000;
  --color-cell: #008080;
}
```

## 类型定义

### 核心类型
- `ColumnType`: 列数据类型
- `ColumnInfo`: 列信息
- `DatasetInfo`: 数据集信息
- `ChartType`: 图表类型
- `ChartConfig`: 图表配置
- `StatisticalResult`: 统计结果
- `AIMessage`: AI 消息

## 开发规范

### 命名规范
- 组件: PascalCase (e.g., `FileUpload`)
- Hooks: camelCase with `use` prefix (e.g., `useFileUpload`)
- 工具函数: camelCase (e.g., `formatFileSize`)
- 类型: PascalCase (e.g., `DatasetInfo`)
- 常量: UPPER_SNAKE_CASE

### 文件组织
- 每个组件一个文件
- 相关组件放在同一目录
- 共享逻辑提取到 hooks
- 类型定义集中管理

### 代码风格
- 使用 TypeScript 严格模式
- 使用函数组件和 Hooks
- 避免使用 `any` 类型
- 添加必要的注释

## 性能优化

1. **代码分割**: 使用动态导入
2. **懒加载**: 页面组件懒加载
3. **Memoization**: 使用 React.memo 和 useMemo
4. **虚拟列表**: 大数据表格使用虚拟滚动
5. **防抖节流**: 频繁触发的事件处理

## 安全考虑

1. **XSS 防护**: 用户输入转义
2. **CSRF 防护**: 使用 Token
3. **文件安全**: 文件类型和大小验证
4. **API 安全**: 认证和授权

## 扩展计划

### 短期
- [ ] 完善统计分析功能
- [ ] 图表库管理
- [ ] 历史分析记录

### 中期
- [ ] 用户认证系统
- [ ] 数据导出功能
- [ ] 协作功能

### 长期
- [ ] 插件系统
- [ ] 自定义图表类型
- [ ] 机器学习集成

## 参考资料

- [React 官方文档](https://react.dev/)
- [TypeScript 官方文档](https://www.typescriptlang.org/)
- [Tailwind CSS 官方文档](https://tailwindcss.com/)
- [Zustand 官方文档](https://github.com/pmndrs/zustand)
- [Plotly.js 官方文档](https://plotly.com/javascript/)
