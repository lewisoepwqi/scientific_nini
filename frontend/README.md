# 科研数据分析工具

为女朋友打造的专属科研数据分析 Web 平台。

## 功能特性

### 1. 文件上传
- 支持 CSV、Excel (.xlsx, .xls)、TXT 格式
- 拖拽上传
- 上传进度显示
- 自动数据类型识别

### 2. 数据预览
- 数据表格预览
- 列类型识别（数值、类别、日期、文本）
- 基础统计信息展示
- 描述性统计

### 3. 图表生成
- 多种图表类型：散点图、折线图、柱状图、箱线图、小提琴图、直方图、热图、相关性矩阵
- X/Y 轴列选择
- 分组/着色列选择
- 期刊样式选择（Nature/Science/Cell）
- 统计显著性标记
- 图表导出（SVG/PNG/JPEG）

### 4. AI 助手
- 聊天式 AI 助手
- 流式响应显示
- 分析建议展示
- 图表建议

### 5. 统计分析
- 描述性统计
- t 检验
- ANOVA
- 相关性分析
- 卡方检验
- Mann-Whitney U 检验
- Kruskal-Wallis 检验

## 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **样式**: Tailwind CSS
- **状态管理**: Zustand
- **图表库**: Plotly.js
- **HTTP 客户端**: Axios
- **文件上传**: react-dropzone

## 项目结构

```
frontend/
├── public/                 # 静态资源
├── src/
│   ├── components/         # 组件
│   │   ├── common/         # 通用组件
│   │   ├── upload/         # 上传组件
│   │   ├── chart/          # 图表组件
│   │   └── chat/           # AI 聊天组件
│   ├── hooks/              # 自定义 Hooks
│   ├── pages/              # 页面组件
│   ├── services/           # API 服务
│   ├── store/              # 状态管理
│   ├── styles/             # 样式文件
│   ├── types/              # TypeScript 类型
│   └── utils/              # 工具函数
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 快速开始

### 安装依赖

```bash
cd frontend
npm install
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，设置 API 地址
```

### 启动开发服务器

```bash
npm run dev
```

### 构建生产版本

```bash
npm run build
```

### 预览生产版本

```bash
npm run preview
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| VITE_API_BASE_URL | API 基础 URL | http://localhost:8000/api |
| VITE_APP_TITLE | 应用标题 | 科研数据分析工具 |

## API 接口

### 文件上传
- `POST /api/upload` - 上传文件
- `POST /api/upload/preview` - 预览文件
- `GET /api/datasets` - 获取数据集列表
- `GET /api/datasets/:id` - 获取数据集详情
- `DELETE /api/datasets/:id` - 删除数据集

### 图表
- `POST /api/charts/generate` - 生成图表
- `POST /api/charts` - 保存图表
- `GET /api/charts` - 获取图表列表
- `DELETE /api/charts/:id` - 删除图表
- `POST /api/charts/:id/export` - 导出图表

### 统计分析
- `POST /api/analysis/descriptive` - 描述性统计
- `POST /api/analysis/t-test` - t 检验
- `POST /api/analysis/anova` - ANOVA
- `POST /api/analysis/correlation` - 相关性分析
- `POST /api/analysis/chi-square` - 卡方检验

### AI 助手
- `POST /api/ai/chat` - 发送消息
- `POST /api/ai/chat/stream` - 流式消息
- `GET /api/ai/suggestions` - 获取建议

## 开发计划

- [x] 项目基础架构
- [x] 文件上传组件
- [x] 数据预览组件
- [x] 图表配置面板
- [x] 图表展示组件
- [x] AI 聊天组件（基础）
- [ ] 统计分析页面完善
- [ ] 图表库管理
- [ ] 历史分析记录
- [ ] 用户认证
- [ ] 数据导出功能

## 贡献指南

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -am 'Add xxx feature'`)
4. 推送分支 (`git push origin feature/xxx`)
5. 创建 Pull Request

## 许可证

MIT License

## 特别感谢

献给最可爱的女朋友 ❤️
