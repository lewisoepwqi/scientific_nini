## ADDED Requirements

### Requirement: Task Status Badge Component

前端 SHALL 提供 TaskStatusBadge 组件用于显示任务阶段状态。

#### Scenario: Display uploading stage
- **GIVEN** 当前任务阶段为 `uploading`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示蓝色徽章，文本为"上传中"

#### Scenario: Display parsed stage
- **GIVEN** 当前任务阶段为 `parsed`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示绿色徽章，文本为"已解析"

#### Scenario: Display profiling stage
- **GIVEN** 当前任务阶段为 `profiling`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示黄色徽章，文本为"分析中"

#### Scenario: Display suggestion_pending stage
- **GIVEN** 当前任务阶段为 `suggestion_pending`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示紫色徽章，文本为"等待建议"

#### Scenario: Display processing stage
- **GIVEN** 当前任务阶段为 `processing`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示橙色徽章，文本为"处理中"

#### Scenario: Display analysis_ready stage
- **GIVEN** 当前任务阶段为 `analysis_ready`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示青色徽章，文本为"分析就绪"

#### Scenario: Display visualization_ready stage
- **GIVEN** 当前任务阶段为 `visualization_ready`
- **WHEN** 渲染 TaskStatusBadge 组件
- **THEN** 显示翠绿色徽章，文本为"可视化就绪"

#### Scenario: Support different sizes
- **GIVEN** 需要不同尺寸的任务状态徽章
- **WHEN** 传入 size="sm" 或 size="md" 属性
- **THEN** 组件 SHALL 渲染对应大小的徽章

### Requirement: Task Creation Notification

系统 SHALL 在任务创建成功后向用户显示通知。

#### Scenario: Successful task creation notification
- **GIVEN** 用户成功上传数据集
- **WHEN** 后端返回任务创建成功响应
- **THEN** 页面右上角显示成功通知，内容为"分析任务已创建（ID: xxxxxxxx）"

#### Scenario: Failed task creation notification
- **GIVEN** 用户上传数据集成功但任务创建失败
- **WHEN** 任务创建 API 返回错误
- **THEN** 页面右上角显示警告通知，内容为"任务创建失败，但数据已上传成功"

### Requirement: Header Task Status Display

Header 组件 SHALL 在有当前任务时显示任务状态信息。

#### Scenario: Display task info in header
- **GIVEN** 存在当前任务（currentTask != null）
- **WHEN** 用户查看页面 Header
- **THEN** 显示任务状态徽章、任务 ID（前 8 位）和"切换"按钮

#### Scenario: Display default subtitle when no task
- **GIVEN** 不存在当前任务（currentTask == null）
- **WHEN** 用户查看页面 Header
- **THEN** 显示默认副标题"Scientific Data Analysis Platform"

#### Scenario: Navigate to task management
- **GIVEN** Header 显示任务信息
- **WHEN** 用户点击"切换"按钮
- **THEN** 导航到任务管理页面

### Requirement: Task Management Navigation

Sidebar SHALL 提供"任务管理"导航入口。

#### Scenario: Task management nav item exists
- **GIVEN** 用户查看 Sidebar 导航栏
- **WHEN** 导航项渲染完成
- **THEN"任务管理"导航项 SHALL 显示在"文件上传"之后

#### Scenario: Navigate to tasks page
- **GIVEN** 用户看到 Sidebar
- **WHEN** 用户点击"任务管理"导航项
- **THEN** 页面 SHALL 导航到任务管理页面

### Requirement: Tasks Page

系统 SHALL 提供集中的任务管理页面。

#### Scenario: Display task list
- **GIVEN** 用户进入任务管理页面
- **WHEN** 页面加载完成
- **THEN" SHALL 显示当前用户的所有任务列表

#### Scenario: Filter tasks by stage
- **GIVEN" 任务列表已显示
- **WHEN" 用户选择阶段筛选器（如"分析就绪"）
- **THEN" 列表 SHALL 只显示该阶段的任务

#### Scenario: Search tasks
- **GIVEN" 任务列表已显示
- **WHEN" 用户在搜索框输入任务 ID 或数据集名称
- **THEN" 列表 SHALL 只显示匹配的任务

#### Scenario: Switch current task
- **GIVEN" 任务列表中显示多个任务
- **WHEN" 用户点击某个任务卡片
- **THEN** 该任务 SHALL 成为当前任务，其他页面同步更新

#### Scenario: Highlight current task
- **GIVEN** 存在当前任务
- **WHEN** 任务列表渲染
- **THEN** 当前任务卡片 SHALL 以高亮样式显示

### Requirement: Task Context Card

系统 SHALL 提供 TaskContextCard 组件显示任务上下文信息。

#### Scenario: Display task context
- **GIVEN" 当前存在任务
- **WHEN" 在 ChartPage 或其他页面渲染 TaskContextCard
- **THEN" SHALL 显示任务 ID、阶段、数据集名称、图表数量、创建时间

