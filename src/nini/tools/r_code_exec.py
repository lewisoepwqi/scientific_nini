"""R 代码执行技能：兼容入口，内部走脚本会话链路。"""

from __future__ import annotations

from typing import Any

from nini.agent.session import Session
from nini.tools.base import Tool, ToolResult
from nini.tools.code_session import CodeSessionSkill


class RunRCodeSkill(Tool):
    """运行用户提供的 R 代码。"""

    @property
    def name(self) -> str:
        return "run_r_code"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "在受限沙箱中运行 R 代码。支持 datasets/df 数据集注入，"
            "可通过 result 返回结构化结果，或通过 output_df 返回数据框。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要执行的 R 代码片段",
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
                    "description": "可选。若 result/output_df 是数据框，则另存为该数据集名",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["exploration", "visualization", "export", "transformation"],
                    "default": "exploration",
                    "description": "代码用途：用于执行历史与产物命名策略",
                },
                "label": {
                    "type": "string",
                    "description": "简短描述代码用途，如‘R 绘制昼夜节律图’",
                },
                "intent": {
                    "type": "string",
                    "description": "执行意图摘要（建议 8-30 字），用于记录本次 run_r_code 的分析目的",
                },
            },
            "required": ["code"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        return await CodeSessionSkill().run_ad_hoc_script(
            session,
            language="r",
            content=str(kwargs.get("code", "") or ""),
            dataset_name=kwargs.get("dataset_name"),
            persist_df=bool(kwargs.get("persist_df", False)),
            save_as=kwargs.get("save_as"),
            purpose=kwargs.get("purpose", "exploration"),
            label=kwargs.get("label"),
            intent=kwargs.get("intent"),
            source_tool="run_r_code",
        )
