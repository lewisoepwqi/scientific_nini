"""统一日志配置与上下文传播。"""

from __future__ import annotations

import logging
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
    "turn_id",
    "tool_call_id",
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


def _build_formatter() -> logging.Formatter:
    """构建统一日志格式。"""
    return logging.Formatter(
        (
            "%(asctime)s %(levelname)s %(logger_name)s "
            "[request_id=%(request_id)s connection_id=%(connection_id)s "
            "session_id=%(session_id)s turn_id=%(turn_id)s "
            "tool_call_id=%(tool_call_id)s] %(message)s"
        )
    )


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
    console_handler.setFormatter(formatter)
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
