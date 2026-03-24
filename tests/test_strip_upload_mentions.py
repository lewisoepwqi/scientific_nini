"""测试 _strip_upload_mentions：过滤摘要中含 upload/上传 关键词的整句。"""

import pytest

from nini.memory.compression import _strip_upload_mentions


@pytest.mark.parametrize(
    "input_text, expected_removed, description",
    [
        # 含 upload 关键词的英文路径句子应被过滤
        (
            "用户分析了数据集。用户通过 upload 上传了文件。结果显示 p<0.05。",
            True,
            "含 upload 关键词的句子应被过滤",
        ),
        # 含 上传 关键词的中文句子应被过滤
        (
            "- [user] 上传了 data/sessions/abc/workspace/sample.csv",
            True,
            "含上传关键词的行应被过滤",
        ),
        # 不含上传关键词的内容不受影响
        (
            "分析结果：t(48)=3.21, p=0.002, d=0.92。结论支持研究假设。",
            False,
            "不含关键词的句子不应被过滤",
        ),
        # 大小写不敏感
        (
            "File was created via UPLOAD operation.",
            True,
            "大写 UPLOAD 也应被过滤",
        ),
    ],
)
def test_strip_upload_mentions(input_text: str, expected_removed: bool, description: str) -> None:
    result = _strip_upload_mentions(input_text)
    if expected_removed:
        assert (
            "upload" not in result.lower() and "上传" not in result
        ), f"{description}: 过滤后结果仍含关键词，result={result!r}"
    else:
        # 原文应完整保留（允许末尾空白差异）
        assert (
            result.strip() == input_text.strip()
        ), f"{description}: 不含关键词的内容不应被修改，result={result!r}"


def test_strip_upload_mentions_preserves_non_upload_sentences() -> None:
    """含上传关键词的句子被过滤，同段其余句子保留。"""
    text = "用户研究了心率变异性。用户上传了 HRV.csv 文件。结论：HRV 与焦虑显著相关。"
    result = _strip_upload_mentions(text)
    assert "上传" not in result
    assert "心率变异性" in result
    assert "焦虑" in result


def test_strip_upload_mentions_empty_input() -> None:
    """空字符串输入不报错，返回空字符串。"""
    assert _strip_upload_mentions("") == ""


def test_strip_upload_mentions_all_filtered() -> None:
    """全部内容含关键词时返回空字符串。"""
    text = "用户上传了文件一。\n用户上传了文件二。"
    result = _strip_upload_mentions(text)
    assert "上传" not in result
