# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库工作时的指南。所有约定均**强制生效**，与默认行为冲突时以本文件为准。

---

## 1. 项目概述

Nini 是本地优先的科研 AI 研究伙伴。单进程同时提供 HTTP API（`/api`）、WebSocket Agent 交互（`/ws`）和前端静态文件服务。前端通过 WebSocket 接收流式事件，不用轮询。

---

## 2. 常用命令

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
cd web && npm test             # 前端单元测试（Vitest）

# 构建
cd web && npm run build        # 前端 TypeScript 检查 + Vite 构建
cd web && npm run test:e2e:critical  # 关键 E2E 测试（前端改动时必须通过）
python -m build                # 打包 wheel
```

---

## 3. 工程约束

- Python >= 3.12，构建系统 hatchling；Black 行宽 100，target py312。
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`。
- Pydantic v2：用 `model_validate()` / `model_dump()`，不用 `parse_obj()` / `dict()`。
- FastAPI 路由、WebSocket handler、Tool.execute 全部 `async`；不写同步阻塞代码。
- 测试使用 pytest + pytest-asyncio（`asyncio_mode = "auto"`），测试路径 `tests/`。
- 会话数据在 `data/sessions/{session_id}/`：`meta.json`、`memory.jsonl`（可能很大，分段读取）、`workspace/`。

---

## 4. 非显而易见的约束

- **测试环境**：部分 pytest 测试需要 NINI_* 环境变量（真实 API key）；多数测试有 mock，可在无 .env 下运行。不要假设全部测试都能在干净环境下通过。
- **前端无 lint**：项目未配置 ESLint 或 Prettier。前端代码质量由 TypeScript 编译器（`npm run build`）保障。不要为前端添加 lint 配置，除非用户明确要求。
- **CI 顺序**：CI 在 `pytest` 前运行 `python scripts/check_event_schema_consistency.py`；若事件 schema 不一致，pytest 不会执行。
- **新增 Tool**：继承 `tools/base.py:Tool`，实现 `execute(session, **kwargs) -> ToolResult`，然后在 `tools/registry.py:create_default_tool_registry()` 中注册，否则 LLM 无法调用。
- **沙箱白名单**：修改 `run_code` 允许的 Python 导入时，改 `sandbox/policy.py` 的 `ALLOWED_IMPORT_ROOTS`；R 代码对应 `sandbox/r_policy.py`。
- **废弃目录**：`frontend/`、`scientific_data_analysis_backend/`、`ai_service/` 已废弃，不要修改。
- **大型变更**：`openspec/` 管理变更提案流程，大型特性需经 proposal → design → tasks 流程。
- **能力治理**：新增 Capability 必须声明 `phase`（研究阶段）、`risk_level`（风险等级）、`trust_ceiling`（可信度上限）；高风险能力需通过三维评审。详见 `@docs/nini-vision-charter.md` 第五章。

---

## 5. 语言要求

- **所有代码注释、文档字符串、TODO 必须用中文**。
- **所有问题回答、代码审查反馈、技术解释必须用中文**。
- 专业术语首次出现可保留英文并附中文解释。
- Commit subject 可中英文，但同一仓库保持风格一致。

---

## 6. 编码原则

> 整体倾向于谨慎而非速度；琐碎任务可酌情判断。

### 6.1 动手前先思考

不要假设、不要掩盖困惑、要主动暴露权衡。

- 明确说出你的假设；不确定就问。
- 存在多种解读时，列出来给用户选，不要默默挑一个。
- 如果有更简单的做法，说出来；该反驳就反驳。
- 不清楚就停下来，指出哪里不清楚，然后问。

### 6.2 最小实现

只写解决问题所需的最少代码，不做投机性设计。

- 不超出需求范围添加功能。
- 单点使用的代码不抽象。
- 不为了"灵活/可配置"而预先扩展。
- 不为不可能发生的场景写错误处理。
- 200 行能压到 50 行就重写。
- 自检："资深工程师会认为这过度设计吗？"如果会，简化。

### 6.3 外科式改动

只动必须动的地方，只清理自己制造的烂摊子。

