## 1. 用户透明度设置功能

- [x] 1.1 在 store types 中新增用户展示偏好类型定义
- [x] 1.2 在 store 中添加 displayPreference 状态和设置方法
- [x] 1.3 实现 localStorage 持久化逻辑（含错误处理）
- [x] 1.4 创建设置面板组件，支持简化/详细/隐藏三种模式切换
- [x] 1.5 在 ChatPanel 中集成设置入口

## 2. IntentSummaryCard 简化重构

- [x] 2.1 新增简化模式 UI：一句话概括 + 查看详情按钮
- [x] 2.2 重构详细模式 UI：折叠面板展示候选能力、推荐工具等
- [x] 2.3 术语友好化：将技术术语映射为用户友好术语
- [x] 2.4 实现置信度判断逻辑：低置信度时自动展开澄清选项
- [x] 2.5 集成 displayPreference，根据设置切换展示模式

## 3. IntentTimelineItem 优化

- [x] 3.1 简化展示内容，移除技术实现细节（如"规则版 v2"）
- [x] 3.2 优化折叠/展开交互
- [x] 3.3 确保与 IntentSummaryCard 内容差异化（确认 vs 预判）
- [x] 3.4 集成 displayPreference，隐藏模式下不展示

## 4. 知识引用标注组件

- [x] 4.1 创建 CitationMarker 组件：展示 [1], [2] 样式引用标注
- [x] 4.2 创建 CitationTooltip 组件：悬停显示来源详情
- [x] 4.3 创建 CitationList 组件：回答底部参考来源列表
- [x] 4.4 实现可信度标签映射逻辑（高可信度/一般参考）
- [x] 4.5 处理无检索结果时的空状态

## 5. MessageBubble 检索展示重构

- [x] 5.1 重构消息内容解析，提取引用标记并渲染为 CitationMarker
- [x] 5.2 在消息底部集成 CitationList 展示
- [x] 5.3 移除原有的内联检索结果展示代码
- [x] 5.4 确保 Markdown 解析与引用标注不冲突
- [x] 5.5 移动端适配优化

## 6. 样式与交互优化

- [x] 6.1 设计并实现简化模式下的卡片样式
- [x] 6.2 设计并实现详细模式下的折叠面板样式
- [x] 6.3 设计引用标注的悬停/点击交互效果
- [x] 6.4 添加过渡动画（展开/折叠、悬停提示）
- [x] 6.5 深色模式适配

## 7. 测试与验证

- [x] 7.1 验证三种展示模式（简化/详细/隐藏）切换正常
- [x] 7.2 验证 localStorage 持久化工作正常
- [x] 7.3 验证引用标注悬停显示详情正常
- [x] 7.4 验证低置信度时自动展开澄清选项
- [x] 7.5 运行前端构建和类型检查
- [x] 7.6 运行 E2E 测试（15/15 全部通过）
- [x] 7.7 修复 analysis-plan-header 测试（工作区任务面板显示分析进度）
- [x] 7.8 修复 analysis-tasks-state-machine 测试（任务状态机验证）
- [x] 7.9 修复检索卡片测试（在 CitationList 中显示 snippet）
- [x] 7.10 修复 workspace gallery URL 格式测试（统一使用 `/api/workspace/{sid}/artifacts/{path}/bundle` 格式）

## 8. 文档更新

- [x] 8.1 更新组件文档（IntentSummaryCard, IntentTimelineItem）
- [x] 8.2 在代码中添加中文注释说明新逻辑
- [x] 8.3 更新用户手册（创建 `docs/user-guide-display-preferences.md`）
