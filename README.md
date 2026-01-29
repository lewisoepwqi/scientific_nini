# 科研数据分析 Web 工具

[![CI](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml/badge.svg)](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml)

为女朋友打造的专属科研数据分析平台。

## 项目结构

```
scientific_nini/
├── frontend/                          # React 前端
├── scientific_data_analysis_backend/  # 数据分析后端 (FastAPI)
├── ai_service/                        # AI 服务 (可选)
├── docker/                            # Docker 部署配置
└── scripts/                           # 部署脚本
```

## 本地开发环境搭建

### 前置要求

- **Node.js** 18+ (推荐使用 nvm 管理)
- **Python** 3.11+
- **Redis** (可选，用于缓存和异步任务)

### 第一步：克隆项目并进入目录

```bash
cd /home/lewis/coding/scientific_nini
```

---

## 启动后端服务

### 1. 创建 Python 虚拟环境

```bash
cd scientific_data_analysis_backend

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# Linux/macOS:
source .venv/bin/activate
# Windows:
# venv\Scripts\activate
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env
```

`.env` 文件默认配置已可用于本地开发，使用 SQLite 数据库，无需额外配置。

关键配置说明：
```bash
# 数据库（默认使用 SQLite，无需安装）
DATABASE_URL=sqlite+aiosqlite:///./scientific_data.db

# 调试模式
DEBUG=true

# CORS 允许的前端地址
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 4. 启动后端服务

```bash
python run.py
```

后端服务将在 http://localhost:8000 启动。

访问 API 文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 启动前端服务

打开新的终端窗口：

### 1. 进入前端目录

```bash
cd /home/lewis/coding/scientific_nini/frontend
```

### 2. 安装 Node.js 依赖

```bash
npm install
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

默认配置：
```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_APP_TITLE=科研数据分析工具
```

### 4. 启动开发服务器

```bash
npm run dev
```

前端将在 http://localhost:5173 启动（Vite 默认端口）。

---

## 启动 AI 服务（可选）

如果需要使用 AI 功能（智能图表推荐、数据分析建议等），需要启动 AI 服务。

打开新的终端窗口：

### 1. 进入 AI 服务目录

```bash
cd /home/lewis/coding/scientific_nini/ai_service
```

### 2. 安装依赖

```bash
# 可以使用后端的虚拟环境，或创建新的
pip install -r requirements.txt
```

### 3. 配置 OpenAI API Key

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 OpenAI API Key：
```bash
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4-turbo  # 或 gpt-3.5-turbo（更便宜）
PORT=8001  # 使用不同端口避免与后端冲突
```

### 4. 启动 AI 服务

```bash
python -m ai_service.main
```

AI 服务将在 http://localhost:8001 启动。

---

## 完整启动流程总结

需要打开 **2-3 个终端窗口**：

**终端 1 - 后端服务：**
```bash
cd scientific_data_analysis_backend
source venv/bin/activate
python run.py
```

**终端 2 - 前端服务：**
```bash
cd frontend
npm run dev
```

**终端 3 - AI 服务（可选）：**
```bash
cd ai_service
python -m ai_service.main
```

启动完成后，打开浏览器访问 http://localhost:5173 即可使用。

---

## 常用开发命令

### 后端

```bash
cd scientific_data_analysis_backend
source venv/bin/activate

# 运行测试
pytest

# 运行单个测试文件
pytest tests/test_health.py -v

# 代码格式化
black app/

# 类型检查
mypy app/

# 代码风格检查
flake8 app/
```

### 前端

```bash
cd frontend

# 开发服务器
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview

# ESLint 检查
npm run lint

# TypeScript 类型检查
npm run type-check
```

---

## 可选：使用 Redis

如果需要使用缓存或 Celery 异步任务功能：

### 安装 Redis

```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# macOS (Homebrew)
brew install redis
brew services start redis

# 验证 Redis 运行
redis-cli ping  # 应返回 PONG
```

---

## 常见问题

### 1. 端口被占用

如果端口已被占用，可以修改配置：

- 后端：修改 `scientific_data_analysis_backend/.env` 中的 `PORT`
- 前端：运行 `npm run dev -- --port 3000` 指定端口
- AI 服务：修改 `ai_service/.env` 中的 `PORT`

### 2. CORS 错误

确保后端 `.env` 中的 `CORS_ORIGINS` 包含前端地址：
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 3. Python 依赖安装失败

某些科学计算库可能需要系统依赖：
```bash
# Ubuntu/Debian
sudo apt install python3-dev build-essential

# macOS
xcode-select --install
```

### 4. Node.js 版本问题

推荐使用 Node.js 18+：
```bash
# 使用 nvm 管理 Node.js 版本
nvm install 18
nvm use 18
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS |
| 状态管理 | Zustand |
| 图表 | Plotly.js |
| 后端 | Python 3.11 + FastAPI |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| ORM | SQLAlchemy 2.0 + Alembic |
| 统计分析 | scipy + statsmodels + scikit-learn |
| AI | OpenAI GPT-4 / GPT-3.5 |

---

## 生产部署

生产环境部署请参考 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)。

## 许可证

MIT License
