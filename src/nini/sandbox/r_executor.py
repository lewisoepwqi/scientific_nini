"""R 子进程沙箱执行器。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
from typing import Any

import pandas as pd

from nini.config import settings
from nini.sandbox.r_policy import RSandboxPolicyError, validate_r_code

try:
    import resource  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    resource = None  # type: ignore[assignment]


BIOC_PACKAGES: set[str] = {
    "Biobase",
    "BiocGenerics",
    "S4Vectors",
    "IRanges",
    "GenomicRanges",
    "SummarizedExperiment",
    "DESeq2",
    "edgeR",
    "limma",
    "clusterProfiler",
    "org.Hs.eg.db",
    "MetaCycle",
    "JTK_CYCLE",
    "ComplexHeatmap",
    "GSVA",
}

_REQUIRED_BOOTSTRAP_PACKAGES: set[str] = {"jsonlite"}

_PACKAGE_REF_RE = re.compile(
    r"\b(?:library|require|requireNamespace)\s*\(\s*['\"]?([A-Za-z][A-Za-z0-9._]*)['\"]?",
    flags=re.IGNORECASE,
)


def _r_env() -> dict[str, str]:
    lib_dir = settings.data_dir / "r_libs"
    lib_dir.mkdir(parents=True, exist_ok=True)
    return {
        **os.environ,
        "R_PROFILE_USER": "",
        "R_ENVIRON_USER": "",
        "R_LIBS_USER": str(lib_dir),
    }


def _r_lib_init_expr() -> str:
    return (
        "lib_target <- Sys.getenv('R_LIBS_USER');"
        "if (nzchar(lib_target)) {"
        " dir.create(lib_target, recursive=TRUE, showWarnings=FALSE);"
        " .libPaths(c(lib_target, .libPaths()));"
        "};"
    )


def detect_r_installation() -> dict[str, Any]:
    """检测 Rscript 可用性与版本信息。"""
    rscript = shutil.which("Rscript")
    if not rscript:
        return {
            "available": False,
            "path": None,
            "version": None,
            "message": "未检测到 Rscript",
        }

    try:
        proc = subprocess.run(
            [rscript, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        version_text = (proc.stdout or proc.stderr or "").strip()
        return {
            "available": proc.returncode == 0,
            "path": rscript,
            "version": version_text,
            "message": "Rscript 可用" if proc.returncode == 0 else version_text,
        }
    except Exception as exc:
        return {
            "available": False,
            "path": rscript,
            "version": None,
            "message": f"Rscript 检测失败: {exc}",
        }


def _rscript_binary() -> str:
    return shutil.which("Rscript") or "Rscript"


def _extract_required_packages(code: str) -> set[str]:
    packages: set[str] = set()
    for matched in _PACKAGE_REF_RE.finditer(code):
        pkg = matched.group(1)
        if pkg:
            packages.add(pkg)
    return packages


def check_r_packages(packages: set[str]) -> dict[str, bool]:
    """检测包是否已安装。"""
    if not packages:
        return {}

    cmd = [
        _rscript_binary(),
        "--vanilla",
        "-e",
        (
            "args <- commandArgs(trailingOnly=TRUE);" + _r_lib_init_expr() + "for (p in args) {"
            "ok <- requireNamespace(p, quietly=TRUE);"
            "cat(paste0(p, '\\t', ifelse(ok, '1', '0'), '\\n'))"
            "}"
        ),
        *sorted(packages),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(10, int(settings.r_sandbox_timeout // 2)),
        check=False,
        env=_r_env(),
    )

    status: dict[str, bool] = {pkg: False for pkg in packages}
    if proc.returncode != 0:
        return status

    for line in proc.stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        pkg, ok = parts
        if pkg in status:
            status[pkg] = ok == "1"
    return status


def install_r_packages(packages: set[str]) -> tuple[bool, str]:
    """安装缺失包（CRAN + Bioconductor）。"""
    if not packages:
        return True, ""

    cran_packages = sorted(pkg for pkg in packages if pkg not in BIOC_PACKAGES)
    bioc_packages = sorted(pkg for pkg in packages if pkg in BIOC_PACKAGES)

    cmd = [
        _rscript_binary(),
        "--vanilla",
        "-e",
        (
            "args <- commandArgs(trailingOnly=TRUE);"
            + _r_lib_init_expr()
            + "bioc <- strsplit(args[1], ',')[[1]];"
            "bioc <- bioc[bioc != ''];"
            "pkgs <- args[-1];"
            "cran <- pkgs[!(pkgs %in% bioc)];"
            "bioc_need <- pkgs[pkgs %in% bioc];"
            "repos <- 'https://cloud.r-project.org';"
            "lib_target <- ifelse(nzchar(Sys.getenv('R_LIBS_USER')), Sys.getenv('R_LIBS_USER'), .libPaths()[1]);"
            "if (length(cran) > 0) { install.packages(cran, repos=repos, lib=lib_target); };"
            "if (length(bioc_need) > 0) {"
            " if (!requireNamespace('BiocManager', quietly=TRUE)) {"
            "   install.packages('BiocManager', repos=repos, lib=lib_target);"
            " };"
            " BiocManager::install(bioc_need, ask=FALSE, update=FALSE, lib=lib_target);"
            "}"
        ),
        ",".join(sorted(BIOC_PACKAGES)),
        *sorted(packages),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(settings.r_package_install_timeout),
            check=False,
            env=_r_env(),
        )
    except subprocess.TimeoutExpired:
        return False, f"R 包安装超时（>{settings.r_package_install_timeout}s）"

    output = "\n".join(x for x in [proc.stdout.strip(), proc.stderr.strip()] if x).strip()
    if proc.returncode != 0:
        return False, output or "R 包安装失败"
    return True, output


def _build_preexec_fn(max_memory_mb: int):
    if resource is None:
        return None

    def _limit_resources() -> None:
        try:
            if hasattr(resource, "RLIMIT_AS") and max_memory_mb > 0:
                mem_bytes = int(max(256, max_memory_mb)) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:
            pass

    return _limit_resources


def _sanitize_stem(name: str, index: int) -> str:
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


def _build_wrapper_script(
    *,
    user_code_path: Path,
    manifest_path: Path,
    dataset_name: str | None,
    persist_df: bool,
) -> str:
    dataset_name_literal = json.dumps(dataset_name or "")
    return f"""
