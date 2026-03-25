## Why

代码审查发现 30+ 个工具文件中使用 `except Exception` 统一捕获模式，将网络超时、内存不足、用户输入错误、权限错误全部归为"执行失败"。生产环境中无法区分可恢复错误与严重故障，导致：(1) 告警噪声大——真正的系统故障被淹没在用户输入错误中；(2) 无法自动重试可恢复错误；(3) FTS5 降级后搜索 API 无能力元数据反馈。

注：WebSocket pending futures 清理（`_cancel_pending_questions()`）已在 `websocket.py:642` 实现，不在本次范围内。FTS5 可用性标志追踪（`is_fts5_available()`）已在 `db.py:60-72` 实现，本次仅补充搜索 API 的 `search_mode` 响应字段。

## What Changes

- **定义工具层异常层次**：新增 `ToolInputError`（用户输入错误）、`ToolTimeoutError`（可重试超时）、`ToolSystemError`（需告警的系统故障），替代 broad `except Exception`
- **重构存在 broad catch 的统计工具异常处理**：`anova.py`、`regression.py`、`nonparametric.py`、`multiple_comparison.py`（4 个实际含 broad catch 的文件；`t_test.py` 和 `correlation.py` 已使用选择性捕获，不需修改）
- **重构存在 broad catch 的模板工具异常处理**：`complete_anova.py`、`complete_comparison.py`（2 个实际含 broad catch 的文件；`correlation_analysis.py` 和 `regression_analysis.py` 无 broad catch）
- **重构 registry_core.py 执行层**：区分工具内部错误与框架错误
- **为 model_resolver.py 添加 LLM 错误分层**：区分 429/503 可重试与 401/403 永久失败，替代当前仅靠字符串匹配 `"rate limit"` 的方式
- **补充搜索 API 能力元数据**：搜索结果返回 `search_mode` 字段标明 FTS5 或 LIKE fallback

## Capabilities

### New Capabilities

- `tool-exception-hierarchy`: 工具层分层异常体系定义和统一错误处理模式

### Modified Capabilities

- `conversation`: 搜索 API 返回 `search_mode` 能力元数据（FTS5 可用性标志已存在，仅补充 API 响应）

## Impact

- **受影响文件**：`tools/base.py`（新增异常类）、`tools/registry_core.py`、`tools/statistics/anova.py`、`tools/statistics/regression.py`、`tools/statistics/nonparametric.py`、`tools/statistics/multiple_comparison.py`、`tools/templates/complete_anova.py`、`tools/templates/complete_comparison.py`、`agent/model_resolver.py`、`memory/db.py`（搜索 API 响应）
- **不受影响文件**：`tools/statistics/t_test.py`（已用 ValueError 捕获）、`tools/statistics/correlation.py`（无 broad catch）、`api/websocket.py`（清理已实现）
- **API 兼容性**：工具返回的 `ToolResult.message` 内容可能变化（错误信息更具体），但结构不变；搜索 API 新增可选 `search_mode` 字段
- **依赖**：无新依赖
