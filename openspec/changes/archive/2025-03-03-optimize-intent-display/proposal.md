## Why

当前 Nini 的"系统理解"和"意图理解"展示存在信息过载、术语过于技术化、打断用户阅读流等问题。IntentSummaryCard 一次性展示太多技术细节（候选能力、显式技能调用等），普通科研用户感到困惑；知识检索结果以相关性分数形式展示，对用户意义不大且影响阅读连贯性。这些问题降低了产品的易用性和用户体验，需要通过渐进式披露设计来优化。

## What Changes

- **简化 IntentSummaryCard**：默认折叠技术细节，只展示一句话概括；术语改为用户语言（如"差异分析"而非"capability"）；只在置信度低时自动展开澄清选项
- **重构知识检索展示**：采用引用标注 [1], [2] 替代内联展示；回答底部统一列出参考来源；鼠标悬停查看详情；用"高可信度/一般参考"标签替代数字分数
- **统一意图理解展示逻辑**：IntentSummaryCard 专注"预判/输入辅助"，IntentTimelineItem 专注"确认/执行反馈"，避免内容重复
- **增加用户控制选项**：提供"显示/隐藏系统理解"的设置，专业用户可展开查看完整技术细节
- **新增引用标注组件**：支持在 AI 回答中标注知识来源，增强答案可信度

## Capabilities

### New Capabilities
- `intent-display-simplification`: 意图展示简化，包括 IntentSummaryCard 重构、术语简化、默认折叠技术细节
- `retrieval-citation-view`: 检索引用展示，包括引用标注组件、来源列表、悬停详情展示
- `user-transparency-settings`: 用户透明度设置，包括显示/隐藏系统理解的偏好设置

### Modified Capabilities
- (无现有 spec 需要修改，本次为前端展示层优化，不涉及核心功能需求变更)

## Impact

**受影响的代码**:
- `web/src/components/IntentSummaryCard.tsx` - 大幅简化展示逻辑
- `web/src/components/IntentTimelineItem.tsx` - 优化内容展示
- `web/src/components/MessageBubble.tsx` - 重构检索结果展示
- `web/src/components/KnowledgeRetrievalView.tsx` - 改为引用标注模式
- `web/src/store.ts` 及相关类型定义 - 可能调整数据结构

**API 影响**: 无，纯前端展示层变更

**依赖**: 无新增依赖

**用户界面变化**:
- 输入框上方卡片更简洁
- AI 回答中出现引用标注 [1], [2]
- 回答底部显示参考来源列表
- 新增设置选项控制展示详情程度
