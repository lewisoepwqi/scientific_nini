"""R 混合执行路由器：webr 优先，原生 R 降级。

路由策略：
1. 代码引用了 BIOC_PACKAGES（Bioconductor 包）→ 跳过 webr，直接原生 R
2. webr 可用且未被禁用 → 先尝试 webr
   - 成功 → 返回结果
   - 失败 → 记录日志，降级原生 R
3. 原生 R 可用 → 使用原生 R
4. 两路均不可用 → 返回含原因的错误
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from nini.config import settings
from nini.sandbox.r_executor import (
    BIOC_PACKAGES,
    RSandboxExecutor,
    _extract_required_packages,
    detect_r_installation,
)
from nini.sandbox.r_policy import validate_r_code
from nini.sandbox.webr_executor import WebRExecutor, detect_webr_installation

logger = logging.getLogger(__name__)


def detect_r_backend() -> dict[str, Any]:
    """汇总两路 R 后端的可用性（供 nini doctor 等诊断命令使用）。

    返回：
        {
            "available": bool,      # 任一后端可用即为 True
            "webr": {...},          # detect_webr_installation() 结果
            "native": {...},        # detect_r_installation() 结果
            "message": str,         # 人类可读的状态摘要
        }
    """
    webr_info = detect_webr_installation()
    native_info = detect_r_installation()

    available = bool(webr_info.get("available")) or bool(native_info.get("available"))

    parts: list[str] = []
    if webr_info.get("available"):
        parts.append(f"webr {webr_info.get('version', '')}")
    if native_info.get("available"):
        parts.append(f"原生 R（{native_info.get('version', '')}）")

    if parts:
        message = "R 可用后端：" + "、".join(parts)
    else:
        message = "R 不可用：webr 未安装，且未检测到 Rscript"

    return {
        "available": available,
        "webr": webr_info,
        "native": native_info,
        "message": message,
    }


class HybridRExecutor(RSandboxExecutor):
    """混合 R 执行器：webr 优先，原生 R 降级。

    继承 RSandboxExecutor 以复用原生 R 的完整执行路径
    （包安装、数据集传递、图表捕获、结果解析等），
    仅覆盖 _execute_sync() 以加入路由决策。
    """

    def __init__(
        self,
        timeout_seconds: int | None = None,
        max_memory_mb: int | None = None,
    ):
        super().__init__(timeout_seconds=timeout_seconds, max_memory_mb=max_memory_mb)
        self._webr = WebRExecutor(timeout_seconds=timeout_seconds or int(settings.r_webr_timeout))

    def _execute_sync(
        self,
        *,
        code: str,
        session_id: str,
        datasets: dict[str, pd.DataFrame],
        dataset_name: str | None,
        persist_df: bool,
    ) -> dict[str, Any]:
        # 策略检查（两路共用，在路由前执行）
        validate_r_code(code)

        # 判断是否引用 Bioconductor 包（必须走原生 R）
        referenced_pkgs = _extract_required_packages(code)
        needs_bioc = bool(referenced_pkgs & BIOC_PACKAGES)

        webr_tried = False
        webr_error: str | None = None

        if not needs_bioc and settings.r_webr_enabled:
            webr_info = detect_webr_installation()
            if webr_info.get("available"):
                webr_tried = True
                try:
                    result = self._webr._execute_sync(
                        code=code,
                        session_id=session_id,
                        datasets=datasets,
                        dataset_name=dataset_name,
                        persist_df=persist_df,
                    )
                except Exception as exc:
                    webr_error = str(exc)
                    logger.warning("webr 执行异常，降级原生 R: %s", exc)
                else:
                    if result.get("success"):
                        return result
                    webr_error = result.get("error", "未知错误")
                    logger.warning("webr 执行失败，降级原生 R: %s", webr_error)
            else:
                logger.debug("webr 不可用，直接使用原生 R: %s", webr_info.get("message"))
        elif needs_bioc:
            logger.debug("代码引用 Bioconductor 包，跳过 webr 直接使用原生 R")

        # 原生 R 路径（复用父类完整逻辑，但跳过策略检查避免重复）
        native_info = detect_r_installation()
        if not native_info.get("available"):
            error_parts: list[str] = []
            if webr_tried and webr_error:
                error_parts.append(f"webr 失败: {webr_error}")
            elif not webr_tried and not needs_bioc:
                winfo = detect_webr_installation()
                error_parts.append(f"webr 不可用: {winfo.get('message', '未安装')}")
            elif needs_bioc:
                error_parts.append("代码需要 Bioconductor 包，仅支持原生 R")
            error_parts.append(f"原生 R 不可用: {native_info.get('message', '未检测到 Rscript')}")
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": "；".join(error_parts),
            }

        # 调用父类 _execute_sync（validate_r_code 已在上方执行，父类会再次调用但无副作用）
        return super()._execute_sync(
            code=code,
            session_id=session_id,
            datasets=datasets,
            dataset_name=dataset_name,
            persist_df=persist_df,
        )


# 模块级单例，供 r_code_exec.py 和其他调用方使用
r_sandbox_executor = HybridRExecutor()

__all__ = [
    "HybridRExecutor",
    "detect_r_backend",
    "r_sandbox_executor",
]