options(stringsAsFactors = FALSE, warn = 1)
{_r_lib_init_expr()}

manifest_path <- {json.dumps(str(manifest_path))}
user_code_path <- {json.dumps(str(user_code_path))}
plots_dir <- file.path(getwd(), "plots")
dir.create(plots_dir, recursive = TRUE, showWarnings = FALSE)

manifest <- jsonlite::fromJSON(manifest_path)
datasets <- list()
if (is.data.frame(manifest) && nrow(manifest) > 0) {{
  for (i in seq_len(nrow(manifest))) {{
    nm <- as.character(manifest$name[[i]])
    fp <- as.character(manifest$path[[i]])
    datasets[[nm]] <- utils::read.csv(fp, check.names = FALSE, stringsAsFactors = FALSE)
  }}
}}

dataset_name <- {dataset_name_literal}
if (nzchar(dataset_name) && dataset_name %in% names(datasets)) {{
  df <- datasets[[dataset_name]]
}}

base_plot_path <- file.path(plots_dir, "base_plots.pdf")
grDevices::pdf(base_plot_path)
on.exit({{ try(grDevices::dev.off(), silent = TRUE) }}, add = TRUE)

err_msg <- NULL
tryCatch({{
  user_code <- paste(readLines(user_code_path, warn = FALSE, encoding = "UTF-8"), collapse = "\\n")
  eval(parse(text = user_code), envir = .GlobalEnv)
}}, error = function(e) {{
  err_msg <<- conditionMessage(e)
}})

if (exists("df") && nzchar(dataset_name)) {{
  datasets[[dataset_name]] <- df
}}

