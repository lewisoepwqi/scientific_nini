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

# Repository Guidelines

## Project Structure & Module Organization
- 当前仓库采用单架构：`src/nini/`（后端与 Agent 运行时）+ `web/`（前端）+ `tests/`（测试）+ `docs/`（文档）+ `data/`（运行时数据）。
- 旧三服务目录（`frontend/`、`scientific_data_analysis_backend/`、`ai_service/`）已清理，不再作为开发目标。
- 新功能默认落在 `src/nini/` 与 `web/src/`。

## Architecture Overview
- 运行链路：`Web UI` → `FastAPI Gateway(HTTP + WebSocket)` → `Agent Runner(ReAct)` → `Skills` → `Memory/Storage`。
- 单进程启动：`nini start`（或 `python -m nini start`）。
- 持久化依赖：`SQLite + 本地文件系统`（默认 `data/`）。

## 重构阶段状态（基于 `dynamic-leaping-cray.md`）
- 当前判断日期：`2026-02-07`。
- `Phase 1`～`Phase 7` 已完成并通过基础验证（测试、前端构建、打包烟测）。
- 当前阶段进入发布后维护：稳定性、性能与可观测性优化。

## Build, Test, and Development Commands
- 安装：`pip install -e .[dev]`
- 首次初始化：`nini init`
- 环境检查：`nini doctor`
- 启动服务：`nini start --reload`
- 后端测试：`pytest -q`
- 前端构建：`cd web && npm install && npm run build`
- 打包：`python -m build`

## Coding Style & Naming Conventions
- 所有文档与注释必须使用中文；专业术语首次出现可保留英文并附中文解释。
- Python 使用 `snake_case`，遵循 `black` 风格。
- TypeScript/React 组件使用 `PascalCase`，变量使用 `camelCase`。
- 变更时保持现有风格，避免无关重排。

## Testing Guidelines
- 后端测试位于 `tests/`，优先覆盖 `agent/`、`skills/`、`api/`、`sandbox/`。
- 最小回归要求：`pytest -q` + `cd web && npm run build`。
- 涉及 CLI 变更时必须补充或更新 `tests/test_phase7_cli.py`。

## Commit & Pull Request Guidelines
- 提交信息建议使用中文、动词开头、说明影响范围。
- PR 建议包含：变更摘要、关键测试命令与结果、必要截图（如有 UI 变化）。

## Security & Configuration Tips
- API Key 仅通过环境变量配置，不提交到仓库。
- `run_code` 使用受限沙箱：导入白名单 + AST 风险函数拦截 + 超时/内存限制。
- 生产环境建议限制上传大小并隔离运行目录。

## Agent-Specific Instructions
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`。
- Pydantic v2 使用 `model_validate()` / `model_dump()`。
- 新能力优先补测试后再接入 WebSocket 事件流。

## Active Technologies
- Python 3.12 + FastAPI + WebSocket + aiosqlite
- pandas / numpy / scipy / statsmodels / plotly / kaleido
- React + TypeScript + Vite + Zustand + Tailwind
- OpenAI / Anthropic / Ollama（多模型路由）

## Recent Changes
- 完成 Phase 7：CLI 子命令（`start/init/doctor`）、打包与烟测。
- 清理旧三服务代码与旧部署脚本，仓库聚焦 Nini 单架构。
- 文档体系更新到 `docs/`（快速开始、配置、CLI、API、开发发布）。

## 后续开发计划（维护阶段）
- 性能优化：大数据集加载速度、图表渲染与导出耗时。
- 可靠性：WebSocket 断线恢复、工具调用失败重试策略。
- 可观测性：增加请求/技能执行耗时日志与错误聚合。
- 用户体验：会话命名、产物管理与下载历史。
