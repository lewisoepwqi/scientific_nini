# Change: Add Frontend Task Visibility

## Why

当前系统虽然已实现了完整的任务化架构（后端任务模型、状态机、API、前端 Store 等），但用户在前端界面中几乎感知不到"任务"概念的存在。主要问题包括：

1. **任务创建无反馈** - 上传数据后任务在后台创建，用户无感知
2. **Header 无任务信息** - 页面顶部只显示固定标题，缺乏当前任务上下文
3. **Sidebar 无任务入口** - 导航栏只有功能模块，没有任务管理入口
4. **任务列表位置隐蔽** - 只能在统计分析页面看到任务列表
5. **图表页无任务标识** - 用户无法直观了解图表属于哪个任务

这些问题导致用户无法建立"任务"心智模型，影响了任务化架构的价值传递。

## What Changes

本提案分为三个阶段实施：

### P0 - 基础打通（1 周）

- **UploadPage 添加任务创建通知** - 上传成功后显示 Toast 通知
- **Header 添加任务状态指示** - 显示当前任务 ID 和阶段状态徽章
- **图表删除功能** - 后端添加 DELETE 端点，前端添加删除按钮
- **TaskStatusBadge 组件** - 可复用的任务状态徽章组件

### P1 - 任务管理完善（2 周）

- **Sidebar 添加"任务管理"导航项** - 新增独立任务管理入口
- **新增 TasksPage 页面** - 集中的任务列表、筛选、切换功能
- **TaskContextCard 组件** - 任务上下文信息卡片
- **TaskSwitcher 组件** - 快速任务切换下拉菜单
- **AnalysisStore 重构** - 分析结果按 taskId 隔离管理
- **完善规范校验逻辑** - 实现字体、字号、线宽、分辨率校验

### P2 - AI 闭环与高级功能（4 周）

- **ChartPage 添加任务卡片** - 显示当前任务上下文
- **AI 建议服务对接** - 与 ai_service 模块真正对接
- **采纳建议后创建 AI 数据版本** - 实现数据清洗闭环
- **补充期刊模板** - 添加 Cell、NEJM、Lancet 模板
- **前端建议执行状态展示** - 实时显示 AI 处理状态

## Impact

### Affected Specs
- `specs/frontend/` - 前端任务可视化相关能力（新建）
- `specs/task-management/` - 任务管理核心能力（已有框架待完善）

### Affected Code

#### 前端文件
- `frontend/src/pages/UploadPage.tsx` - 添加任务创建通知
- `frontend/src/components/common/Header.tsx` - 添加任务状态指示
- `frontend/src/components/common/Sidebar.tsx` - 添加任务管理导航
- `frontend/src/types/index.ts` - AppPage 类型扩展
- `frontend/src/App.tsx` - 添加 TasksPage 路由
- `frontend/src/pages/ChartPage.tsx` - 添加任务上下文卡片
- `frontend/src/components/TaskChartList.tsx` - 添加删除按钮

#### 新增前端组件
- `frontend/src/components/task/TaskStatusBadge.tsx` - 任务状态徽章
- `frontend/src/components/task/TaskContextCard.tsx` - 任务上下文卡片
- `frontend/src/components/task/TaskSwitcher.tsx` - 任务切换器
- `frontend/src/pages/TasksPage.tsx` - 任务管理页面

#### 后端文件
- `scientific_data_analysis_backend/app/api/v1/endpoints/tasks.py` - 添加图表删除端点
- `scientific_data_analysis_backend/app/services/publication_template_service.py` - 完善校验逻辑
- `scientific_data_analysis_backend/app/models/publication_templates.py` - 补充期刊模板
- `scientific_data_analysis_backend/app/services/ai_suggestion_service.py` - 对接 AI 服务

### Dependencies
- 依赖现有任务化架构（已完成的 AnalysisTask 模型、taskStore 等）
- P2 阶段依赖 ai_service 模块的可用性

## Success Criteria

### 阶段一验收（P0）
- [ ] 上传数据后，页面右上角出现"分析任务已创建（ID: xxxxxxxx）"通知
- [ ] Header 显示当前任务 ID 和阶段状态（如 `parsed`）
- [ ] 点击任务图表列表中的删除按钮，图表被移除

### 阶段二验收（P1）
- [ ] Sidebar 出现"任务管理"导航项
- [ ] 点击进入任务管理页面，显示任务列表
- [ ] 可以按阶段筛选任务
- [ ] 点击任务卡片，切换为当前任务
- [ ] 分析结果按任务隔离，切换任务后显示对应结果

### 阶段三验收（P2）
- [ ] ChartPage 顶部显示当前任务信息卡片
- [ ] 点击"生成建议"后，AI 返回清洗/统计/图表建议
- [ ] 点击"采纳"后，系统自动创建 `ai` 类型的数据版本
- [ ] 可以选择 Cell/NEJM/Lancet 期刊模板导出图表

## Related Documents
- 《项目实现现状与前端优化方案.md》
- 《综合优化建议报告.md》
