

# Repository Guidelines

> 适用对象：OpenAI Codex / 其他读取 AGENTS.md 的编码智能体
> 目标：保证 `main` 分支稳定、提交可追溯、变更可验证、PR 可审查。

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
- Python 格式化：`black src tests`
- Python 格式检查：`black --check src tests`
- Python 类型检查：`mypy src/nini`
- 后端测试：`pytest -q`
- 前端构建：`cd web && npm install && npm run build`
- 前端 E2E（按需）：`cd web && npm run test:e2e`
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

## Git 工作流（强制）
- 禁止在 `main` 直接开发与提交。
- 所有开发必须走：`feature/fix/chore/docs` 分支 → PR → 合并到 `main`。
- 分支命名规范：
  - `feature/<topic>`：新功能
  - `fix/<topic>`：缺陷修复
  - `chore/<topic>`：构建、依赖、配置
  - `docs/<topic>`：文档
- 合并策略：
  - 默认使用 `Squash merge`，保持 `main` 历史整洁。
  - 禁止在 `main` 执行 `git push --force`。

## 提交规范（强制）
### 提交信息格式（Conventional Commits）
- 格式：`type(scope): subject`。
- `scope` 可省略；`subject` 推荐英文小写开头（允许中文，但全仓保持一致）。
- `type` 取值：
  - `feat`：新功能
  - `fix`：修复缺陷
  - `docs`：文档
  - `refactor`：重构（不改变外部行为）
  - `perf`：性能优化
  - `test`：测试
  - `build`：构建系统
  - `ci`：CI 配置
  - `chore`：杂项
- 示例：
  - `feat(agent): add websocket reconnect`
  - `fix(api): handle empty dataset response`
  - `docs(cli): update init examples`

### 提交粒度与内容
- 一个提交只做一件事，避免“顺手改”无关内容。
- 禁止仅为格式化而全仓改动（除非任务就是格式化）。
- 禁止提交敏感信息（token、密码、证书、私钥）。
- 仅提交必要文件；`lockfile`（如 `uv.lock`）仅在依赖变更时提交。

## PR 规范（强制）
### PR 基本要求
- PR 描述必须写清：
  - 变更内容（做了什么）
  - 验证方式（怎么验证通过）
  - 风险点与回滚方式（如有）
- PR 应尽量小，保证可审查、可回滚。

### 合并前自检清单（必须通过）
- ✅ 代码可运行/可编译（若适用）。
- ✅ 测试通过（若存在测试体系）。
- ✅ lint/format 通过（若适用）。
- ✅ 新增/修改行为有对应测试或说明（至少二选一）。
- ✅ 文档/注释同步更新（若影响使用方式）。
- 推荐执行顺序：`format → lint/typecheck → test → build`。
- 本仓库常用命令：
  - `black --check src tests`
  - `mypy src/nini`
  - `pytest -q`
  - `cd web && npm run build`
  - `python -m build`（发布前建议）
  - `cd web && npm run test:e2e`（前端交互改动时建议）

## 智能体工作约束（强制）
- 先计划后修改：开始动手前先输出 3～7 条行动计划（文件级别）。
- 最小改动原则：优先局部修改，避免无关重构。
- 新增依赖必须说明原因，并优先复用现有依赖；如必须新增依赖，PR 描述中必须写明。
- 任何可能破坏性操作（清库、批量删除、重写历史等）必须停止并请求人工确认。

## Done 定义（强制）
- 变更已按规范提交在非 `main` 分支上。
- PR 已创建（或已达到可直接创建状态，描述与检查项齐全）。
- 合并前自检清单全部通过（或在 PR 明确说明豁免原因）。
- 变更说明清晰，可复现、可回滚。

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
