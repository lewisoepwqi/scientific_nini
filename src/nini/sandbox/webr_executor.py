"""WebR（WebAssembly R）沙箱执行器。

通过 `webr` Python 包在进程内运行 R 代码，无需本地安装 R。
首次使用时会自动下载 ~80MB 的 WebAssembly R 运行时。

局限性：
- 不支持 Bioconductor 包（需原生 R）
- 部分 CRAN 包可能尚未编译为 WASM 版本
- 执行速度比原生 R 慢约 2-5x
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from nini.config import settings
from nini.sandbox.r_policy import RSandboxPolicyError, validate_r_code

logger = logging.getLogger(__name__)

# 延迟检测：避免在 import 时触发 webr 运行时下载
_webr_import_error: Exception | None = None
_WEBR_CHECKED = False
_WEBR_AVAILABLE = False


def _check_webr() -> bool:
    """检测 webr 包是否可导入（仅执行一次）。"""
    global _WEBR_CHECKED, _WEBR_AVAILABLE, _webr_import_error
    if _WEBR_CHECKED:
        return _WEBR_AVAILABLE
    _WEBR_CHECKED = True
    try:
        import webr  # type: ignore[import-not-found]  # noqa: F401

        _WEBR_AVAILABLE = True
    except ImportError as exc:
        _webr_import_error = exc
        _WEBR_AVAILABLE = False
    return _WEBR_AVAILABLE


def detect_webr_installation() -> dict[str, Any]:
    """检测 webr Python 包可用性。

    返回格式与 detect_r_installation() 保持一致：
    {available: bool, path: str|None, version: str|None, message: str}
    """
    if not _check_webr():
        return {
            "available": False,
            "path": None,
            "version": None,
            "message": (
                f"webr 包未安装（{_webr_import_error}）。"
                "运行 `pip install nini[webr]` 以启用无需本地 R 的执行模式。"
            ),
        }

    try:
        import webr  # type: ignore[import]

        version = getattr(webr, "__version__", "unknown")
        return {
            "available": True,
            "path": "webr (wasm)",
            "version": version,
            "message": f"webr {version} 可用（WebAssembly R）",
        }
    except Exception as exc:
        return {
            "available": False,
            "path": None,
            "version": None,
            "message": f"webr 检测失败: {exc}",
        }


def _sanitize_stem(name: str, index: int) -> str:
    import re

    cleaned = re.sub(r"[^0-9A-Za-z_.-]", "_", name).strip("._")
    if not cleaned:
        cleaned = f"dataset_{index}"
    return cleaned


def _write_datasets_csv(
    datasets: dict[str, pd.DataFrame], target_dir: Path
) -> list[dict[str, str]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for idx, (name, df) in enumerate(datasets.items(), start=1):
        if not isinstance(df, pd.DataFrame):
            continue
        stem = _sanitize_stem(name, idx)
        csv_path = target_dir / f"{idx:03d}_{stem}.csv"
        df.to_csv(csv_path, index=False)
        manifest.append({"name": name, "path": str(csv_path)})
    return manifest


def _build_webr_wrapper(
    *,
    user_code: str,
    manifest: list[dict[str, str]],
    dataset_name: str | None,
    persist_df: bool,
    plots_dir: Path,
) -> str:
    """构建传入 webr 的完整 R 脚本（含数据集注入、结果捕获）。"""
    dataset_name_literal = json.dumps(dataset_name or "")
    manifest_json = json.dumps(manifest, ensure_ascii=False)
    plots_dir_str = json.dumps(str(plots_dir))

    return f"""
options(stringsAsFactors = FALSE, warn = 1)

# ---- 数据集注入 ----
manifest_data <- {manifest_json}
datasets <- list()
if (length(manifest_data) > 0) {{
  for (i in seq_along(manifest_data)) {{
    item <- manifest_data[[i]]
    nm <- item$name
    fp <- item$path
    if (file.exists(fp)) {{
      datasets[[nm]] <- utils::read.csv(fp, check.names = FALSE, stringsAsFactors = FALSE)
    }}
  }}
}}

dataset_name <- {dataset_name_literal}
if (nzchar(dataset_name) && dataset_name %in% names(datasets)) {{
  df <- datasets[[dataset_name]]
}}

# ---- 图表捕获 ----
plots_dir <- {plots_dir_str}
dir.create(plots_dir, recursive = TRUE, showWarnings = FALSE)
base_plot_path <- file.path(plots_dir, "base_plots.pdf")
tryCatch(grDevices::pdf(base_plot_path), error = function(e) NULL)
on.exit({{ try(grDevices::dev.off(), silent = TRUE) }}, add = TRUE)

# ---- 执行用户代码 ----
err_msg <- NULL
tryCatch({{
{user_code}
}}, error = function(e) {{
  err_msg <<- conditionMessage(e)
}})

# ---- 捕获 ggplot 对象 ----
if ("ggplot2" %in% loadedNamespaces()) {{
  obj_names <- ls(envir = .GlobalEnv, all.names = TRUE)
  for (nm in obj_names) {{
    obj <- get(nm, envir = .GlobalEnv)
    if (inherits(obj, "ggplot")) {{
      safe <- gsub("[^0-9A-Za-z_.-]", "_", nm)
      if (!nzchar(safe)) safe <- "ggplot"
      png_path <- file.path(plots_dir, paste0("ggplot_", safe, ".png"))
      try(ggplot2::ggsave(filename = png_path, plot = obj, width = 8, height = 5, dpi = 300),
          silent = TRUE)
    }}
  }}
}}

