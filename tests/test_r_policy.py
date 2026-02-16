"""R 沙箱策略测试。"""

from __future__ import annotations

import pytest

from nini.sandbox.r_policy import RSandboxPolicyError, validate_r_code


def test_r_policy_allows_safe_code() -> None:
    code = """
result <- 1 + 2
x <- c(1, 2, 3)
print(mean(x))
"""
    validate_r_code(code)


def test_r_policy_blocks_banned_call() -> None:
    code = """
result <- 1
system('ls')
"""
    with pytest.raises(RSandboxPolicyError) as exc_info:
        validate_r_code(code)

    assert "不允许调用函数" in str(exc_info.value)
    assert "system" in str(exc_info.value)


def test_r_policy_blocks_non_whitelist_package() -> None:
    code = """
library(devtools)
result <- 1
"""
    with pytest.raises(RSandboxPolicyError) as exc_info:
        validate_r_code(code)

    assert "不允许使用 R 包" in str(exc_info.value)
    assert "devtools" in str(exc_info.value)


def test_r_policy_ignores_comment_line() -> None:
    code = """
# system('rm -rf /')
result <- 42
"""
    validate_r_code(code)
