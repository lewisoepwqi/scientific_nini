# Change: 重构分析输出契约与报告交付链路

## Why
当前分析链路存在跨层协议不一致：图表消息契约在不同技能间不统一、报告混入观测信息、Markdown 下载缺少资源打包、预览行为在不同入口不一致。这些问题已经影响核心分析功能的可靠性与可解释性。

## What Changes
- 建立统一的图表输出契约（面向消息流、会话持久化与前端渲染），并提供兼容适配层处理历史格式。
- 重构报告生成策略：业务报告与系统观测信息分层，关键发现基于结构化执行记录，不再从噪声文本拼接。
- 建立图表预览去重规则：同一图表仅展示一个主预览格式，其余格式进入下载清单。
- 统一 Markdown 导出策略：含图片引用的 Markdown 默认提供“文档+资源”打包下载。
- 统一 PDF 预览策略：工作区侧栏与弹窗使用一致的 PDF 内嵌预览行为。
- 强化会话读取一致性：消息加载时支持大型 payload 解引用，避免会话重开后图表失效。
- 增加回归测试矩阵，覆盖图表渲染、报告内容、导出打包、预览一致性。

## Impact
- Affected specs:
  - `chart-rendering`
  - `conversation`
  - `skills`
  - `workspace`
- Affected code:
  - `src/nini/skills/templates/*`
  - `src/nini/skills/report.py`
  - `src/nini/agent/runner.py`
  - `src/nini/agent/session.py`
  - `src/nini/api/routes.py`
  - `src/nini/memory/conversation.py`
  - `web/src/components/ChartViewer.tsx`
  - `web/src/components/FilePreviewPane.tsx`
  - `web/src/components/FilePreviewModal.tsx`
  - `web/src/components/ArtifactDownload.tsx`
  - `web/src/components/FileListItem.tsx`
- Breaking/compatibility:
  - 对现有历史会话提供兼容读取，不要求用户迁移旧数据。
  - 图表消息契约升级为统一格式，保留旧格式兼容窗口。
