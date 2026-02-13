"""测试沙箱导入修复。

验证用户代码中的 import 语句可以正常工作。
"""

from __future__ import annotations

import pandas as pd
import pytest

from nini.agent.session import Session
from nini.sandbox.executor import sandbox_executor


class TestSandboxImportFix:
    """测试沙箱导入功能。"""

    @pytest.mark.asyncio
    async def test_import_numpy(self):
        """测试 import numpy。"""
        code = """
import numpy as np

result = np.array([1, 2, 3, 4, 5])
print(f"数组均值: {result.mean()}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "数组均值: 3.0" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_import_datetime(self):
        """测试 import datetime。"""
        code = """
import datetime

now = datetime.datetime(2024, 1, 15, 12, 30, 0)
formatted = now.strftime("%Y-%m-%d %H:%M")
print(f"格式化时间: {formatted}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "2024-01-15 12:30" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_import_collections(self):
        """测试 from collections import Counter。"""
        code = """
from collections import Counter

words = ['apple', 'banana', 'apple', 'cherry', 'banana', 'apple']
counts = Counter(words)
print(f"最常见: {counts.most_common(1)}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "apple" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_import_re(self):
        """测试 import re（正则表达式）。"""
        code = """
import re

text = "There are 123 apples and 456 oranges"
numbers = re.findall(r'\\d+', text)
print(f"找到的数字: {numbers}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "123" in outcome["stdout"]
        assert "456" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_preloaded_modules(self):
        """测试预加载的模块可以直接使用（无需 import）。"""
        code = """
# 直接使用预加载的模块
arr = np.array([1, 2, 3])
print(f"NumPy 数组: {arr}")

now = datetime.datetime.now()
print(f"当前时间验证: {str(now)[:10]}")  # 输出日期部分，避免使用 type()

pattern = re.compile(r'\\d+')
result = pattern.findall('123abc456')
print(f"正则匹配结果: {result}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "NumPy 数组" in outcome["stdout"]
        assert "当前时间验证" in outcome["stdout"]
        assert "正则匹配结果" in outcome["stdout"]
        assert "123" in outcome["stdout"]
        assert "456" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_pandas_numpy_integration(self):
        """测试 pandas + numpy 集成（用户报告的场景）。"""
        code = """
import pandas as pd
import numpy as np

# 创建测试数据
df = pd.DataFrame({
    'A': [1, 2, 3, 4, 5],
    'B': [10, 20, 30, 40, 50]
})

# NumPy 操作
mean_a = np.mean(df['A'])
print(f"A列均值: {mean_a}")

# Pandas 操作
total = df['B'].sum()
print(f"B列总和: {total}")
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "A列均值: 3.0" in outcome["stdout"]
        assert "B列总和: 150" in outcome["stdout"]

    @pytest.mark.asyncio
    async def test_blocked_import_still_fails(self):
        """测试被禁止的模块导入仍然失败。"""
        from nini.sandbox.policy import SandboxPolicyError

        code = """
import os
files = os.listdir('.')
"""
        session = Session()

        # 应该在 validate_code 阶段抛出 SandboxPolicyError
        with pytest.raises(SandboxPolicyError) as exc_info:
            await sandbox_executor.execute(
                code=code,
                session_id=session.id,
                datasets=session.datasets,
                dataset_name=None,
                persist_df=False,
            )

        assert "不允许导入" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_user_reported_scenario(self):
        """测试用户报告的实际场景。"""
        code = """
import pandas as pd
import numpy as np

# 模拟用户的数据
df = pd.DataFrame({
    'Unnamed: 0': [1, 2, 3],
    'Unnamed: 4': ['a', 'b', 'c'],
    'Unnamed: 5': [None, None, None],
})

# 查看前几行
print("前3行数据：")
print(df.head(3))

# 列信息
print("\\n列名和数据类型：")
print(df.dtypes)

# 数据形状
print("\\n数据形状:", df.shape)

# 缺失值统计
print("\\n缺失值统计：")
print(df.isnull().sum())
"""
        session = Session()
        outcome = await sandbox_executor.execute(
            code=code,
            session_id=session.id,
            datasets=session.datasets,
            dataset_name=None,
            persist_df=False,
        )

        assert outcome["success"], f"执行失败: {outcome.get('error')}"
        assert "前3行数据" in outcome["stdout"]
        assert "数据形状" in outcome["stdout"]
        assert "缺失值统计" in outcome["stdout"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
