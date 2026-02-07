"""进程隔离代码执行器。"""

from __future__ import annotations

import asyncio
import builtins as py_builtins
import multiprocessing
from multiprocessing.connection import Connection
import os
import pickle
import traceback
from typing import Any

import pandas as pd

from nini.config import settings
from nini.sandbox.capture import capture_stdio
from nini.sandbox.policy import validate_code

try:
    import resource  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Windows 等平台可能不存在
    resource = None  # type: ignore[assignment]


SAFE_BUILTINS: dict[str, Any] = {
    "__import__": py_builtins.__import__,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
}


def _safe_copy_datasets(datasets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    copied: dict[str, pd.DataFrame] = {}
    for name, df in datasets.items():
        copied[name] = df.copy(deep=True)
    return copied


def _set_resource_limits(timeout_seconds: int, max_memory_mb: int) -> None:
    """对子进程施加资源限制。"""
    if resource is None:
        return
    try:
        if hasattr(resource, "RLIMIT_CPU"):
            cpu_limit = max(1, int(timeout_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
        if hasattr(resource, "RLIMIT_AS") and int(max_memory_mb) >= 1024:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux ru_maxrss 单位是 KB，macOS 是 Byte；统一转换为 MB
            usage_mb = usage / 1024 if usage > 10_000 else usage / (1024 * 1024)
            # 给运行时和序列化留出缓冲，避免进程尚未执行业务代码就触发 OOM
            # 经验上低于 1GB 在科学计算栈中容易误杀，因此设置下限为 1024MB。
            effective_limit_mb = max(int(max_memory_mb), 1024, int(usage_mb) + 512)
            mem_limit = effective_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
    except Exception:
        # 某些环境不允许设置 rlimit，降级为仅使用超时终止
        pass


def _try_pickleable(value: Any) -> Any:
    """确保结果可跨进程传输。"""
    try:
        pickle.dumps(value)
        return value
    except Exception:
        return repr(value)


def _build_exec_globals(datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    globals_dict: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "datasets": datasets,
    }
    return globals_dict


def _sandbox_worker(
    conn: Connection,
    code: str,
    datasets: dict[str, pd.DataFrame],
    working_dir: str,
    timeout_seconds: int,
    max_memory_mb: int,
    dataset_name: str | None,
    persist_df: bool,
) -> None:
    """子进程执行入口。"""
    stdout_text = ""
    stderr_text = ""

    try:
        _set_resource_limits(timeout_seconds, max_memory_mb)
        os.chdir(working_dir)

        local_datasets = _safe_copy_datasets(datasets)
        exec_globals = _build_exec_globals(local_datasets)
        exec_locals: dict[str, Any] = {}

        if dataset_name:
            if dataset_name not in local_datasets:
                raise ValueError(f"数据集 '{dataset_name}' 不存在")
            exec_locals["df"] = local_datasets[dataset_name].copy(deep=True)

        with capture_stdio() as (stdout_buf, stderr_buf):
            compiled = compile(code, "<sandbox>", "exec")
            exec(compiled, exec_globals, exec_locals)
            stdout_text = stdout_buf.getvalue()
            stderr_text = stderr_buf.getvalue()

        result_obj = exec_locals.get("result", exec_globals.get("result"))
        output_df = exec_locals.get("output_df")

        if persist_df and dataset_name and isinstance(exec_locals.get("df"), pd.DataFrame):
            local_datasets[dataset_name] = exec_locals["df"]

        if isinstance(output_df, pd.DataFrame):
            result_obj = output_df

        payload = {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "result": _try_pickleable(result_obj),
            "datasets": local_datasets if persist_df else {},
        }
        conn.send(payload)
    except Exception as exc:
        tb = traceback.format_exc()
        conn.send(
            {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": str(exc),
                "traceback": tb,
            }
        )
    finally:
        conn.close()


class SandboxExecutor:
    """沙箱执行器（进程隔离 + 策略校验 + 超时控制）。"""

    def __init__(self, timeout_seconds: int | None = None, max_memory_mb: int | None = None):
        self.timeout_seconds = timeout_seconds or settings.sandbox_timeout
        self.max_memory_mb = max_memory_mb or settings.sandbox_max_memory_mb

    async def execute(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None = None,
        persist_df: bool = False,
    ) -> dict[str, Any]:
        """异步执行入口。"""
        return await asyncio.to_thread(
            self._execute_sync,
            code=code,
            session_id=session_id,
            datasets=datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )

    def _execute_sync(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None,
        persist_df: bool,
    ) -> dict[str, Any]:
        validate_code(code)

        working_dir = settings.sessions_dir / session_id / "sandbox_tmp"
        working_dir.mkdir(parents=True, exist_ok=True)

        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)
        process = ctx.Process(
            target=_sandbox_worker,
            args=(
                child_conn,
                code,
                datasets,
                str(working_dir),
                self.timeout_seconds,
                self.max_memory_mb,
                dataset_name,
                persist_df,
            ),
            daemon=True,
        )

        process.start()
        child_conn.close()
        process.join(self.timeout_seconds)

        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            parent_conn.close()
            return {
                "success": False,
                "error": f"代码执行超时（>{self.timeout_seconds}s）",
                "stdout": "",
                "stderr": "",
            }

        if not parent_conn.poll():
            parent_conn.close()
            return {
                "success": False,
                "error": "沙箱进程异常退出，未返回结果",
                "stdout": "",
                "stderr": "",
            }

        payload = parent_conn.recv()
        parent_conn.close()
        return payload


sandbox_executor = SandboxExecutor()
