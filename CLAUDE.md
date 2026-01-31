<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目语言要求

**本项目的所有文档、代码注释、用户交互和提交信息必须严格使用中文。**

- 代码注释、文档字符串、错误提示必须使用中文
- Git 提交信息必须使用中文
- 专业术语可保留英文原文，但首次出现时需提供中文解释

## 项目概述

这是一个为科研数据分析设计的 Web 平台，包含三个主要子系统：

1. **前端 (frontend/)** - React + TypeScript + Vite
2. **数据分析后端 (scientific_data_analysis_backend/)** - Python FastAPI
3. **AI 服务 (ai_service/)** - 独立的 AI 分析服务

## 常用命令

### 前端开发

```bash
cd frontend
npm install          # 安装依赖
npm run dev          # 启动开发服务器
npm run build        # 构建生产版本
npm run lint         # ESLint 检查
npm run type-check   # TypeScript 类型检查
```

### 数据分析后端开发

```bash
cd scientific_data_analysis_backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py                    # 启动开发服务器 (localhost:8000)
pytest                           # 运行测试
pytest tests/test_health.py -v   # 运行单个测试文件
black app/                       # 代码格式化
mypy app/                        # 类型检查
flake8 app/                      # 代码风格检查
```

### AI 服务开发

```bash
cd ai_service
pip install -r requirements.txt
python -m ai_service.main        # 启动服务 (localhost:8000)
```

### Docker 部署

```bash
cd docker
docker-compose up -d             # 启动所有服务
docker-compose logs -f           # 查看日志
./scripts/deploy.sh --full       # 完整部署
./scripts/db-migrate.sh migrate  # 数据库迁移
```

## 系统架构

```
┌─────────────────┐
│   React 前端    │
│  (Vite + TS)    │
└────────┬────────┘
         │ HTTP
┌────────▼────────┐     ┌──────────────────┐
│  FastAPI 后端   │────▶│    AI 服务       │
│ (数据分析)      │     │  (OpenAI/GPT)    │
└────────┬────────┘     └──────────────────┘
         │
┌────────▼────────┐
│   PostgreSQL    │
│   + Redis       │
└─────────────────┘
```

### 前端状态管理 (Zustand)

- `DatasetStore` - 数据集和上传状态
- `ChartStore` - 图表配置和生成状态
- `AnalysisStore` - 统计分析结果
- `AIChatStore` - AI 聊天和流式响应
- `UIStore` - 页面导航和通知

### 后端 API 路由

- `/api/v1/datasets/*` - 数据集上传和管理
- `/api/v1/analysis/*` - 统计分析 (t检验、ANOVA、相关性等)
- `/api/v1/visualizations/*` - 图表生成 (散点图、箱线图、热图等)
- `/api/v1/health` - 健康检查

### AI 服务 API 路由

- `/api/ai/chart/recommend` - 智能图表推荐
- `/api/ai/data/analyze` - AI 数据分析
- `/api/ai/experiment/design` - 实验设计助手
- `/api/ai/cost/summary` - 成本统计

所有 AI 端点支持流式响应（添加 `/stream` 后缀）。

## 关键技术栈

### 前端
- Plotly.js (react-plotly.js) 用于交互式图表
- react-dropzone 用于文件上传
- Tailwind CSS 用于样式
- Axios 用于 HTTP 请求

### 后端
- SQLAlchemy 2.0 + aiosqlite 用于异步数据库
- Alembic 用于数据库迁移
- scipy/statsmodels 用于统计分析
- Plotly + kaleido 用于服务端图表生成
- Celery + Redis 用于异步任务

### AI 服务
- OpenAI API (GPT-4/GPT-4-turbo/GPT-3.5-turbo)
- 支持流式响应 (SSE)
- 内置成本追踪和重试机制
- 预留 LangGraph Agent 架构

## 数据可视化

支持学术期刊风格的图表：Nature、Science、Cell、NEJM、Lancet。图表可导出为 SVG/PNG/JPEG 格式。

## 开发注意事项

### Python 版本兼容性
- 项目使用 Python 3.12+
- 使用 `datetime.now(timezone.utc)` 替代已废弃的 `datetime.utcnow()`
- 模型文件中已定义 `utcnow()` 辅助函数

### Pydantic v2
- 使用 `model_config = ConfigDict(from_attributes=True)` 替代 `class Config`
- 使用 `model_validate()` 替代 `from_orm()`
- 使用 `model_dump()` 替代 `dict()`

### SQLAlchemy + SQLite
- Enum 类型需要 `native_enum=False` 参数
- 使用异步 API：`select()` 语法而非 `query()`

### 异步代码
- 端点中的 Pandas 操作是同步的，可能阻塞事件循环
- 大数据集处理建议使用 `asyncio.to_thread()`
