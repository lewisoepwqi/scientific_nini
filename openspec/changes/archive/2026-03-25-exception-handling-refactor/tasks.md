## 1. 异常层次定义

- [x] 1.1 在 `tools/base.py` 中新增 `ToolError`、`ToolInputError`、`ToolTimeoutError`、`ToolSystemError` 异常类
- [x] 1.2 在 `tools/__init__.py` 中导出新异常类
- [x] 1.3 添加异常层次的单元测试（继承关系、isinstance 判断）

## 2. registry_core.py 统一异常调度

- [x] 2.1 重构 `FunctionToolRegistryOps.execute()` 的异常处理（约第 153 行），按 ToolInputError/ToolTimeoutError/ToolSystemError/Exception 四级捕获
- [x] 2.2 为 ToolTimeoutError 的返回结果新增 `retryable: true` 字段
- [x] 2.3 添加测试：验证各异常类型对应正确的日志级别和返回格式

## 3. 统计工具异常重构（仅含 broad catch 的文件）

- [x] 3.1 重构 `statistics/anova.py` 的 execute() 异常处理（约第 153 行 broad catch）
- [x] 3.2 重构 `statistics/regression.py` 的 execute() 异常处理（约第 107 行 broad catch）
- [x] 3.3 重构 `statistics/nonparametric.py` 的 execute() 异常处理（约第 116、219 行，2 处 broad catch）
- [x] 3.4 重构 `statistics/multiple_comparison.py` 的 execute() 异常处理

## 4. 模板工具异常重构（仅含 broad catch 的文件）

- [x] 4.1 重构 `templates/complete_anova.py` 的 execute() 异常处理（约第 171 行 broad catch）
- [x] 4.2 重构 `templates/complete_comparison.py` 的 execute() 异常处理（约第 137、148、159 行，3 处 broad catch）

## 5. Model Resolver LLM 错误分层

- [x] 5.1 在 `model_resolver.py` 的 LLM 调用层区分 `openai.RateLimitError`/`anthropic.RateLimitError`（可重试）和 `AuthenticationError`（永久失败）
- [x] 5.2 替代现有字符串匹配 `"rate limit"` 检测（约第 1216 行），使用结构化异常类型
- [x] 5.3 `httpx.TimeoutException`/`httpx.ConnectError` 走 fallback 链，401/403 立即返回用户友好错误
- [x] 5.4 添加测试：验证 429 触发 fallback、401 立即报错

## 6. 搜索 API 能力元数据

- [x] 6.1 在 `db.py` 的归档搜索函数返回结果中添加 `search_mode` 字段（基于已有的 `is_fts5_available()` 标志）
- [x] 6.2 添加测试：验证 FTS5 可用时返回 `"fts5"`，不可用时返回 `"like_fallback"`

## 7. 验证与收尾

- [x] 7.1 运行 `pytest -q` 确认全部测试通过
- [x] 7.2 运行 `black --check src tests` 确认格式
- [x] 7.3 运行 `mypy src/nini` 确认类型检查通过
