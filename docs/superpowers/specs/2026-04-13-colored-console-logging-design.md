# 终端运行时日志颜色优化

## 背景

`nini start` 后的运行时日志输出全部为单色纯文本，在大量日志中难以快速定位 WARNING/ERROR。需要给控制台日志加上颜色区分，提升可读性。

## 范围

- **仅优化 uvicorn 运行时日志**（通过 `logging` 模块输出的日志）
- **不改 CLI 子命令**的 `print()` 输出（如 `nini doctor`、`nini tools list`）
- **不改文件 handler** 的输出格式（日志文件保持纯文本）

## 方案

### 依赖

在 `pyproject.toml` 中新增 `rich` 依赖，仅使用 `rich.text.Text` 和 `rich.console.Console` 做颜色化，不使用 `rich.logging.RichHandler`。

### 改动文件

仅修改 2 个文件：

1. **`src/nini/logging_config.py`** — 新增 `ColoredFormatter` 类，替换 console handler 的 formatter
2. **`pyproject.toml`** — 新增 `rich` 依赖

### ColoredFormatter 设计

自定义 `logging.Formatter` 子类，重写 `format()` 方法：

- **终端检测**：通过 `sys.stderr.isatty()` 判断，非终端时回退到纯文本格式
- **颜色映射**：
  - `ERROR` / `CRITICAL` → 红色（`bold red`）
  - `WARNING` → 黄色（`yellow`）
  - `INFO` → 绿色（`green`）
  - `DEBUG` → 灰色（`dim`）
  - `TRACE` → 更暗灰色（`dim`）
- **结构高亮**：
  - 时间戳 → 灰色（`dim`）
  - 日志级别 → 按上述颜色映射
  - 模块名 → 蓝色（`blue`）
  - 上下文括号 `[request_id=... session_id=...]` → 灰色（`dim`）
  - 消息正文 → 默认色

### Handler 分离策略

- Console handler：使用 `ColoredFormatter`（彩色）
- File handler：继续使用现有 `_build_formatter()` 返回的纯文本 Formatter

### 不改的部分

- 日志格式字符串的顺序和字段不变
- 文件 handler 输出不变
- 所有 `logger = logging.getLogger(__name__)` 调用点不变
- 上下文传播机制（`bind_log_context` 等）不变

## 验证

1. `nini start --reload` 启动后观察终端日志颜色
2. 确认日志文件内容仍为纯文本（无 ANSI 转义码）
3. 管道场景 `nini start 2>&1 | cat` 下输出无 ANSI 码
4. `pytest -q` 全部通过