#### Scenario: Switch task from context card
- **GIVEN" TaskContextCard 显示在页面上
- **WHEN" 用户点击"切换任务"按钮
- **THEN" SHALL 导航到任务管理页面

### Requirement: Task Switcher Component

系统 SHALL 提供 TaskSwitcher 组件用于快速切换任务。

#### Scenario: Display recent tasks
- **GIVEN" 用户点击 TaskSwitcher 下拉触发器
- **WHEN" 下拉菜单展开
- **THEN" SHALL 显示最近 5 个任务

#### Scenario: Highlight current task in dropdown
- **GIVEN" 下拉菜单已展开
- **WHEN" 列表渲染
- **THEN" 当前任务 SHALL 以高亮样式显示

#### Scenario: Navigate to all tasks
- **GIVEN** 下拉菜单已展开
- **WHEN" 用户点击"查看全部任务"
- **THEN" SHALL 导航到任务管理页面

### Requirement: Visualization Deletion

用户 SHALL 能够删除任务下的图表。

#### Scenario: Delete button exists
- **GIVEN" 任务图表列表显示
- **WHEN" 列表渲染完成
- **THEN" 每个图表卡片右上角 SHALL 显示删除按钮

#### Scenario: Confirm before delete
- **GIVEN" 用户点击删除按钮
- **WHEN" 删除操作触发
- **THEN** 系统 SHALL 显示确认对话框

#### Scenario: Successful deletion
- **GIVEN" 用户确认删除
- **WHEN" 后端返回删除成功响应
- **THEN** 图表 SHALL 从列表中移除，并显示成功通知

#### Scenario: Backend delete endpoint
- **GIVEN** 用户发起删除请求
- **WHEN" 请求到达后端
- **THEN** DELETE /tasks/{task_id}/visualizations/{viz_id} SHALL 删除对应图表

### Requirement: Analysis Results Isolation

分析结果 SHALL 按任务 ID 隔离存储。

#### Scenario: Results stored by taskId
- **GIVEN" 用户执行任务分析
- **WHEN" 分析结果返回
- **THEN" 结果 SHALL 存储在以任务 ID 为键的位置

#### Scenario: Load task-specific results
- **GIVEN" 用户切换到另一个任务
- **WHEN** 新任务成为当前任务
- **THEN" 页面 SHALL 显示该任务的专属分析结果

#### Scenario: Clear results on task switch
- **GIVEN" 用户当前查看任务 A 的结果
- **WHEN" 用户切换到任务 B
- **THEN" 任务 B 无结果时 SHALL 显示空状态，而非任务 A 的结果

## MODIFIED Requirements

### Requirement: AppPage Type

AppPage 类型 SHALL 支持 'tasks' 值以支持任务管理页面。

#### Scenario: Tasks page navigation
- **GIVEN" AppPage 类型已更新
- **WHEN" 导航到 'tasks' 页面
- **THEN" TypeScript 编译 SHALL 通过，无类型错误

## ADDED Requirements (P2 - AI Integration)

### Requirement: AI Suggestion Service Integration

后端 SHALL 与 ai_service 模块对接提供 AI 建议功能。

#### Scenario: Generate suggestions
- **GIVEN" 用户请求 AI 分析建议
- **WHEN" 建议生成接口被调用
- **THEN" 系统 SHALL 调用 ai_service 并返回清洗/统计/图表建议

#### Scenario: Handle AI service timeout
- **GIVEN" ai_service 响应超时
- **WHEN" 超时发生
- **THEN" 系统 SHALL 返回友好错误信息

### Requirement: AI Dataset Version Creation

采纳 AI 建议后 SHALL 自动创建 AI 类型的数据版本。

#### Scenario: Create AI version on accept
- **GIVEN" 用户点击"采纳"按钮
- **WHEN** 建议被采纳
- **THEN** 系统 SHALL 创建 `ai` 类型的 DatasetVersion

#### Scenario: Link version to task
- **GIVEN" AI 数据版本已创建
- **WHEN" 创建过程完成
- **THEN** 新版本 SHALL 自动关联到当前任务

#### Scenario: Display version in frontend
- **GIVEN" AI 数据版本创建完成
- **WHEN" 前端状态更新
- **THEN" 建议面板 SHALL 显示"已创建数据版本"状态

### Requirement: Additional Publication Templates

系统 SHALL 支持更多期刊模板。

#### Scenario: Cell template available
- **GIVEN" 用户选择导出图表
- **WHEN" 查看模板选项
- **THEN" Cell 期刊模板 SHALL 可用

#### Scenario: NEJM template available
- **GIVEN" 用户选择导出图表
- **WHEN" 查看模板选项
- **THEN" NEJM 期刊模板 SHALL 可用

#### Scenario: Lancet template available
- **GIVEN" 用户选择导出图表
- **WHEN" 查看模板选项
- **THEN" Lancet 期刊模板 SHALL 可用

#### Scenario: Template validation
- **GIVEN" 用户应用某期刊模板
- **WHEN" 图表渲染
- **THEN" 系统 SHALL 校验字体、字号、线宽、分辨率是否符合期刊要求