# 捕获显式创建但未自动输出的 ggplot 对象
if ("ggplot2" %in% loadedNamespaces()) {{
  obj_names <- ls(envir = .GlobalEnv, all.names = TRUE)
  for (nm in obj_names) {{
    obj <- get(nm, envir = .GlobalEnv)
    if (inherits(obj, "ggplot")) {{
      safe <- gsub("[^0-9A-Za-z_.-]", "_", nm)
      if (!nzchar(safe)) safe <- "ggplot"
      png_path <- file.path(plots_dir, paste0("ggplot_", safe, ".png"))
      pdf_path <- file.path(plots_dir, paste0("ggplot_", safe, ".pdf"))
      try(ggplot2::ggsave(filename = png_path, plot = obj, width = 8, height = 5, dpi = 300), silent = TRUE)
      try(ggplot2::ggsave(filename = pdf_path, plot = obj, width = 8, height = 5), silent = TRUE)
    }}
  }}
}}

updates_manifest <- list()
if ({"TRUE" if persist_df else "FALSE"}) {{
  updates_dir <- file.path(getwd(), "dataset_updates")
  dir.create(updates_dir, recursive = TRUE, showWarnings = FALSE)
  for (nm in names(datasets)) {{
    safe <- gsub("[^0-9A-Za-z_.-]", "_", nm)
    if (!nzchar(safe)) safe <- "dataset"
    out_path <- file.path(updates_dir, paste0(safe, ".csv"))
    utils::write.csv(datasets[[nm]], out_path, row.names = FALSE)
    updates_manifest[[nm]] <- out_path
  }}
  jsonlite::write_json(updates_manifest, "_datasets.json", auto_unbox = TRUE, pretty = TRUE)
}}

result_type <- "null"
result_payload <- NULL
result_repr <- NULL

if (exists("result")) {{
  result_type <- class(result)[1]
  if (is.data.frame(result)) {{
    utils::write.csv(result, "_result_df.csv", row.names = FALSE)
    result_type <- "data.frame"
    result_payload <- list(
      rows = nrow(result),
      columns = as.list(names(result))
    )
  }} else {{
    result_payload <- tryCatch(
      jsonlite::fromJSON(jsonlite::toJSON(result, auto_unbox = TRUE, dataframe = "rows", null = "null")),
      error = function(e) NULL
    )
    if (is.null(result_payload)) {{
      result_repr <- paste(utils::capture.output(str(result, max.level = 1)), collapse = "\\n")
    }}
  }}
}}

if (exists("output_df") && is.data.frame(output_df)) {{
  utils::write.csv(output_df, "_output_df.csv", row.names = FALSE)
}}

if (!is.null(err_msg)) {{
  jsonlite::write_json(
    list(success = FALSE, error = err_msg),
    "_result.json",
    auto_unbox = TRUE,
    pretty = TRUE,
    null = "null"
  )
  quit(status = 1)
}}

