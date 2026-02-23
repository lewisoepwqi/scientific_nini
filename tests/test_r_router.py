"""R 混合路由器测试（全部使用 mock，不依赖 Rscript 或 webr 实际安装）。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from nini.sandbox.r_router import HybridRExecutor, detect_r_backend

# ---- 辅助工厂函数 ----

_WEBR_OK = {"available": True, "path": "webr (wasm)", "version": "0.3.0", "message": "webr 可用"}
_WEBR_NA = {"available": False, "path": None, "version": None, "message": "webr 未安装"}
_NATIVE_OK = {
    "available": True,
    "path": "/usr/bin/Rscript",
    "version": "R 4.3.0",
    "message": "Rscript 可用",
}
_NATIVE_NA = {"available": False, "path": None, "version": None, "message": "未检测到 Rscript"}

_WEBR_RESULT_OK: dict[str, Any] = {
    "success": True,
    "stdout": "hello webr",
    "stderr": "",
    "result": 42,
    "result_type": "int",
    "figures": [],
    "datasets": {},
    "workdir": "/tmp/webr_run",
    "backend": "webr",
}

_WEBR_RESULT_FAIL: dict[str, Any] = {
    "success": False,
    "stdout": "",
    "stderr": "",
    "error": "webr 执行失败",
}

_NATIVE_RESULT_OK: dict[str, Any] = {
    "success": True,
    "stdout": "hello native R",
    "stderr": "",
    "result": 99,
    "result_type": "int",
    "figures": [],
    "datasets": {},
    "workdir": "/tmp/native_run",
}


@pytest.fixture()
def executor() -> HybridRExecutor:
    return HybridRExecutor()


# ---- 测试 1：普通代码优先走 webr ----


@pytest.mark.asyncio
async def test_router_prefers_webr_for_plain_code(executor: HybridRExecutor) -> None:
    """普通 R 代码（无 Bioc 包）且 webr 成功时，应返回 webr 结果。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_OK),
        patch.object(executor._webr, "_execute_sync", return_value=_WEBR_RESULT_OK) as mock_webr,
        patch.object(
            HybridRExecutor.__bases__[0], "_execute_sync", return_value=_NATIVE_RESULT_OK
        ) as mock_native,
    ):
        result = await executor.execute(
            code="result <- 6 * 7\ncat('hello webr')",
            session_id="sess-001",
            datasets={},
        )

    assert result["success"] is True
    assert result["backend"] == "webr"
    assert result["result"] == 42
    mock_webr.assert_called_once()
    mock_native.assert_not_called()


# ---- 测试 2：Bioc 包强制原生 R ----


@pytest.mark.asyncio
async def test_router_forces_native_for_bioc_packages(executor: HybridRExecutor) -> None:
    """代码引用 Bioconductor 包时，应跳过 webr 直接调用原生 R。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_OK),
        patch.object(executor._webr, "_execute_sync", return_value=_WEBR_RESULT_OK) as mock_webr,
        patch.object(
            HybridRExecutor.__bases__[0], "_execute_sync", return_value=_NATIVE_RESULT_OK
        ) as mock_native,
    ):
        result = await executor.execute(
            code="library(DESeq2)\nresult <- 99",
            session_id="sess-002",
            datasets={},
        )

    assert result["success"] is True
    mock_webr.assert_not_called()
    mock_native.assert_called_once()


# ---- 测试 3：webr 失败后降级原生 R ----


@pytest.mark.asyncio
async def test_router_falls_back_to_native_on_webr_failure(executor: HybridRExecutor) -> None:
    """webr 执行失败时，应自动降级到原生 R 并返回原生 R 结果。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_OK),
        patch.object(executor._webr, "_execute_sync", return_value=_WEBR_RESULT_FAIL) as mock_webr,
        patch.object(
            HybridRExecutor.__bases__[0], "_execute_sync", return_value=_NATIVE_RESULT_OK
        ) as mock_native,
    ):
        result = await executor.execute(
            code="result <- 1 + 1",
            session_id="sess-003",
            datasets={},
        )

    assert result["success"] is True
    assert result.get("backend") != "webr"  # 应来自原生 R（无 backend 字段）
    mock_webr.assert_called_once()
    mock_native.assert_called_once()


# ---- 测试 4：两路均不可用时返回错误 ----


@pytest.mark.asyncio
async def test_router_returns_error_when_both_unavailable(executor: HybridRExecutor) -> None:
    """webr 和原生 R 均不可用时，应返回 success=False 且错误信息包含两路原因。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_NA),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_NA),
    ):
        result = await executor.execute(
            code="result <- 1",
            session_id="sess-004",
            datasets={},
        )

    assert result["success"] is False
    assert "Rscript" in result.get("error", "") or "R" in result.get("error", "")


# ---- 测试 5：r_webr_enabled=False 时直接使用原生 R ----


@pytest.mark.asyncio
async def test_router_respects_r_webr_enabled_false(executor: HybridRExecutor) -> None:
    """settings.r_webr_enabled=False 时应完全跳过 webr，直接使用原生 R。"""
    with (
        patch("nini.sandbox.r_router.settings") as mock_settings,
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_OK),
        patch.object(executor._webr, "_execute_sync", return_value=_WEBR_RESULT_OK) as mock_webr,
        patch.object(
            HybridRExecutor.__bases__[0], "_execute_sync", return_value=_NATIVE_RESULT_OK
        ) as mock_native,
    ):
        mock_settings.r_webr_enabled = False
        mock_settings.r_webr_timeout = 60

        result = await executor.execute(
            code="result <- 1",
            session_id="sess-005",
            datasets={},
        )

    assert result["success"] is True
    mock_webr.assert_not_called()
    mock_native.assert_called_once()


# ---- 测试 6：detect_r_backend 汇总逻辑 ----


def test_detect_r_backend_both_available() -> None:
    """两路均可用时，available=True，message 包含双后端信息。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_OK),
    ):
        info = detect_r_backend()

    assert info["available"] is True
    assert "webr" in info["message"]
    assert "原生 R" in info["message"]


def test_detect_r_backend_only_webr() -> None:
    """只有 webr 可用时，available=True。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_OK),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_NA),
    ):
        info = detect_r_backend()

    assert info["available"] is True


def test_detect_r_backend_neither_available() -> None:
    """两路均不可用时，available=False。"""
    with (
        patch("nini.sandbox.r_router.detect_webr_installation", return_value=_WEBR_NA),
        patch("nini.sandbox.r_router.detect_r_installation", return_value=_NATIVE_NA),
    ):
        info = detect_r_backend()

    assert info["available"] is False