# ---- 数据集持久化 ----
if (exists("df") && nzchar(dataset_name)) {{
  datasets[[dataset_name]] <- df
}}

if (!is.null(err_msg)) {{
  cat(paste0("__NINI_ERROR__:", err_msg, "\n"))
}} else {{
  cat("__NINI_OK__\n")
  if (exists("result")) {{
    tryCatch({{
      cat(paste0("__NINI_RESULT__:", jsonlite::toJSON(result, auto_unbox = TRUE), "\n"))
    }}, error = function(e) NULL)
  }}
}}
""".strip()


class WebRExecutor:
    """WebAssembly R 执行器（通过 webr Python 包）。"""

    def __init__(self, timeout_seconds: int | None = None):
        self.timeout_seconds = timeout_seconds or int(settings.r_webr_timeout)
        self._session: Any = None  # lazy init

    def _get_session(self) -> Any:
        """获取或初始化 webr 会话（延迟初始化，避免启动时下载）。"""
        if self._session is not None:
            return self._session
        import webr  # type: ignore[import]

        # webr Python 包的典型 API：RVirtualMachine / Shelter
        # 不同版本的 API 可能有差异，做兼容处理
        if hasattr(webr, "RVirtualMachine"):
            self._session = webr.RVirtualMachine()
        elif hasattr(webr, "Shelter"):
            self._session = webr.Shelter()
        else:
            raise RuntimeError(
                f"未知的 webr API，请检查已安装版本（{getattr(webr, '__version__', '?')}）"
            )
        return self._session

    async def execute(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None = None,
        persist_df: bool = False,
    ) -> dict[str, Any]:
        return self._execute_sync(
            code=code,
            session_id=session_id,
            datasets=datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )

    def _run_r_code(self, r_session: Any, code: str) -> tuple[str, str]:
        """调用 webr 执行 R 代码，返回 (stdout, stderr)。

        兼容不同版本的 webr Python API。
        """
        # 尝试常见 API 变体
        if hasattr(r_session, "run_r_code"):
            result = r_session.run_r_code(code)
            stdout = getattr(result, "output", "") or ""
            stderr = getattr(result, "message", "") or ""
        elif hasattr(r_session, "eval_r"):
            result = r_session.eval_r(code)
            stdout = str(result) if result is not None else ""
            stderr = ""
        elif hasattr(r_session, "console"):
            console = r_session.console
            console.write(code + "\n")
            if hasattr(console, "read"):
                stdout = console.read() or ""
            else:
                stdout = ""
            stderr = ""
        else:
            raise RuntimeError("无法识别 webr 会话对象的 API，请检查 webr 包版本")
        return str(stdout), str(stderr)

    def _execute_sync(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None,
        persist_df: bool,
    ) -> dict[str, Any]:
        validate_r_code(code)

        if not _check_webr():
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"webr 不可用: {_webr_import_error}",
            }

        run_id = f"webr_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        working_dir = settings.sessions_dir / session_id / "webr_tmp" / run_id
        working_dir.mkdir(parents=True, exist_ok=True)
        plots_dir = working_dir / "plots"

        datasets_manifest = _write_datasets_csv(datasets, working_dir / "datasets")

        wrapper_code = _build_webr_wrapper(
            user_code=code,
            manifest=datasets_manifest,
            dataset_name=dataset_name,
            persist_df=persist_df,
            plots_dir=plots_dir,
        )

        try:
            r_session = self._get_session()
            stdout_raw, stderr_raw = self._run_r_code(r_session, wrapper_code)
        except RSandboxPolicyError:
            raise
        except Exception as exc:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"webr 执行异常: {exc}",
            }

        stdout_lines = stdout_raw.splitlines()
        user_stdout_lines: list[str] = []
        error_msg: str | None = None
        result_json: str | None = None

        for line in stdout_lines:
            if line.startswith("__NINI_ERROR__:"):
                error_msg = line[len("__NINI_ERROR__:") :]
            elif line.startswith("__NINI_RESULT__:"):
                result_json = line[len("__NINI_RESULT__:") :]
            elif line != "__NINI_OK__":
                user_stdout_lines.append(line)

        stdout_text = "\n".join(user_stdout_lines).strip()
        stderr_text = stderr_raw.strip()

        if error_msg is not None:
            return {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": error_msg,
            }

        result_obj: Any = None
        if result_json:
            try:
                result_obj = json.loads(result_json)
            except Exception:
                result_obj = None

        figures: list[dict[str, Any]] = []
        if plots_dir.exists():
            for path in sorted(plots_dir.glob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower().lstrip(".")
                if suffix not in {"pdf", "png", "svg"}:
                    continue
                figures.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "format": suffix,
                        "size": path.stat().st_size,
                    }
                )

        # 清理临时工作目录（仅 webr 模式，文件均在内存中传递，磁盘占用小）
        try:
            import shutil

            shutil.rmtree(working_dir, ignore_errors=True)
        except Exception:
            pass

        return {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "result": result_obj,
            "result_type": type(result_obj).__name__ if result_obj is not None else "null",
            "figures": figures,
            "datasets": {},
            "workdir": str(working_dir),
            "backend": "webr",
        }


webr_executor = WebRExecutor()

__all__ = [
    "WebRExecutor",
    "detect_webr_installation",
    "webr_executor",
]
