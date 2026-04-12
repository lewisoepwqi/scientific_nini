"""统一日志配置与上下文传播。"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar, Token
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

_LOG_CONTEXT: ContextVar[dict[str, str]] = ContextVar("nini_log_context", default={})
_CONTEXT_FIELDS = (
    "request_id",
    "connection_id",
    "session_id",
)
_MANAGED_HANDLER_ATTR = "_nini_managed_handler"
_ORIGINAL_RECORD_FACTORY = logging.getLogRecordFactory()
_RECORD_FACTORY_INSTALLED = False


def _normalize_logger_name(name: str) -> str:
    """归一化日志来源名称，避免第三方 logger 名称造成误解。"""
    if name == "uvicorn.error":
        return "uvicorn"
    return name


def _install_record_factory() -> None:
    """安装带上下文字段的 LogRecord 工厂。"""
    global _RECORD_FACTORY_INSTALLED

    if _RECORD_FACTORY_INSTALLED:
        return

    def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = _ORIGINAL_RECORD_FACTORY(*args, **kwargs)
        context = _LOG_CONTEXT.get()
        setattr(record, "logger_name", _normalize_logger_name(record.name))
        for field in _CONTEXT_FIELDS:
            value = context.get(field)
            setattr(record, field, value if value else "-")
        return record

    logging.setLogRecordFactory(_record_factory)
    _RECORD_FACTORY_INSTALLED = True


def resolve_log_level(level: str | int | None, default: str | int = "INFO") -> int:
    """解析日志级别，兼容 stdlib logging 与 Uvicorn trace。"""
    if isinstance(level, int):
        return level

    raw = str(level or default).strip().upper()
    if raw == "TRACE":
        return TRACE_LEVEL

    resolved = logging.getLevelName(raw)
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def bind_log_context(**values: str | None) -> Token[dict[str, str]]:
    """绑定日志上下文，返回可用于恢复的 token。"""
    current = dict(_LOG_CONTEXT.get())
    for key, value in values.items():
        if value is None:
            current.pop(key, None)
            continue
        normalized = str(value).strip()
        if normalized:
            current[key] = normalized
        else:
            current.pop(key, None)
    return _LOG_CONTEXT.set(current)


def reset_log_context(token: Token[dict[str, str]]) -> None:
    """恢复先前的日志上下文。"""
    _LOG_CONTEXT.reset(token)


def clear_log_context(*keys: str) -> None:
    """清理全部或指定日志上下文字段。"""
    if not keys:
        _LOG_CONTEXT.set({})
        return

    current = dict(_LOG_CONTEXT.get())
    for key in keys:
        current.pop(key, None)
    _LOG_CONTEXT.set(current)


def _remove_managed_handlers(logger: logging.Logger) -> None:
    """移除当前 logger 上由 Nini 管理的 handler。"""
    for handler in list(logger.handlers):
        if not getattr(handler, _MANAGED_HANDLER_ATTR, False):
            continue
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            continue


def _build_context_tag(record: logging.LogRecord) -> str:
    """根据日志记录的上下文字段动态构建标签，省略值为 '-' 的字段。"""
    parts: list[str] = []
    for field in _CONTEXT_FIELDS:
        value = getattr(record, field, "-")
        if value and value != "-":
            parts.append(f"{field}={value}")
    if not parts:
        return ""
    return f"[{' '.join(parts)}] "


class _ContextFormatter(logging.Formatter):
    """动态上下文格式化基类，省略空上下文字段。"""

    # 子类共用同一模板，上下文部分由 format() 动态插入。
    _BASE_FMT = "%(asctime)s %(levelname)s %(logger_name)s %(message)s"

    def __init__(self) -> None:
        super().__init__(self._BASE_FMT)

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        context_tag = _build_context_tag(record)
        if not context_tag:
            return msg
        # 在模块名和消息之间插入上下文标签。
        logger_name = getattr(record, "logger_name", record.name)
        # 基类 format 后的格式: "asctime LEVELNAME module message"
        # 找到模块名后、消息前的位置插入。
        name_end = msg.find(logger_name) + len(logger_name) if logger_name else 0
        return msg[:name_end] + " " + context_tag + msg[name_end:].lstrip()


def _build_formatter() -> logging.Formatter:
    """构建统一日志格式（纯文本，用于文件 handler）。"""
    return _ContextFormatter()


# ANSI 终端颜色标记，供 ColoredFormatter 使用。
_LEVEL_STYLES: dict[int, str] = {
    logging.CRITICAL: "bold red",
    logging.ERROR: "bold red",
    logging.WARNING: "yellow",
    logging.INFO: "green",
    logging.DEBUG: "dim",
    TRACE_LEVEL: "dim",
}


class ColoredFormatter(_ContextFormatter):
    """控制台日志着色 Formatter，仅对终端（tty）输出 ANSI 颜色。"""

    def __init__(self) -> None:
        super().__init__()
        from rich.console import Console

        self._console = Console(file=sys.stderr, force_terminal=True)
        self._is_tty = sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        # 非终端时回退到纯文本。
        if not self._is_tty:
            return super().format(record)

        from rich.text import Text

        # 先通过基类获取完整纯文本（含动态上下文）。
        text = super().format(record)
        level_style = _LEVEL_STYLES.get(record.levelno, "")

        # 拆分结构化部分：时间戳 | 级别 | 模块名 | 上下文 | 消息
        asctime = record.asctime  # type: ignore[attr-defined]
        ts_end = text.find(asctime) + len(asctime) if asctime else 0
        ts_part = text[:ts_end]
        remainder = text[ts_end:].lstrip()

        level_name = record.levelname
        level_end = remainder.find(level_name) + len(level_name) if level_name else 0
        level_part = remainder[:level_end]
        remainder = remainder[level_end:].lstrip()

        logger_name = getattr(record, "logger_name", record.name)
        name_end = remainder.find(logger_name) + len(logger_name) if logger_name else 0
        name_part = remainder[:name_end]
        remainder = remainder[name_end:].lstrip()

        # remainder 现在是 [context] message 或直接 message
        context_part = ""
        if remainder.startswith("["):
            bracket_end = remainder.find("] ")
            if bracket_end != -1:
                context_part = remainder[: bracket_end + 1]
                remainder = remainder[bracket_end + 1 :].lstrip()

        # 组装带颜色的 Text 对象
        rich_text = Text()
        if ts_part:
            rich_text.append(ts_part, style="dim")
            rich_text.append(" ")
        rich_text.append(level_part, style=level_style or "")
        rich_text.append(" ")
        rich_text.append(name_part, style="blue")
        rich_text.append(" ")
        if context_part:
            rich_text.append(context_part, style="dim")
            rich_text.append(" ")
        rich_text.append(remainder)

        with self._console.capture() as capture:
            self._console.print(rich_text, end="", highlight=False)
        return capture.get()


def _build_colored_formatter() -> ColoredFormatter:
    """构建带颜色的控制台日志格式。"""
    return ColoredFormatter()


def _mark_managed(handler: logging.Handler) -> logging.Handler:
    """给 handler 打上 Nini 管理标记。"""
    setattr(handler, _MANAGED_HANDLER_ATTR, True)
    return handler


def setup_logging(
    *,
    log_level: str | int | None = None,
    log_dir: Path | None = None,
    file_name: str | None = None,
    rotate_when: str | None = None,
    rotate_interval: int | None = None,
    backup_count: int | None = None,
) -> Path | None:
    """初始化统一日志配置，并返回日志文件路径。"""
    from nini.config import settings

    _install_record_factory()

    resolved_level = resolve_log_level(log_level, default=settings.effective_log_level)
    target_dir = log_dir or settings.logs_dir
    target_name = file_name or settings.log_file_name
    when = rotate_when or settings.log_rotate_when
    interval = rotate_interval or settings.log_rotate_interval
    retention = backup_count if backup_count is not None else settings.log_backup_count
    formatter = _build_formatter()

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    _remove_managed_handlers(root_logger)

    console_handler = _mark_managed(logging.StreamHandler())
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(_build_colored_formatter())
    root_logger.addHandler(console_handler)

    log_path: Path | None = target_dir / target_name
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        resolved_log_path = log_path
        if resolved_log_path is None:
            raise ValueError("日志文件路径为空")
        file_handler = _mark_managed(
            TimedRotatingFileHandler(
                resolved_log_path,
                when=when,
                interval=interval,
                backupCount=retention,
                encoding="utf-8",
                utc=True,
            )
        )
        file_handler.setLevel(resolved_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as exc:
        logging.getLogger(__name__).warning("日志文件初始化失败，已回退为仅控制台输出: %s", exc)
        log_path = None

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(resolved_level)
        uvicorn_logger.propagate = True

    # httpx/httpcore 在 INFO 级别会打印每一条外部请求，启动探测和工具调用时噪声较大。
    # 仅在 DEBUG 模式下保留逐请求日志，其他级别统一抬到 WARNING。
    third_party_http_level = resolved_level if resolved_level <= logging.DEBUG else logging.WARNING
    for logger_name in ("httpx", "httpcore"):
        http_logger = logging.getLogger(logger_name)
        http_logger.handlers.clear()
        http_logger.setLevel(third_party_http_level)
        http_logger.propagate = True

    return log_path
