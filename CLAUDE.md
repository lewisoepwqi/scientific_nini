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

> 适用对象：Claude Code
> 目标：让 Claude Code 严格遵循本仓库的提交与 PR 规范，避免 `main` 被污染。

## 项目概述

Nini 是一个本地优先的科研数据分析 AI Agent。用户通过对话上传并分析数据，Agent 自动调用统计、作图、清洗、代码执行与报告生成技能。单进程同时提供 HTTP API、WebSocket Agent 交互和前端静态文件。

## 项目语言要求
文档、注释、用户交互默认使用中文；专业术语首次出现可保留英文并附中文解释。
提交信息必须遵循 Conventional Commits；subject 可中文或英文，但同一仓库应保持风格一致。

## 常用命令

### 安装与启动
```bash
pip install -e .[dev]          # 安装后端及开发依赖
nini init                      # 生成 .env 配置文件
nini doctor                    # 检查运行环境
nini start --reload            # 开发模式启动（热重载），等价于 python -m nini start --reload
cd web && npm install && npm run build  # 构建前端
```

### 格式化 / 类型检查 / 测试 / 构建（按顺序）
```bash
black --check src tests        # 代码格式检查（行宽 100）
black src tests                # 自动格式化
mypy src/nini                  # 类型检查（Python 3.12）
pytest -q                      # 运行全部后端测试
pytest tests/test_phase3_run_code.py -q           # 运行单个测试文件
pytest tests/test_phase3_run_code.py::test_name -q  # 运行单个测试
cd web && npm run build        # 前端 TypeScript 检查 + Vite 构建
cd web && npm run test:e2e     # Playwright E2E 测试（前端交互改动时）
```

### 发布
```bash
python -m build                # 打包到 dist/
```

## 架构

### 后端 (`src/nini/`)

**请求入口**：`app.py` 工厂函数 `create_app()` 创建 FastAPI 实例，注册 HTTP 路由（`api/routes.py`，前缀 `/api`）和 WebSocket 端点（`api/websocket.py`，路径 `/ws`）。前端构建产物通过 StaticFiles 挂载 + SPA fallback 中间件提供服务。

**Agent 核心循环**：`agent/runner.py` 中的 `AgentRunner` 实现 ReAct 循环：接收用户消息 → 构建上下文（system prompt + 会话历史 + 知识库检索） → 调用 LLM → 解析 tool_calls → 执行对应 Skill → 循环直到无 tool_call。所有事件通过 callback 推送（WebSocket 端点消费这些事件流式发送给客户端）。

**多模型路由**：`agent/model_resolver.py` 中 `ModelResolver` 管理多 LLM 客户端（OpenAI、Anthropic、Ollama、Moonshot、Kimi Coding、智谱、DeepSeek、阿里百炼），统一为 `BaseLLMClient.chat()` 异步流式接口。按优先级尝试，失败自动降级到下一个可用提供商。

**技能系统**：每个技能继承 `skills/base.py:Skill`，实现 `execute(session, **kwargs) -> SkillResult`。`skills/registry.py:SkillRegistry` 在启动时注册全部技能，并提供给 LLM 的 tools schema。技能分类：
- 统计：`t_test`、`anova`、`correlation`、`regression`、`mann_whitney`、`kruskal_wallis`（含自动降级，如正态性不满足 t_test → mann_whitney）
- 可视化：`create_chart`（7 种图表 + 6 种期刊风格）、`export_chart`
- 数据操作：`load_dataset`、`preview_data`、`data_summary`、`clean_data`
- 代码执行：`run_code`（通过 `sandbox/executor.py` 进程隔离执行，受限 builtins + 内存/时间限制）
- 产物：`generate_report`、`organize_workspace`
- 复合技能模板：`skills/templates.py` 中预定义多步分析流程

**会话管理**：`agent/session.py` 管理会话状态（消息历史、已加载 DataFrame、产物列表）。会话持久化到 `data/sessions/{session_id}/`。

**沙箱执行**：`sandbox/executor.py` 通过 `multiprocessing` 进程隔离执行用户代码，`sandbox/policy.py` 做静态代码审查（禁止危险导入/操作），`sandbox/capture.py` 捕获 stdout/stderr。

**配置**：`config.py` 基于 `pydantic-settings`，环境变量前缀 `NINI_`，自动读取项目根 `.env` 文件。全局单例 `settings`。

**知识库**：`knowledge/` 提供 RAG 向量检索，`memory/` 管理对话历史压缩与存储。

**工作区**：`workspace/manager.py` 管理会话文件（数据集、产物、笔记），支持文件夹组织。

### 前端 (`web/`)

React 18 + Vite + TypeScript + Tailwind CSS。状态管理使用 Zustand 单一 store（`store.ts`）。通过 WebSocket 与后端 Agent 交互，接收流式事件（text/chart/data/tool_call/done 等）。

