"""沙箱错误消息可读性测试。"""

from __future__ import annotations

import pytest
import pandas as pd

from nini.agent.session import Session, session_manager
from nini.config import settings
from nini.tools.code_runtime import execute_python_code


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    settings.ensure_dirs()
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.mark.asyncio
async def test_key_error_integer_on_string_indexed_series_gives_readable_message() -> None:
    """row[j] 对字符串索引 Series 应产生包含 iloc 提示的错误消息，而非裸 '0'。"""
    session = Session()
    session.datasets["test_df"] = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})

    code = """
row = df.iloc[0]   # Series with string index ["col_a", "col_b"]
val = row[0]       # KeyError(0) — integer label lookup on string index
"""

    result = await execute_python_code(session, code=code, dataset_name="test_df")

    assert result.success is False
    message = result.message
    # 不应该是裸 "代码执行失败: 0"
    assert message != "代码执行失败: 0", f"错误消息太模糊: {message!r}"
    # 应包含可诊断内容
    assert any(
        hint in message for hint in ("KeyError", "iloc", "整数", "列名", "label")
    ), f"错误消息应包含诊断提示，实际: {message!r}"


@pytest.mark.asyncio
async def test_key_error_string_key_gives_readable_message() -> None:
    """字典字符串键缺失时，消息走 else 分支，应包含"列名或字典键"提示而非 iloc 建议。"""
    session = Session()

    code = """
d = {"a": 1, "b": 2}
val = d["missing_key"]  # KeyError('missing_key')
"""

    result = await execute_python_code(session, code=code, dataset_name=None)

    assert result.success is False
    message = result.message
    assert (
        "missing_key" in message or "列名" in message or "键" in message
    ), f"错误消息应提及缺失的键，实际: {message!r}"
    # 不应触发 iloc 建议（那是整数下标专属）
    assert "iloc" not in message, f"字符串键不应建议 iloc，实际: {message!r}"


@pytest.mark.asyncio
async def test_key_error_empty_args_gives_readable_message() -> None:
    """裸 raise KeyError() 时（exc.args 为空），消息应包含 '<unknown>'，不含异常对象 repr。"""
    session = Session()

    code = """
raise KeyError()  # 空 args——触发 fallback 分支
"""

    result = await execute_python_code(session, code=code, dataset_name=None)

    assert result.success is False
    message = result.message
    assert "KeyError()" not in message, f"消息不应含异常对象 repr 'KeyError()'，实际: {message!r}"
    assert (
        "<unknown>" in message or "键" in message or "KeyError" in message
    ), f"消息应包含可读兜底提示，实际: {message!r}"