- 不顺手"改进"相邻代码、注释或格式。
- 不重构没坏的东西。
- 沿用现有风格，即使你有不同偏好。
- 注意到无关的死代码：提一下，但**不要删**。
- 自己的改动产生的孤儿（未用的 import / 变量 / 函数）要清理掉；先前就存在的死代码不要碰。
- 判据：每一行变更都能直接追溯到用户的请求。

### 6.4 目标驱动执行

把任务转换为可验证的成功标准，循环直到满足。

- "加校验" → "为非法输入写测试，再让它通过"
- "修 bug" → "写出能复现的测试，再让它通过"
- "重构 X" → "确保重构前后测试都通过"

多步任务先给出简短计划：
```
1. [步骤] → 验证：[检查]
2. [步骤] → 验证：[检查]
3. [步骤] → 验证：[检查]
```

### 6.5 Claude Code 工作方式

- 开始前给出 3～7 条计划（明确将改动哪些文件）。
- 坚持最小改动：不做无关重构、不全仓格式化。
- 不引入新依赖，除非用户明确要求并说明理由。

---

## 7. Git / Commit / PR 规范

### 7.1 分支与合并

- 必须走 `feature/<topic>` / `fix/<topic>` / `chore/<topic>` / `docs/<topic>` → PR → Squash merge。
- 禁止直接向 `main` 提交或开发。

### 7.2 Commit（Conventional Commits）

格式：`type(scope): subject`

类型：`feat` `fix` `docs` `refactor` `perf` `test` `build` `ci` `chore`

禁止：`update`、`fix bug`、`try` 等无信息量描述。

### 7.3 PR

- PR 描述必须包含：**变更内容**、**验证方式**（命令/截图）、**风险与回滚方案**。
- 合并前自检：格式通过、类型检查通过、测试通过、构建通过。

---

## 8. 不可违反的硬性规则

- 禁止直接向 `main` 提交或开发。
- 禁止 `git push --force`（用户明确要求除外）。
- 禁止提交敏感信息（token、密码、私钥）。
- 禁止未经确认的批量删除、重写历史、清理数据等破坏性操作。

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **scientific_nini** (28884 symbols, 52853 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/scientific_nini/context` | Codebase overview, check index freshness |
| `gitnexus://repo/scientific_nini/clusters` | All functional areas |
| `gitnexus://repo/scientific_nini/processes` | All execution flows |
| `gitnexus://repo/scientific_nini/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Tests area (1339 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Tools area (503 symbols) | `.claude/skills/generated/tools/SKILL.md` |
| Work in the Agent area (321 symbols) | `.claude/skills/generated/agent/SKILL.md` |
| Work in the Components area (316 symbols) | `.claude/skills/generated/components/SKILL.md` |
| Work in the Store area (299 symbols) | `.claude/skills/generated/store/SKILL.md` |
| Work in the Memory area (193 symbols) | `.claude/skills/generated/memory/SKILL.md` |
| Work in the Api area (188 symbols) | `.claude/skills/generated/api/SKILL.md` |
| Work in the Nini area (167 symbols) | `.claude/skills/generated/nini/SKILL.md` |
| Work in the Workspace area (143 symbols) | `.claude/skills/generated/workspace/SKILL.md` |
| Work in the Scripts area (112 symbols) | `.claude/skills/generated/scripts/SKILL.md` |
| Work in the Harness area (81 symbols) | `.claude/skills/generated/harness/SKILL.md` |
| Work in the Todo area (80 symbols) | `.claude/skills/generated/todo/SKILL.md` |
| Work in the Sandbox area (76 symbols) | `.claude/skills/generated/sandbox/SKILL.md` |
| Work in the Pages area (64 symbols) | `.claude/skills/generated/pages/SKILL.md` |
| Work in the Executors area (60 symbols) | `.claude/skills/generated/executors/SKILL.md` |
| Work in the Update area (55 symbols) | `.claude/skills/generated/update/SKILL.md` |
| Work in the Providers area (54 symbols) | `.claude/skills/generated/providers/SKILL.md` |
| Work in the Knowledge area (44 symbols) | `.claude/skills/generated/knowledge/SKILL.md` |
| Work in the Skills area (43 symbols) | `.claude/skills/generated/skills/SKILL.md` |
| Work in the Intent area (33 symbols) | `.claude/skills/generated/intent/SKILL.md` |

<!-- gitnexus:end -->
