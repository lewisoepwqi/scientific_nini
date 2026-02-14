# workspace Specification

## Purpose
TBD - created by archiving change add-workspace-panel. Update Purpose after archive.
## Requirements
### Requirement: 独立工作区面板
系统 SHALL 提供独立的右侧工作区面板，采用三栏布局（会话列表 + 对话面板 + 工作区面板），面板宽度默认 360px，支持展开/收起切换。

#### Scenario: 用户打开工作区面板
- **WHEN** 用户点击顶栏的工作区按钮
- **THEN** 右侧面板展开，显示当前会话的文件列表

#### Scenario: 用户收起工作区面板
- **WHEN** 用户点击面板关闭按钮或再次点击顶栏按钮
- **THEN** 右侧面板收起，对话面板占据全部剩余宽度

#### Scenario: 移动端响应式
- **WHEN** 屏幕宽度小于 768px
- **THEN** 工作区面板以抽屉式覆盖方式展开，不影响对话面板布局

### Requirement: 混合模式 Tab 切换
工作区面板 SHALL 提供两个 Tab 页：「文件」和「执行历史」，用户可自由切换。

#### Scenario: 切换到文件 Tab
- **WHEN** 用户点击「文件」Tab
- **THEN** 显示文件搜索框、目录树/文件列表、产物画廊入口

#### Scenario: 切换到执行历史 Tab
- **WHEN** 用户点击「执行历史」Tab
- **THEN** 显示 Agent 代码执行的 Request/Response 历史记录

### Requirement: 文件搜索
系统 SHALL 支持在工作区面板中按文件名模糊搜索文件。

#### Scenario: 搜索文件
- **WHEN** 用户在搜索框输入关键词
- **THEN** 文件列表实时过滤，仅显示文件名包含关键词的文件

#### Scenario: 清空搜索
- **WHEN** 用户清空搜索框
- **THEN** 恢复显示全部文件

### Requirement: 文件删除
系统 SHALL 支持删除工作区中的文件（数据集、产物、笔记）。

#### Scenario: 删除文件
- **WHEN** 用户点击文件的删除按钮并确认
- **THEN** 文件从磁盘和索引中移除，文件列表实时更新

#### Scenario: 取消删除
- **WHEN** 用户点击删除按钮后取消确认
- **THEN** 文件保持不变

### Requirement: 文件重命名
系统 SHALL 支持重命名工作区中的文件。

#### Scenario: 重命名文件
- **WHEN** 用户双击文件名或点击重命名按钮
- **THEN** 文件名变为可编辑状态，用户输入新名称后按回车确认

### Requirement: 文件预览
系统 SHALL 支持在弹窗中预览工作区文件，根据文件类型提供不同的预览方式。

#### Scenario: 预览图片文件
- **WHEN** 用户点击 PNG/JPEG/SVG 文件
- **THEN** 弹窗中显示图片原图

#### Scenario: 预览文本文件
- **WHEN** 用户点击 TXT/CSV 文件
- **THEN** 弹窗中显示文件前 50 行内容，带语法高亮

#### Scenario: 预览 HTML 图表
- **WHEN** 用户点击 HTML 文件（Plotly 图表）
- **THEN** 弹窗中使用 iframe 沙箱渲染图表

#### Scenario: 预览 PDF 文件
- **WHEN** 用户点击 PDF 文件
- **THEN** 弹窗中渲染 PDF 内容，支持翻页和缩放

#### Scenario: 预览 Markdown 文件
- **WHEN** 用户点击 MD 文件
- **THEN** 弹窗中渲染 Markdown 为富文本，支持 GFM 语法、代码块高亮和表格

### Requirement: 文件类型图标
系统 SHALL 为不同类型的文件显示对应的图标，便于用户快速识别。

#### Scenario: 显示文件图标
- **WHEN** 文件列表渲染时
- **THEN** CSV/Excel 显示表格图标，PNG/JPEG 显示图片图标，MD/TXT 显示文本图标，PDF 显示 PDF 图标，其他显示通用文件图标

### Requirement: 目录树导航
系统 SHALL 支持树状目录结构展示文件，默认按类型分为三个目录（数据集/产物/笔记），并支持 Agent 自定义文件夹。

#### Scenario: 展开目录
- **WHEN** 用户点击文件夹图标
- **THEN** 展开显示该目录下的文件列表，显示文件数量