关键组件：`ChatPanel`（对话主界面）、`MessageBubble`（消息渲染）、`MarkdownContent`（Markdown + 代码高亮）、`ChartViewer`/`PlotlyFromUrl`（Plotly 图表）、`DataViewer`（表格预览）、`WorkspacePanel`/`WorkspaceSidebar`（文件管理）、`FileUpload`（数据上传）。

### 数据流

```
用户消息 → WebSocket /ws → AgentRunner.run()
  → ModelResolver.chat() (流式 LLM)
  → 解析 tool_calls → SkillRegistry.invoke()
  → Skill.execute() → SkillResult
  → callback 推送事件 → WebSocket 发送 JSON 到前端
  → Zustand store 更新 → React 渲染
```

## 仓库现状（以当前代码为准）
- 当前仓库为单架构：`src/nini/`（后端与 Agent Runtime）+ `web/`（前端）+ `tests/`（测试）+ `docs/`（文档）+ `data/`（运行时数据）。
- 旧目录 `frontend/`、`scientific_data_analysis_backend/`、`ai_service/` 已废弃，不作为开发目标。
- `openspec/` 管理变更提案流程，大型变更需通过 proposal → design → tasks 流程。

## 项目语言要求
- 文档、注释、用户交互默认使用中文；专业术语首次出现可保留英文并附中文解释。
- 提交信息必须遵循 Conventional Commits；`subject` 可中文或英文，但同一仓库应保持风格一致。

## 1) 不可违反的规则（强制）
- 禁止在 `main` 分支直接开发或提交。
- 必须使用：分支开发 → PR → 合并到 `main`。
- 禁止 `git push --force`（除非用户明确要求）。
- 禁止提交任何敏感信息（token、密码、私钥、证书等）。

## 2) 标准开发流程（强制）
1. 同步本地 `main`：
   - `git checkout main && git pull --ff-only`
2. 从 `main` 新建分支（按类型命名）：
   - `feature/<topic>` / `fix/<topic>` / `chore/<topic>` / `docs/<topic>`
3. 在分支上小步提交：
   - 每次提交只做一件事，避免混合无关修改
4. 推送分支并创建 PR：
   - base 必须是 `main`
5. 合并策略：
   - 推荐使用 Squash merge 合并到 `main`

## 3) Commit 规范（Conventional Commits，强制）
- 格式：`type(scope): subject`
- `type`：`feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore`
- 示例：
  - `feat(ui): add status badge`
  - `fix(api): prevent null crash`
  - `chore(deps): bump dependencies`
- 要求：
  - `subject` 必须具体、可读、可追溯
  - 禁止 `update`、`fix bug`、`try` 这类无信息量描述

## 4) PR 规范（强制）
### PR 描述必须包含
- 变更内容：做了什么
- 验证方式：如何验证（命令/步骤/截图）
- 风险与回滚：可能影响与回滚方法（如有）

### 合并前自检（必须完成）
- ✅ tests 通过（若存在）
- ✅ lint/format 通过（若存在）
- ✅ 构建/运行验证通过（若适用）
- ✅ 文档/注释已更新（若影响使用方式）

## 5) Claude Code 工作方式（强制）
- 开始前先给出 3～7 条计划（明确将修改/新增哪些文件）。
- 坚持最小改动：避免无关重构、避免全仓格式化。
- 除非用户明确要求，否则不要引入新依赖；若必须引入，需说明原因与替代方案。
- 任何可能破坏性的操作（批量删除、重写历史、清理数据）必须先请求人工确认。
- 修改完成后必须提供：
  - 变更摘要（按文件列出）
  - 验证结果（运行了哪些命令、是否通过）
  - 建议的 PR 标题与描述（按本规范）

## 6) 完成标准（强制）
仅当满足以下条件才算完成：
- 变更已按规范提交在分支上
- PR 已创建或已准备好创建（含标题与描述）
- 自检全部通过，或明确列出未通过项及原因

## 工程约束补充
- Python >= 3.12，构建系统 hatchling。
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`。
- Pydantic v2 使用 `model_validate()` / `model_dump()`。
- 新能力优先补测试，再接入 WebSocket 事件流。
- 添加新技能时：继承 `skills/base.py:Skill`，在 `skills/registry.py:create_default_registry()` 中注册。
- 沙箱安全策略三重防护：AST 静态分析（`sandbox/policy.py`）+ 受限 builtins（`sandbox/executor.py`）+ 进程隔离（multiprocessing spawn）。修改白名单在 `sandbox/policy.py` 的 `ALLOWED_IMPORT_ROOTS`。
- 会话数据存储在 `data/sessions/{session_id}/`，包含 `meta.json`（标题）、`memory.jsonl`（对话历史，可能很大需分段读取）、`workspace/`（上传文件和产物）。
- Black 行宽 100，目标版本 py312。
- 测试使用 pytest + pytest-asyncio（`asyncio_mode = "auto"`），测试路径 `tests/`。
- 前端环境变量或 API 代理配置在 `web/vite.config.ts`。