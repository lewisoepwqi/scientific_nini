## Context

代码审查发现 30+ 个工具文件中存在 `except Exception` 统一捕获模式。经验证，实际含 broad catch 的工具文件包括：统计工具 4 个（`anova.py`、`regression.py`、`nonparametric.py`、`multiple_comparison.py`；`t_test.py` 仅捕获 ValueError，`correlation.py` 无 broad catch）、模板工具 2 个（`complete_anova.py`、`complete_comparison.py`）、`registry_core.py` 1 个、以及 20+ 其他工具文件（`code_runtime.py`、`data_ops.py`、`edit_file.py` 等）。

**已实现项（不在本次范围）**：WebSocket pending futures 清理已通过 `_cancel_pending_questions()` 在 `websocket.py:642` 实现。FTS5 可用性标志已通过 `is_fts5_available()` 在 `db.py:60-72` 实现。

本变更可与 `security-hardening` 并行推进，无技术阻塞依赖。

## Goals / Non-Goals

**Goals:**
- 建立工具层分层异常体系（`ToolInputError` / `ToolTimeoutError` / `ToolSystemError`）
- 在 `registry_core.py` 中实现统一异常调度（核心枢纽，一处修改覆盖所有工具）
- 对实际含 broad catch 的统计工具（4 个文件）和模板工具（2 个文件）改用分层异常
- 为 `model_resolver.py` 的 LLM 调用区分可重试和永久失败（替代当前字符串匹配 `"rate limit"` 的方式）
- 为搜索 API 补充 `search_mode` 能力元数据

**Non-Goals:**
- 不引入外部错误追踪服务（如 Sentry）
- 不修改 `ToolResult` 的序列化格式（仅新增可选字段 `retryable`）
- 不重构 model_resolver 的 fallback 链架构
- 不修改前端错误展示逻辑
- 不重构已使用选择性捕获的工具（`t_test.py`、`correlation.py` 等）
- 不重构 20+ 其他工具文件（范围控制在核心统计/模板工具，其余留待后续迭代）

## Decisions

### D1: 异常层次设计

在 `tools/base.py` 中新增：

```python
class ToolError(Exception):
    """工具执行异常基类。"""

class ToolInputError(ToolError):
    """用户输入错误，不可重试。"""

class ToolTimeoutError(ToolError):
    """超时错误，可重试。"""

class ToolSystemError(ToolError):
    """系统故障，需记录 error 日志。"""
```

**替代方案**：使用 `ToolError(severity: Literal["input", "timeout", "system"])` 单一类 + severity 枚举。不选择的原因：独立异常类型支持 `except ToolInputError:` 语法，比 `except ToolError as e: if e.severity == ...` 更简洁；且 isinstance 检查更适合分层调度。

### D2: 统计/模板工具重构模式

仅对**实际含 broad catch 的文件**进行重构，改为：
```python
except (ValueError, KeyError) as exc:
    raise ToolInputError(str(exc)) from exc
except asyncio.TimeoutError as exc:
    raise ToolTimeoutError("统计计算超时") from exc
except ToolError:
    raise
except Exception as exc:
    raise ToolSystemError(str(exc)) from exc
```

涉及文件（统计工具，4 个实际含 broad catch）：`anova.py`、`regression.py`、`nonparametric.py`、`multiple_comparison.py`
涉及文件（模板工具，2 个实际含 broad catch）：`complete_anova.py`、`complete_comparison.py`
**不涉及**：`t_test.py`（仅 ValueError）、`correlation.py`（无 broad catch）、`correlation_analysis.py`（无 broad catch）、`regression_analysis.py`（无 broad catch）

### D3: registry_core.py 统一调度

```python
try:
    result = await tool.execute(session, **kwargs)
except ToolInputError as exc:
    logger.info("工具 %s 输入错误: %s", tool_name, exc)
    return {"success": False, "message": str(exc)}
except ToolTimeoutError as exc:
    logger.warning("工具 %s 超时: %s", tool_name, exc)
    return {"success": False, "message": str(exc), "retryable": True}
except ToolSystemError as exc:
    logger.error("工具 %s 系统错误: %s", tool_name, exc, exc_info=True)
    return {"success": False, "message": f"系统错误: {exc}"}
except Exception as exc:
    logger.error("工具 %s 未分类异常: %s", tool_name, exc, exc_info=True)
    return {"success": False, "message": f"执行失败: {exc}"}
```

保留最后的 `except Exception` 兜底——不能让未预期的异常逃逸到 Agent 循环。这意味着即使未重构的工具仍能正常工作。

### D4: model_resolver LLM 错误分层

当前 `model_resolver.py:1216` 使用字符串匹配 `"rate limit" in error_msg.lower()` 检测限流，不够可靠。改为对 provider client 的异常进行结构化分层：
- `openai.RateLimitError` / `anthropic.RateLimitError` → warning 日志 + fallback 到下一个 provider
- `openai.AuthenticationError` / `anthropic.AuthenticationError` / HTTP 401/403 → error 日志 + 立即返回用户友好错误
- `httpx.TimeoutException` / `httpx.ConnectError` → warning 日志 + fallback
- 其他 `openai.APIError` / `anthropic.APIError` → error 日志 + fallback

### D5: 搜索 API 能力元数据

FTS5 可用性标志已存在（`db.py:60-72` 的 `is_fts5_available()`）。仅需在归档搜索函数返回结果中附加：
```python
return {"results": results, "search_mode": "fts5" if is_fts5_available() else "like_fallback"}
```

## Risks / Trade-offs

- **[异常分类边界模糊]** → 某些错误难以归类（如 pandas 内存不足是 ToolSystemError，但 DataFrame 过大也可能是 ToolInputError）。Mitigation：约定——如果错误与用户输入直接相关（可通过不同输入解决）则为 InputError，否则为 SystemError。
- **[retryable 字段向前兼容]** → 新增 `retryable` 字段到 ToolResult dict 可能影响现有消费方。Mitigation：该字段为可选，所有现有代码使用 `.get()` 访问不会出错。
- **[未重构工具的兼容性]** → 本次仅重构 6 个工具文件 + registry 枢纽。其余 20+ 工具仍抛 Exception。Mitigation：D3 中 registry_core.py 的兜底 `except Exception` 确保向后兼容。
- **[model_resolver 异常类型差异]** → 不同 LLM provider SDK（openai、anthropic、httpx）的异常类名不同。Mitigation：在各 provider client 的 `chat()` 方法内部统一转换为 `ToolError` 子类或标准异常。
