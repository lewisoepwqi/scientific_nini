# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **消息去重架构**: 修复了消息重复显示的问题
  - WebSocket TEXT 事件新增 `message_id` 和 `operation` 元数据字段
  - 支持三种操作类型：`append`（追加）、`replace`（替换）、`complete`（完成）
  - `generate_report` 工具使用 `replace` 操作替换流式预览，避免报告内容重复显示
  - 前端实现消息缓冲区管理，支持去重和过期清理
  - 保持向后兼容，旧事件无 `message_id` 时回退到传统追加逻辑

### Added

- `WSEvent` 类型新增 `metadata.message_id` 和 `metadata.operation` 字段
- 前端新增 `MessageBuffer` 类型和缓冲区辅助函数（`updateMessageBuffer`, `getMessageBufferContent`, `completeMessageBuffer`, `cleanupMessageBuffer`, `hasMessageBuffer`）
- 消息缓冲区自动清理机制（默认5分钟过期）

### Technical Details

- 消息ID格式：`{turn_id}-{sequence}`（例如：`turn-abc123-0`）
- 操作语义：
  - `append`: 累加内容到现有消息
  - `replace`: 替换整个消息内容（用于工具生成完整内容）
  - `complete`: 标记消息完成并清理缓冲区

