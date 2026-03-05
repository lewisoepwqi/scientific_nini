# user-profile-injection Specification

## Purpose
TBD - created by archiving change optimize-memory-prompt-system. Update Purpose after archive.
## Requirements
### Requirement: 系统提示词构建时动态填充用户研究偏好画像
系统 SHALL 在每次构建系统提示词时，从用户画像管理器读取当前会话的用户研究偏好，并将其注入 user.md 组件内容，替代静态默认文本。

#### Scenario: 用户画像存在时动态填充 user.md
- **WHEN** AgentRunner 构建 LLM 上下文，且当前 session 关联用户有已存储的研究画像
- **THEN** 系统 SHALL 调用 `profile_manager.get_profile_summary(session_id)` 获取画像摘要
- **AND** 摘要内容 SHALL 作为 user.md 组件的内容，覆盖默认"用户画像：默认未知"文本
- **AND** 用户画像内容 SHALL 通过 `component_overrides={"user.md": <画像摘要>}` 注入 PromptBuilder

#### Scenario: 用户画像为空时回退默认文本
- **WHEN** `get_profile_summary()` 返回空字符串或 None
- **THEN** 系统 SHALL 使用 user.md 的原始默认文本（"用户画像：默认未知..."）
- **AND** Agent 行为 SHALL 与当前无画像时一致

#### Scenario: 用户画像读取异常时静默回退
- **WHEN** `get_profile_summary()` 抛出异常
- **THEN** 异常 SHALL 被捕获并记录警告日志
- **AND** 系统 SHALL 回退到 user.md 静态默认文本，不中断 Agent 主循环

#### Scenario: 磁盘文件优先于动态画像注入
- **WHEN** 磁盘上存在自定义的 user.md 组件文件（operator 手动配置）
- **THEN** PromptBuilder SHALL 优先使用磁盘文件内容
- **AND** 动态画像内容 SHALL NOT 覆盖已存在的磁盘文件配置

### Requirement: 用户研究画像摘要格式适合系统提示词注入
`profile_manager.get_profile_summary()` 返回的内容 SHALL 具有适合注入系统提示词的格式和长度。

#### Scenario: 画像摘要长度受控
- **WHEN** `get_profile_summary()` 返回用户画像摘要
- **THEN** 摘要长度 SHALL 不超过 500 字（约 300 token）
- **AND** 超出限制的内容 SHALL 被截断，优先保留领域偏好、分析风格偏好等核心字段

#### Scenario: 画像摘要包含科研相关字段
- **WHEN** 用户已有存储的研究画像
- **THEN** 摘要 SHALL 包含（若有）：研究领域、常用统计方法偏好、数据集类型偏好、报告风格偏好
- **AND** 摘要 SHALL 以结构化可读格式输出（Markdown 列表或简短段落）

