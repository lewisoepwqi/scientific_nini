"""图表代码模板：生成用于复现图表的 Python 脚本。

设计目标（D1 内联）：生成的脚本必须自包含，不依赖 nini 包，仅依赖 pandas / plotly / matplotlib。
所需的样式辅助函数（apply_plotly_style、_prepare_line_dataframe 等）会被内联到生成代码中。

设计目标（D2 完全替代）：visualization.py 的渲染路径也通过对本模块生成的代码执行 exec() 来完成，
确保"代码档案中的代码"与"实际渲染产物"完全等价，无漂移。
"""

from __future__ import annotations

from nini.charts.code_templates.plotly_templates import render_plotly_script

__all__ = ["render_plotly_script"]
