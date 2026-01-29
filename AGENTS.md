# Repository Guidelines

## Project Structure & Module Organization
- 仓库 由 三个 主子系统 构成: `frontend/` (React + TypeScript + Vite), `scientific_data_analysis_backend/` (Python FastAPI), `ai_service/` (独立 AI 服务).
- 前端 源码 通常 位于 `frontend/src/`; 后端 业务 代码 位于 `scientific_data_analysis_backend/app/`; AI 服务 入口 位于 `ai_service/`.
- 部署 与 运维 脚本 在 `docker/` 与 `scripts/`.

## Architecture Overview
- 典型 调用 路径: 前端 → FastAPI 后端 → AI 服务; 数据 存储 依赖 PostgreSQL 与 Redis.
- 后端 提供 `/api/v1/*` 统计 与 可视化 接口; AI 服务 提供 `/api/ai/*` 流式 分析 接口.

## Build, Test, and Development Commands
- 前端: `cd frontend && npm install`, `npm run dev`, `npm run build`, `npm run lint`, `npm run type-check`.
- 后端: `cd scientific_data_analysis_backend && python -m venv venv && source venv/bin/activate`, `pip install -r requirements.txt`, `python run.py`, `pytest`, `black app/`, `mypy app/`, `flake8 app/`.
- AI 服务: `cd ai_service && pip install -r requirements.txt`, `python -m ai_service.main`.
- 容器: `cd docker && docker-compose up -d`, `docker-compose logs -f`.

## Coding Style & Naming Conventions
- 所有 文档 与 注释 必须 使用 中文; 专业 术语 首次 出现 可保留 英文 并附 中文 解释.
- Python 遵循 `black` 与 `flake8` 规范, 命名 使用 `snake_case`; TypeScript/React 组件 使用 `PascalCase`, 变量 使用 `camelCase`.
- 变更 时 保持 现有 文件 风格, 避免 额外 重排.

## Testing Guidelines
- 后端 使用 `pytest`, 测试 位于 `scientific_data_analysis_backend/tests/`.
- 运行 示例: `pytest` 或 `pytest tests/test_health.py -v`.
- 前端 暂无 明确 测试 命令 时, 至少 运行 `npm run lint` 与 `npm run type-check`.

## Commit & Pull Request Guidelines
- 当前 环境 无 `.git` 历史, 无法 总结 既有 提交 规范; 默认 使用 中文 简洁 描述, 动词 开头, 说明 影响 范围.
- PR 建议 包含: 变更 摘要, 关联 问题/需求, 关键 测试 命令 结果; 涉及 UI 请附 截图.

## Security & Configuration Tips
- 密钥 与 连接 串 仅通过 环境变量 配置, 不提交 至 仓库.
- AI 服务 依赖 OpenAI API 凭据, 本地 开发 前 请确认 已配置.

## Agent-Specific Instructions
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`; Pydantic v2 使用 `model_validate()` / `model_dump()`.
- SQLAlchemy 异步 查询 使用 `select()`; SQLite Enum 需 `native_enum=False`.
