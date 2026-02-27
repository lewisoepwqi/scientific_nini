# Nini Skills 跨 Coding Agent 兼容规范（2026-02-27）

## 目标

让 Nini 的 Markdown Skills 同时兼容以下生态，并且在 Nini 内可统一发现与管理：

- Claude Code Skills
- OpenAI Codex Skills
- OpenCode Skills
- Agent Skills 开放规范
- Cursor / Windsurf / Gemini CLI / GitHub Copilot 的仓库级指令体系（AGENTS/CLAUDE/GEMINI 等）

> 说明：Cursor/Windsurf/Gemini/Copilot 主要是“仓库级指令文件”规范，不是目录化 Skills 规范。
> Nini 对这部分采用“文档兼容”策略，对 Claude/Codex/Agent Skills 采用“目录 + Frontmatter 兼容”策略。

## 官方规范要点（摘要）

### 1. Claude Code Skills

- 目录约定：`.claude/skills/<skill>/SKILL.md`
- 载体：Markdown + Frontmatter
- 关键字段：`name`、`description`（`category` 可选）

### 2. OpenAI Codex Skills

- 目录约定：`<repo>/.codex/skills/`（项目级）
- 载体：Markdown Skill（含 Frontmatter）
- 支持扩展：`agents` 字段及 `agents/openai.yaml`（Agent Skills 兼容）

### 3. Agent Skills（开放规范）

- 目录约定：`.agents/skills/<skill>/SKILL.md`
- 载体：Markdown + YAML Frontmatter
- 常见扩展字段：`agents`、`allowed-tools`、`argument-hint`、`user-invocable`、`disable-model-invocation`

### 4. 其他 Coding Agent（仓库级指令）

- Cursor / Windsurf / Gemini CLI / GitHub Copilot 已支持 AGENTS.md 及同类指令文件的读取/优先级。
- 这类规范用于“全仓行为约束”，不是 Skill 包管理格式。

## Nini 兼容策略

### 1. 技能目录发现（已实现）

按优先级扫描下列目录：

1. `<repo>/.codex/skills`
2. `<repo>/.claude/skills`
3. `<repo>/.opencode/skills`
4. `<repo>/.agents/skills`
5. `skills/`（Nini 既有目录）
6. `NINI_SKILLS_EXTRA_DIRS` 指定的附加目录（逗号分隔）

同名 Skill 时，保留高优先级目录版本，低优先级版本忽略并记录告警。

### 2. Frontmatter 兼容（已实现）

- 使用标准 YAML 解析（支持数组/布尔值）
- 保留并透传扩展字段到 `metadata.frontmatter`
- 识别并标准化常见扩展字段：
  - `agents`
  - `allowed-tools` / `allowed_tools`
  - `argument-hint` / `argument_hint`
  - `user-invocable` / `user_invocable`
  - `disable-model-invocation` / `disable_model_invocation`

### 3. 编辑保真（已实现）

Web 编辑 Markdown Skill 时：

- 仅覆盖 `name`、`description`、`category`、正文
- 未识别 frontmatter 字段全部保留（不会被覆盖丢失）

### 4. 安全边界（已实现）

技能管理 API 对文件路径做允许目录校验，仅允许在已配置的 skills 根目录集合内读写。

## 配置项

- `NINI_SKILLS_AUTO_DISCOVER_COMPAT_DIRS`：是否自动发现 `.codex/.claude/.opencode/.agents`（默认 false）
- `NINI_SKILLS_DIR_PATH`：Nini 主 skills 目录（默认 `skills/`）
- `NINI_SKILLS_EXTRA_DIRS`：额外扫描目录（逗号分隔）

## 当前限制

- Nini 将 Markdown Skills 作为“提示词技能”而非可直接执行工具。
- `agents/openai.yaml` 当前仅做解析与元数据展示，不直接驱动 Nini 工具权限模型。
- Cursor/Windsurf/Gemini/Copilot 的“仓库指令文件”尚未纳入 Nini 的 Skill 扫描对象。

## 建议实践

- 新 Skill 优先使用 `SKILL.md + YAML frontmatter`，并提供 `name/description/category`。
- 若需跨 Agent 复用，建议补充：
  - `agents`（声明目标 agent）
  - `allowed-tools`（工具白名单）
  - `argument-hint`（参数提示）
- 若需 Codex 深度兼容，可在 skill 目录下增加 `agents/openai.yaml`。
