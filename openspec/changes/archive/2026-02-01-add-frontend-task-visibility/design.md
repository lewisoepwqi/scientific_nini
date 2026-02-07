# Design: Add Frontend Task Visibility

## Context

当前项目已实现完整的任务化架构后端（AnalysisTask 模型、7 阶段状态机、任务 API、任务 Store），但前端缺乏任务概念的可视化呈现。用户在上传数据、查看图表、进行分析时无法感知"任务"的存在，导致任务化架构的价值无法传达给用户。

## Goals / Non-Goals

### Goals
- 让用户在上传数据后立刻感知任务已创建
- 在全局 Header 显示当前任务上下文
- 提供集中的任务管理页面
- 支持图表删除功能
- 实现分析结果按任务隔离

### Non-Goals
- 重构后端任务模型（已完成）
- 修改任务状态机逻辑（已完成）
- 支持任务归档/恢复（P2 可选）
- 团队权限管理（超出当前范围）

## Technical Decisions

### Decision 1: TaskStatusBadge 组件设计
**Decision**: 创建一个独立的 TaskStatusBadge 组件，支持两种尺寸和 7 种阶段状态颜色映射。

**Rationale**:
- 任务状态需要在 Header、任务卡片、下拉菜单多处使用，独立组件确保一致性
- Tailwind CSS 的颜色类（bg-blue-100, text-blue-700 等）提供良好的视觉层次
- Props 设计：`stage: TaskStage`, `size?: 'sm' | 'md'`

**Alternatives considered**:
- 在每个使用处内联实现 - 重复代码，维护困难
- 使用图标替代颜色徽章 - 颜色更直观传达状态语义

### Decision 2: State Management for Task-Isolated Results
**Decision**: 重构 AnalysisStore，使用嵌套对象结构按 taskId 存储分析结果。

**Current State**:
```typescript
interface AnalysisState {
  results: AnalysisResult[]; // 全局存储
}
```

**Proposed State**:
```typescript
interface AnalysisState {
  resultsByTask: Record<string, AnalysisResult[]>; // 按 taskId 分组
  currentTaskId: string | null;
}
```

**Rationale**:
- 避免切换任务时结果混淆
- 保留历史任务的缓存结果，切换回来时无需重新加载
- 使用 Record 类型便于 TypeScript 类型推断

**Migration Strategy**:
- 保持向后兼容，旧的全局 results 可保留作为 fallback
- 新数据写入 resultsByTask
- 读取时优先从 resultsByTask[currentTaskId] 获取

### Decision 3: Notification System Integration
**Decision**: 复用现有的 `useUIStore` 中的 `addNotification` 方法，而非创建新的通知系统。

**Rationale**:
- 项目已有 UI Store 和通知系统，避免重复造轮子
- 统一的 Toast 通知样式保持一致性
- 减少新增依赖和学习成本

### Decision 4: Task Deletion Strategy
**Decision**: 后端实现硬删除（hard delete），前端添加确认对话框。

**Rationale**:
- 图表数据可通过重新生成恢复，硬删除简化逻辑
- 确认对话框防止误操作
- 软删除会增加数据表复杂性和查询成本

**Implementation**:
- 后端：`DELETE /tasks/{task_id}/visualizations/{viz_id}`
- 前端：点击删除 → 确认对话框 → 调用 API → 本地状态过滤

### Decision 5: Tasks Page Layout
**Decision**: 使用网格布局（grid-cols-1 md:grid-cols-2 lg:grid-cols-3）展示任务卡片。

**Rationale**:
- 卡片式布局直观展示任务关键信息
- 响应式网格适配不同屏幕尺寸
- 预留扩展空间（如缩略图预览）

