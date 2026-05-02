"""沙箱安全加固回归测试：df.eval/query 拦截、pd.read_* 路径限制、safe_type 行为。"""

from __future__ import annotations

import uuid
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from nini.config import settings
from nini.sandbox.executor import (
    SandboxExecutor,
    safe_type,
    _check_eval_expr,
    _make_path_restricted_reader,
)
from nini.sandbox.policy import SandboxPolicyError


def _random_session_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


# --- df.eval / df.query 表达式拦截 ---


class TestEvalQueryInterception:
    """验证 df.eval/df.query 中的危险表达式被拦截，合法表达式正常执行。"""

    @pytest.mark.parametrize(
        "expr",
        [
            "__import__('os').system('id')",
            "exec('pass')",
            "compile('1','','exec')",
            "open('/etc/passwd')",
            "os.system('id')",
            "subprocess.run(['ls'])",
            "sys.exit(1)",
        ],
    )
    def test_eval_dangerous_expression_blocked(self, expr: str) -> None:
        with pytest.raises(SandboxPolicyError, match="df.eval"):
            _check_eval_expr(expr, "df.eval")

    @pytest.mark.parametrize(
        "expr",
        [
            "age > 30",
            "salary * 12",
            "col_a + col_b",
            "(x > 0) & (y < 10)",
        ],
    )
    def test_eval_safe_expression_passes(self, expr: str) -> None:
        _check_eval_expr(expr, "df.eval")

    def test_eval_query_same_rules(self) -> None:
        with pytest.raises(SandboxPolicyError, match="df.query"):
            _check_eval_expr("__import__('os')", "df.query")

    def test_non_string_expr_passes(self) -> None:
        _check_eval_expr(123, "df.eval")

    @pytest.mark.asyncio
    async def test_eval_blocked_in_sandbox(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        with pytest.raises(SandboxPolicyError, match="__import__"):
            await executor.execute(
                code="result = df.eval(\"__import__('os').system('id')\")",
                session_id=_random_session_id(),
                datasets={"df": pd.DataFrame({"a": [1, 2]})},
                dataset_name="df",
            )

    @pytest.mark.asyncio
    async def test_eval_safe_in_sandbox(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        result = await executor.execute(
            code="result = df.eval('a > 1')",
            session_id=_random_session_id(),
            datasets={"df": pd.DataFrame({"a": [1, 2, 3]})},
            dataset_name="df",
        )
        assert result["success"] is True
        # df.eval('a > 1') 返回 boolean Series，不是 DataFrame
        assert isinstance(result["result"], pd.Series)

    @pytest.mark.asyncio
    async def test_query_safe_in_sandbox(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        result = await executor.execute(
            code="result = df.query('a > 1')",
            session_id=_random_session_id(),
            datasets={"df": pd.DataFrame({"a": [1, 2, 3]})},
            dataset_name="df",
        )
        assert result["success"] is True
        assert isinstance(result["result"], pd.DataFrame)
        assert len(result["result"]) == 2


# --- pd.read_* 路径限制 ---


class TestReadPathRestriction:
    """验证 pd.read_* 系列函数限制路径在 working_dir 内。"""

    def test_read_within_working_dir(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "data.csv"
        csv_path.write_text("a,b\n1,2\n")

        _restricted = _make_path_restricted_reader(pd.read_csv, "read_csv", str(tmp_path))
        # 使用绝对路径，因为测试 CWD 不一定是 tmp_path
        df = _restricted(str(csv_path))
        assert len(df) == 1

    def test_read_absolute_path_blocked(self, tmp_path: Path) -> None:
        _restricted = _make_path_restricted_reader(pd.read_csv, "read_csv", str(tmp_path))
        with pytest.raises(SandboxPolicyError, match="工作目录之外"):
            _restricted("/etc/passwd")

    def test_read_traversal_blocked(self, tmp_path: Path) -> None:
        _restricted = _make_path_restricted_reader(pd.read_csv, "read_csv", str(tmp_path))
        with pytest.raises(SandboxPolicyError, match="工作目录之外|路径遍历"):
            _restricted("../../../../etc/passwd")

    def test_read_buffer_passes(self, tmp_path: Path) -> None:
        _restricted = _make_path_restricted_reader(pd.read_csv, "read_csv", str(tmp_path))
        df = _restricted(StringIO("a,b\n1,2\n"))
        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_read_csv_absolute_blocked_in_sandbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        with pytest.raises(SandboxPolicyError, match="工作目录之外"):
            await executor.execute(
                code="result = pd.read_csv('/etc/passwd')",
                session_id=_random_session_id(),
                datasets={},
            )


# --- safe_type 行为 ---


class TestSafeType:
    """验证 safe_type 仅允许单参数形式。"""

    def test_single_arg_returns_type(self) -> None:
        assert safe_type(42) is int
        assert safe_type("hello") is str
        assert safe_type([1, 2]) is list

    def test_three_args_blocked(self) -> None:
        with pytest.raises(SandboxPolicyError, match="动态创建类型"):
            safe_type("X", (), {})

    def test_two_args_blocked(self) -> None:
        with pytest.raises(SandboxPolicyError, match="动态创建类型"):
            safe_type("X", ())

    @pytest.mark.asyncio
    async def test_type_single_arg_in_sandbox(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        result = await executor.execute(
            code="result = str(type(42))",
            session_id=_random_session_id(),
            datasets={},
        )
        assert result["success"] is True
        assert result["result"] == "<class 'int'>"

    @pytest.mark.asyncio
    async def test_type_three_args_blocked_in_sandbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
        settings.ensure_dirs()

        executor = SandboxExecutor()
        with pytest.raises(SandboxPolicyError, match="动态创建类型"):
            await executor.execute(
                code="result = type('X', (), {})",
                session_id=_random_session_id(),
                datasets={},
            )
