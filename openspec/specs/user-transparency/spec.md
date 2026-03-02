# Capability: User Transparency

## Purpose

赋予用户控制系统理解展示方式的能力，通过展示级别设置让用户根据自己的偏好查看系统理解信息。

## Requirements

### Requirement: 用户可设置系统理解展示级别

用户 SHALL 能够在设置中选择系统理解的展示级别（简化/详细/隐藏）。

#### Scenario: 用户切换到详细模式

- **WHEN** 用户在设置中选择"详细模式"
- **THEN** IntentSummaryCard 默认展开显示完整技术细节
- **AND** IntentTimelineItem 展示所有分析信息

#### Scenario: 用户切换到简化模式

- **WHEN** 用户在设置中选择"简化模式"
- **THEN** IntentSummaryCard 只展示一句话概括
- **AND** 技术细节默认折叠

#### Scenario: 用户选择隐藏系统理解

- **WHEN** 用户在设置中选择"隐藏系统理解"
- **THEN** 不展示 IntentSummaryCard
- **AND** 不展示 IntentTimelineItem
- **AND** 只保留知识引用标注功能

### Requirement: 展示级别设置持久化

用户的展示级别偏好 SHALL 持久化保存，下次会话自动恢复。

#### Scenario: 设置持久化到本地存储

- **WHEN** 用户更改展示级别设置
- **THEN** 设置保存到 localStorage
- **AND** 下次打开页面时自动恢复该设置

### Requirement: 默认展示级别为简化模式

新用户或首次访问用户的默认展示级别 SHALL 为简化模式。

#### Scenario: 新用户看到简化展示

- **WHEN** 新用户首次访问 Nini
- **THEN** 系统理解默认以简化模式展示
- **AND** 提供明显的入口引导用户切换到详细模式