**Card Content**:
- 任务 ID（前 8 位）
- 状态徽章
- 数据集名称
- 图表数量
- 创建时间
- 操作按钮（切换、删除）

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| AnalysisStore 重构影响现有功能 | 高 | 1. 保留旧数据结构作为 fallback<br>2. 逐步迁移读取逻辑<br>3. 增加单元测试覆盖 |
| Header 高度变化影响布局 | 低 | TaskStatusBadge 使用紧凑设计（size="sm"），避免增加 Header 高度 |
| 任务列表加载性能 | 中 | 1. 后端分页 API（如需要）<br>2. 前端虚拟滚动（任务数 >50） |
| 状态同步延迟 | 低 | 使用 Zustand 的 subscribe 机制，确保跨组件同步 |

## Migration Plan

### Phase 1 (P0) - No Breaking Changes
- 所有新增功能均为新增 API/组件，不影响现有流程
- 图表删除功能为新增端点，可选使用

### Phase 2 (P1) - AnalysisStore Refactoring
1. **准备阶段**: 添加新的 `resultsByTask` 字段，保持 `results` 字段
2. **写入迁移**: 新分析结果同时写入 `results` 和 `resultsByTask`
3. **读取迁移**: 组件逐步改为从 `resultsByTask` 读取
4. **清理阶段**: 确认无组件使用旧 `results` 后移除

### Phase 3 (P2) - AI Integration
- 新增功能，无迁移风险
- AI 服务可选，不影响核心功能

## Component API Reference

### TaskStatusBadge
```typescript
interface TaskStatusBadgeProps {
  stage: TaskStage; // 'uploading' | 'parsed' | 'profiling' | 'suggestion_pending' | 'processing' | 'analysis_ready' | 'visualization_ready'
  size?: 'sm' | 'md';
  className?: string;
}

// Usage
<TaskStatusBadge stage="analysis_ready" size="sm" />
```

### TaskContextCard
```typescript
interface TaskContextCardProps {
  task: Task;
  datasetName?: string;
  chartCount?: number;
  onSwitchTask?: () => void;
  className?: string;
}

// Usage
<TaskContextCard
  task={currentTask}
  datasetName={dataset?.filename}
  chartCount={taskCharts[currentTask.id]?.length || 0}
  onSwitchTask={() => setCurrentPage('tasks')}
/>
```

### TaskSwitcher
```typescript
interface TaskSwitcherProps {
  currentTask: Task | null;
  tasks: Task[];
  onSelect: (task: Task) => void;
  onViewAll?: () => void;
  maxRecent?: number; // default: 5
}

// Usage
<TaskSwitcher
  currentTask={currentTask}
  tasks={tasks}
  onSelect={setCurrentTask}
  onViewAll={() => setCurrentPage('tasks')}
/>
```

## File Structure

```
frontend/src/
├── components/
│   ├── task/                          # 新增目录
│   │   ├── TaskStatusBadge.tsx        # 任务状态徽章
│   │   ├── TaskContextCard.tsx        # 任务上下文卡片
│   │   ├── TaskSwitcher.tsx           # 任务切换器
│   │   └── index.ts                   # 统一导出
│   ├── common/
│   │   ├── Header.tsx                 # 修改：添加任务状态
│   │   └── Sidebar.tsx                # 修改：添加导航项
│   └── TaskChartList.tsx              # 修改：添加删除按钮
├── pages/
│   ├── TasksPage.tsx                  # 新增：任务管理页面
│   ├── UploadPage.tsx                 # 修改：添加通知
│   └── ChartPage.tsx                  # 修改：添加任务卡片
├── store/
│   └── analysisStore.ts               # 修改：按 taskId 隔离
└── types/
    └── index.ts                       # 修改：AppPage 类型
```

## Open Questions

1. **任务删除权限**: 是否需要限制只有任务创建者才能删除？（当前设计：是）
2. **任务数量上限**: 是否需要限制用户的任务数量？（当前设计：暂不限制）
3. **AI 服务超时**: 建议生成超时时间设置为多少？（建议：30 秒）
4. **结果缓存策略**: AnalysisStore 中的结果是否需要持久化到 localStorage？（建议：P1 不做，P2 考虑）