jsonlite::write_json(
  list(
    success = TRUE,
    result_type = result_type,
    result = result_payload,
    result_repr = result_repr
  ),
  "_result.json",
  auto_unbox = TRUE,
  pretty = TRUE,
  null = "null"
)
""".strip() + "\n"


class RSandboxExecutor:
    """R 沙箱执行器。"""

    def __init__(self, timeout_seconds: int | None = None, max_memory_mb: int | None = None):
        self.timeout_seconds = timeout_seconds or int(settings.r_sandbox_timeout)
        self.max_memory_mb = max_memory_mb or int(settings.r_sandbox_max_memory_mb)

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

        installation = detect_r_installation()
        if not installation.get("available"):
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": installation.get("message", "Rscript 不可用"),
            }

        run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        working_dir = settings.sessions_dir / session_id / "r_sandbox_tmp" / run_id
        working_dir.mkdir(parents=True, exist_ok=True)

        datasets_manifest = _write_datasets_csv(datasets, working_dir / "datasets")
        manifest_path = working_dir / "_datasets_manifest.json"
        manifest_path.write_text(
            json.dumps(datasets_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        referenced_packages = _extract_required_packages(code) | _REQUIRED_BOOTSTRAP_PACKAGES
        if referenced_packages:
            pkg_status = check_r_packages(referenced_packages)
            missing = {pkg for pkg, ok in pkg_status.items() if not ok}
            if missing:
                if not settings.r_auto_install_packages:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "",
                        "error": f"缺少 R 包: {', '.join(sorted(missing))}",
                    }
                install_ok, install_log = install_r_packages(missing)
                if not install_ok:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": install_log,
                        "error": "R 包自动安装失败",
                    }

        user_code_path = working_dir / "user_code.R"
        user_code_path.write_text(code, encoding="utf-8")
        wrapper_path = working_dir / "_wrapper.R"
        wrapper_path.write_text(
            _build_wrapper_script(
                user_code_path=user_code_path,
                manifest_path=manifest_path,
                dataset_name=dataset_name,
                persist_df=persist_df,
            ),
            encoding="utf-8",
        )

        cmd = [_rscript_binary(), "--vanilla", str(wrapper_path)]
        env = _r_env()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                env=env,
                preexec_fn=_build_preexec_fn(self.max_memory_mb),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"R 代码执行超时（>{self.timeout_seconds}s）",
            }
        except Exception as exc:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"R 代码执行失败: {exc}",
            }

        stdout_text = (proc.stdout or "").strip()
        stderr_text = (proc.stderr or "").strip()

        result_json_path = working_dir / "_result.json"
        result_data: dict[str, Any] = {}
        if result_json_path.exists():
            try:
                loaded = json.loads(result_json_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    result_data = loaded
            except Exception:
                result_data = {}

        if proc.returncode != 0 and not result_data.get("success", False):
            return {
                "success": False,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "error": str(result_data.get("error") or "R 代码执行失败"),
            }

        output_df: pd.DataFrame | None = None
        output_df_path = working_dir / "_output_df.csv"
        if output_df_path.exists():
            try:
                output_df = pd.read_csv(output_df_path)
            except Exception:
                output_df = None

        result_obj: Any = result_data.get("result")
        result_type = str(result_data.get("result_type") or "null")
        result_repr = result_data.get("result_repr")

        if output_df is None and result_type == "data.frame":
            result_df_path = working_dir / "_result_df.csv"
            if result_df_path.exists():
                try:
                    output_df = pd.read_csv(result_df_path)
                except Exception:
                    output_df = None

        persisted_datasets: dict[str, pd.DataFrame] = {}
        if persist_df:
            updates_manifest = working_dir / "_datasets.json"
            if updates_manifest.exists():
                try:
                    loaded = json.loads(updates_manifest.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        for name, path in loaded.items():
                            if isinstance(name, str) and isinstance(path, str):
                                csv_path = Path(path)
                                if csv_path.exists():
                                    persisted_datasets[name] = pd.read_csv(csv_path)
                except Exception:
                    persisted_datasets = {}

        figures: list[dict[str, Any]] = []
        plots_dir = working_dir / "plots"
        if plots_dir.exists():
            for path in sorted(plots_dir.glob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower().lstrip(".")
                if suffix not in {"pdf", "png", "svg", "html"}:
                    continue
                figures.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "format": suffix,
                        "size": path.stat().st_size,
                    }
                )

        payload: dict[str, Any] = {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "result": result_obj,
            "result_type": result_type,
            "figures": figures,
            "datasets": persisted_datasets,
            "workdir": str(working_dir),
        }
        if result_repr:
            payload["result_repr"] = result_repr
        if output_df is not None:
            payload["output_df"] = output_df

        return payload


r_sandbox_executor = RSandboxExecutor()


__all__ = [
    "BIOC_PACKAGES",
    "RSandboxExecutor",
    "check_r_packages",
    "detect_r_installation",
    "install_r_packages",
    "r_sandbox_executor",
    "RSandboxPolicyError",
]
