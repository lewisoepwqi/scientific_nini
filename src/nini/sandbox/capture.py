"""沙箱执行输出捕获。"""

from __future__ import annotations

from contextlib import contextmanager
import io
import sys
from typing import Generator


@contextmanager
def capture_stdio() -> Generator[tuple[io.StringIO, io.StringIO], None, None]:
    """捕获 stdout / stderr，供沙箱回传日志。"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    out = io.StringIO()
    err = io.StringIO()
    try:
        sys.stdout = out
        sys.stderr = err
        yield out, err
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
