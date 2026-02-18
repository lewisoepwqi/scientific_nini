"""测试初始化。"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Python 3.12 下在部分测试组合中会出现偶发的 asyncio 事件循环析构告警，
# 不影响功能正确性，统一在测试入口忽略该类噪声。
warnings.filterwarnings(
    "ignore",
    category=ResourceWarning,
    message=r"unclosed event loop .*",
)
