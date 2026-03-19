"""代码执行技能：兼容入口，内部走脚本会话链路。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.code_session import CodeSessionSkill


class RunCodeSkill(Tool):
    """运行用户提供的 Python 代码。"""

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "在受限沙箱中运行 Python 代码。支持 matplotlib/plotly 绘图，图表会自动检测并保存为产物。"
            "可使用变量：datasets（所有数据集字典）、df（指定 dataset_name 时可用）。"
            "可通过 result 返回结果，或通过 output_df 返回 DataFrame。"
            "绘制复杂自定义图表、子图布局、统计标注时，优先使用此工具而非 create_chart。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码片段",
                },
                "dataset_name": {
                    "type": "string",
                    "description": "可选。绑定为变量 df 的数据集名称",
                },
                "persist_df": {
                    "type": "boolean",
                    "default": False,
                    "description": "当 dataset_name 存在时，是否将修改后的 df 覆盖回原数据集",
                },
                "save_as": {
                    "type": "string",
                    "description": "可选。若 result/output_df 是 DataFrame，则另存为该数据集名",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["exploration", "visualization", "export", "transformation"],
                    "default": "exploration",
                    "description": "代码用途：exploration=探索性分析，visualization=绘图，export=导出，transformation=数据变换",
                },
                "label": {
                    "type": "string",
                    "description": "简短描述代码用途，如'绘制组间箱线图'，用于产物命名",
                },
                "intent": {
                    "type": "string",
                    "description": "执行意图摘要（建议 8-30 字），用于记录本次 run_code 的分析目的",
                },
            },
            "required": ["code"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        return await CodeSessionSkill().run_ad_hoc_script(
            session,
            language="python",
            content=str(kwargs.get("code", "") or ""),
            dataset_name=kwargs.get("dataset_name"),
            persist_df=bool(kwargs.get("persist_df", False)),
            save_as=kwargs.get("save_as"),
            purpose=kwargs.get("purpose", "exploration"),
            label=kwargs.get("label"),
            intent=kwargs.get("intent"),
            extra_allowed_imports=kwargs.get("extra_allowed_imports"),
            source_tool="run_code",
        )