#### Scenario: 收起目录
- **WHEN** 用户再次点击已展开的文件夹
- **THEN** 收起该目录

### Requirement: 代码执行面板
系统 SHALL 在「执行历史」Tab 中显示 Agent 的代码执行记录，包含代码输入（Request）和执行输出（Response）。执行历史 SHALL 持久化到磁盘，会话恢复时自动加载。

#### Scenario: 查看执行历史
- **WHEN** 用户切换到「执行历史」Tab
- **THEN** 按时间倒序显示所有代码执行记录，每条记录包含代码块和输出结果

#### Scenario: 复制代码
- **WHEN** 用户点击代码块的复制按钮
- **THEN** 代码内容复制到剪贴板

#### Scenario: 执行历史持久化
- **WHEN** Agent 执行代码完成
- **THEN** 执行记录（代码、输出、状态、时间戳）持久化到 `workspace/executions/` 目录

#### Scenario: 会话恢复时加载执行历史
- **WHEN** 用户切换到已有会话
- **THEN** 自动从磁盘加载该会话的历史执行记录，显示在执行历史 Tab 中

### Requirement: 产物画廊
系统 SHALL 提供产物画廊视图，以网格缩略图方式展示图表和报告产物，支持按类型筛选和批量下载。

#### Scenario: 查看产物画廊
- **WHEN** 用户在文件 Tab 中切换到画廊视图
- **THEN** 以网格缩略图方式显示所有产物

#### Scenario: 筛选产物类型
- **WHEN** 用户选择筛选条件（图表/报告/数据快照）
- **THEN** 仅显示对应类型的产物

#### Scenario: 批量选择产物
- **WHEN** 用户勾选多个产物的复选框
- **THEN** 底部显示已选数量和"批量下载"按钮

#### Scenario: 批量下载为 ZIP
- **WHEN** 用户选择多个产物后点击"批量下载"按钮
- **THEN** 后端将选中文件打包为 ZIP 文件，浏览器自动下载

### Requirement: 文件版本控制
系统 SHALL 为产物文件维护版本历史，同一产物多次生成时保留历史版本。

#### Scenario: 自动创建版本
- **WHEN** Agent 重新生成同名产物
- **THEN** 旧版本保留在版本历史中，新版本成为当前版本

#### Scenario: 查看版本历史
- **WHEN** 用户在文件详情中查看版本历史
- **THEN** 显示所有历史版本列表，可下载任意版本

#### Scenario: 版本数量上限
- **WHEN** 版本数量超过上限（默认 10）
- **THEN** 自动清理最旧的版本

### Requirement: Agent 自定义文件夹
系统 SHALL 允许 Agent 通过 skill 调用创建自定义文件夹并组织文件。

#### Scenario: Agent 创建文件夹
- **WHEN** Agent 调用 `organize_workspace` skill 指定创建文件夹
- **THEN** 工作区中创建新文件夹，文件移动到指定位置

### Requirement: WebSocket 实时更新
系统 SHALL 在文件变更（新增/删除/重命名/产物生成）时通过 WebSocket 推送 `workspace_update` 事件，前端自动刷新文件列表。

#### Scenario: 产物生成后实时更新
- **WHEN** Agent 生成新产物
- **THEN** 前端工作区面板自动显示新文件，无需手动刷新

### Requirement: Excel 多工作表加载模式
系统 SHALL 在 `load_dataset` 中支持多工作表读取模式，以便模型根据分析任务选择按 sheet 分析或跨 sheet 合并分析。

#### Scenario: 加载指定工作表
- **WHEN** 用户或模型调用 `load_dataset`，并指定 `sheet_mode=single` 与 `sheet_name`
- **THEN** 系统仅加载目标 sheet，并在会话中创建对应数据集

#### Scenario: 加载全部工作表并分别分析
- **WHEN** 调用 `load_dataset`，并指定 `sheet_mode=all` 且 `combine_sheets=false`
- **THEN** 系统加载全部 sheet，并在会话中为每个 sheet 创建独立数据集

#### Scenario: 加载全部工作表并合并分析
- **WHEN** 调用 `load_dataset`，并指定 `sheet_mode=all` 且 `combine_sheets=true`
- **THEN** 系统将全部 sheet 合并为一个数据集
- **AND** 可选添加来源列用于标记原始 sheet

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

