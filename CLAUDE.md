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

> 适用对象：Claude Code
> 目标：让 Claude Code 严格遵循本仓库的提交与 PR 规范，避免 `main` 被污染。

## 仓库现状（以当前代码为准）
- 当前仓库为单架构：`src/nini/`（后端与 Agent Runtime）+ `web/`（前端）+ `tests/`（测试）+ `docs/`（文档）+ `data/`（运行时数据）。
- 旧目录 `frontend/`、`scientific_data_analysis_backend/`、`ai_service/` 已废弃，不作为开发目标。
- 常用启动命令：`nini start --reload`（或 `python -m nini start`）。

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

本仓库建议命令（按 `format → lint/typecheck → test → build`）：
- `black --check src tests`
- `mypy src/nini`
- `pytest -q`
- `cd web && npm run build`
- `python -m build`（发布前建议）
- `cd web && npm run test:e2e`（前端交互改动时建议）

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
- 使用 `datetime.now(timezone.utc)` 代替 `datetime.utcnow()`。
- Pydantic v2 使用 `model_validate()` / `model_dump()`。
- 新能力优先补测试，再接入 WebSocket 事件流。
