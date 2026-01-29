# 快速开始指南

## 环境要求

- Node.js 18+
- npm 9+ 或 yarn 1.22+

## 安装步骤

### 1. 进入项目目录

```bash
cd frontend
```

### 2. 安装依赖

```bash
npm install
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_APP_TITLE=科研数据分析工具
```

### 4. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 5. 构建生产版本

```bash
npm run build
```

## 项目结构说明

```
frontend/
├── src/
│   ├── components/     # React 组件
│   ├── hooks/          # 自定义 Hooks
│   ├── pages/          # 页面组件
│   ├── services/       # API 服务
│   ├── store/          # 状态管理 (Zustand)
│   ├── styles/         # 样式文件
│   ├── types/          # TypeScript 类型
│   └── utils/          # 工具函数
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 可用脚本

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 构建生产版本 |
| `npm run preview` | 预览生产版本 |
| `npm run lint` | 运行 ESLint |
| `npm run type-check` | 运行 TypeScript 类型检查 |

## 依赖说明

### 核心依赖
- `react`: React 框架
- `react-dom`: React DOM
- `typescript`: TypeScript 支持

### UI 相关
- `tailwindcss`: CSS 框架
- `lucide-react`: 图标库
- `react-hot-toast`: 通知组件

### 状态管理
- `zustand`: 轻量级状态管理

### 图表
- `react-plotly.js`: Plotly React 封装
- `plotly.js`: 图表库

### 文件处理
- `react-dropzone`: 拖拽上传
- `papaparse`: CSV 解析
- `xlsx`: Excel 解析

### HTTP 请求
- `axios`: HTTP 客户端

## 开发注意事项

1. **类型安全**: 所有组件和函数都应该有明确的类型定义
2. **状态管理**: 使用 Zustand 进行状态管理，避免 prop drilling
3. **API 调用**: 统一使用 `services/api.ts` 中的方法
4. **样式**: 使用 Tailwind CSS 工具类，避免内联样式
5. **组件**: 保持组件单一职责，复杂逻辑提取到 hooks

## 常见问题

### Q: 安装依赖时卡住？
A: 尝试使用淘宝镜像：`npm config set registry https://registry.npmmirror.com`

### Q: 启动时报错找不到模块？
A: 检查 `tsconfig.json` 中的 paths 配置是否正确

### Q: 图表不显示？
A: 确保已安装 plotly.js，并且数据格式正确

### Q: 如何添加新的图表类型？
A: 在 `types/index.ts` 中添加新的 `ChartType`，然后在 `ChartConfigPanel` 中添加对应的选项

## 后端 API 要求

前端期望后端提供以下 API：

### 文件上传
- `POST /api/upload` - 上传文件
- `GET /api/datasets` - 获取数据集列表
- `GET /api/datasets/:id` - 获取数据集详情

### 图表
- `POST /api/charts/generate` - 生成图表
- `POST /api/charts/:id/export` - 导出图表

### 统计分析
- `POST /api/analysis/descriptive` - 描述性统计
- `POST /api/analysis/t-test` - t 检验
- `POST /api/analysis/anova` - ANOVA
- `POST /api/analysis/correlation` - 相关性分析

### AI 助手
- `POST /api/ai/chat` - 发送消息
- `POST /api/ai/chat/stream` - 流式消息

详细的 API 规范请参考 `ARCHITECTURE.md` 文件。

## 下一步

1. 启动后端服务
2. 配置 API 地址
3. 测试各功能模块
4. 根据需求进行定制开发
