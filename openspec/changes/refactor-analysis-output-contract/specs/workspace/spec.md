## ADDED Requirements
### Requirement: Markdown 资源打包下载
系统 SHALL 在下载 Markdown 产物时自动检测会话内图片引用，并在存在引用时提供“Markdown + 资源文件”打包下载。

#### Scenario: Markdown 含会话图片引用
- **WHEN** 用户下载包含 `/api/artifacts/{session_id}/...` 图片链接的 Markdown
- **THEN** 系统返回 ZIP 文件
- **AND** ZIP 内包含改写为相对路径的 Markdown 与 `images/` 目录资源

#### Scenario: Markdown 不含图片引用
- **WHEN** 用户下载不包含图片引用的 Markdown
- **THEN** 系统返回原始 Markdown 文件

### Requirement: PDF 预览入口一致性
系统 SHALL 保证工作区不同预览入口（侧栏预览与弹窗预览）对 PDF 文件提供一致的内嵌预览能力。

#### Scenario: 从侧栏打开 PDF
- **WHEN** 用户在工作区侧栏打开 PDF 文件
- **THEN** 系统以内嵌方式渲染 PDF

#### Scenario: 从弹窗打开 PDF
- **WHEN** 用户在弹窗预览中打开同一 PDF 文件
- **THEN** 系统采用与侧栏一致的内嵌预览行为
- **AND** 保留下载按钮作为补充动作

### Requirement: 下载入口策略统一
系统 SHALL 在文件列表、消息产物卡片、预览面板等下载入口中统一使用 Markdown 打包下载策略，避免入口行为不一致。

#### Scenario: 多入口下载同一 Markdown
- **WHEN** 用户分别通过列表下载与消息卡片下载同一 Markdown 报告
- **THEN** 两个入口下载结果一致
- **AND** 均符合 Markdown 资源打包规则
