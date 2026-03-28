# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Nini 是本地优先的科研 AI 研究伙伴。单进程同时提供 HTTP API（`/api`）、WebSocket Agent 交互（`/ws`）和前端静态文件服务。前端通过 WebSocket 接收流式事件，不用轮询。

## 常用命令

```bash
# 安装
pip install -e .[dev]          # 后端及开发依赖

# 启动
nini init                      # 生成 .env 配置文件
nini doctor                    # 检查运行环境
nini start --reload            # 开发模式（热重载）
cd web && npm run dev          # 前端开发服务器（端口 3000，代理 /api /ws → 8000）

# 格式化 / 类型检查（按顺序）
black src tests                # 自动格式化（行宽 100）
black --check src tests        # 格式检查
mypy src/nini                  # 类型检查（Python 3.12）

# 测试
python scripts/check_event_schema_consistency.py  # 必须先通过，CI 在 pytest 前运行此脚本
pytest -q                      # 运行全部后端测试
pytest tests/test_phase3_run_code.py::test_name -q  # 单个测试

# 构建
cd web && npm run build        # 前端 TypeScript 检查 + Vite 构建
cd web && npm run test:e2e:critical  # 关键 E2E 测试（前端改动时必须通过）
python -m build                # 打包 wheel
```

## 非显而易见的约束

- **测试环境**：部分 pytest 测试需要 NINI_* 环境变量（真实 API key）；多数测试有 mock，可在无 .env 下运行。不要假设全部测试都能在干净环境下通过。
- **前端无 lint**：项目未配置 ESLint 或 Prettier。前端代码质量由 TypeScript 编译器（`npm run build`）保障。不要为前端添加 lint 配置，除非用户明确要求。
- **CI 顺序**：CI 在 `pytest` 前运行 `python scripts/check_event_schema_consistency.py`；若事件 schema 不一致，pytest 不会执行。
- **新增 Tool**：继承 `tools/base.py:Tool`，实现 `execute(session, **kwargs) -> ToolResult`，然后在 `tools/registry.py:create_default_tool_registry()` 中注册，否则 LLM 无法调用。
- **沙箱白名单**：修改 `run_code` 允许的 Python 导入时，改 `sandbox/policy.py` 的 `ALLOWED_IMPORT_ROOTS`；R 代码对应 `sandbox/r_policy.py`。
- **废弃目录**：`frontend/`、`scientific_data_analysis_backend/`、`ai_service/` 已废弃，不要修改。
- **大型变更**：`openspec/` 管理变更提案流程，大型特性需经 proposal → design → tasks 流程。

## 工程约束

- Python >= 3.12，构建系统 hatchling；Black 行宽 100，target py312。
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`。
- Pydantic v2：用 `model_validate()` / `model_dump()`，不用 `parse_obj()` / `dict()`。
- FastAPI 路由、WebSocket handler、Tool.execute 全部 `async`；不写同步阻塞代码。
- 测试使用 pytest + pytest-asyncio（`asyncio_mode = "auto"`），测试路径 `tests/`。
- 会话数据在 `data/sessions/{session_id}/`：`meta.json`、`memory.jsonl`（可能很大，分段读取）、`workspace/`。

## 语言要求

- **所有代码注释、文档字符串、TODO 必须用中文**。
- **所有问题回答、代码审查反馈、技术解释必须用中文**。
- 专业术语首次出现可保留英文并附中文解释。
- Commit subject 可中英文，但同一仓库保持风格一致。

## 不可违反的规则

- 禁止直接向 `main` 提交或开发；必须走 `feature/<topic>` / `fix/<topic>` / `chore/<topic>` / `docs/<topic>` → PR → Squash merge。
- 禁止 `git push --force`（用户明确要求除外）。
- 禁止提交敏感信息（token、密码、私钥）。
- 禁止未经确认的批量删除、重写历史、清理数据等破坏性操作。

## Commit 规范（Conventional Commits）

格式：`type(scope): subject`
类型：`feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore`
禁止：`update`、`fix bug`、`try` 等无信息量描述。

## PR 规范

PR 描述必须包含：变更内容、验证方式（命令/截图）、风险与回滚方案。
合并前自检：格式通过、类型检查通过、测试通过、构建通过。

## Claude Code 工作方式

- 开始前给出 3～7 条计划（明确将改动哪些文件）。
- 坚持最小改动：不做无关重构，不全仓格式化。
- 不引入新依赖，除非用户明确要求并说明理由。
