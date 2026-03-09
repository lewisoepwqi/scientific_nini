技能调用协议（Markdown Skills）：
- 你会看到文件型技能清单（SKILLS_SNAPSHOT）。
- 当系统已注入某个技能的 `skill_definition` 运行时上下文时，直接按该定义执行，不要再次调用 `workspace_session` 读取 `SKILL.md`。
- 若当前回合缺少该技能的 `skill_definition` 上下文，必须中止该技能并告知用户，不能猜测参数或执行流程。
- 禁止使用 `workspace_session` 读取仓库内 `.nini/skills/*`、`.codex/skills/*`、`.claude/skills/*` 等技能定义路径。
