"""规划层 Agent。

负责意图识别、任务分解、方案选择和生成执行计划。
"""

from __future__ import annotations

import logging
from typing import Any

from nini.agent.session import Session
from nini.agent.model_resolver import ModelResolver, model_resolver
from nini.models.execution_plan import (
    ActionType,
    ExecutionPlan,
    MustHave,
    PhaseType,
    PlanAction,
    PlanPhase,
    PlanStatus,
)

# 规划提示词：要求 LLM 输出结构化意图分析，包含 must_haves 数组
_INTENT_ANALYSIS_PROMPT = """你是科研数据分析规划助手。根据用户消息和会话上下文，识别用户分析意图。

请以 JSON 格式输出：
{{
  "intent": "用户意图的一句话描述",
  "must_haves": [
    {{"type": "truth", "description": "必须验证的统计事实"}},
    {{"type": "artifact", "description": "必须生成的产物（图/报告/表格）"}},
    {{"type": "key_link", "description": "关键推理链条"}}
  ]
}}

type 枚举值：truth（统计事实）、artifact（产物）、key_link（推理链）。
must_haves 数组可包含 0-5 项，只列出真正必要的条件。
仅输出 JSON，不要添加任何额外文字。

用户消息：{user_message}"""

logger = logging.getLogger(__name__)


class PlannerAgent:
    """规划层 Agent。

    在执行层之前运行，负责：
    1. 意图识别（用户想做什么？）
    2. 任务分解（需要哪些步骤？）
    3. 方案选择（用什么统计方法？）
    4. 生成执行计划（JSON 格式）
    """

    def __init__(self, resolver: ModelResolver | None = None):
        """初始化规划 Agent。

        Args:
            resolver: 模型解析器，默认使用全局单例
        """
        self._resolver = resolver or model_resolver

    async def create_plan(
        self,
        session: Session,
        user_message: str,
    ) -> ExecutionPlan:
        """根据用户消息创建执行计划。

        Args:
            session: 会话对象
            user_message: 用户消息

        Returns:
            ExecutionPlan: 生成的执行计划
        """
        # 分析意图（含 must_haves 生成）
        intent, must_haves = await self._analyze_intent_with_must_haves(session, user_message)

        # 检查是否有数据
        has_data = len(session.datasets) > 0

        # 构建阶段
        phases: list[PlanPhase] = []

        # 阶段1: 数据加载（如果需要）
        if not has_data:
            phases.append(
                PlanPhase(
                    phase_type="data_loading",
                    description="加载用户数据",
                    actions=[
                        PlanAction(
                            action_type="load_data",
                            skill="load_dataset",
                            parameters={"prompt": "请上传数据集"},
                            description="等待用户上传数据",
                        )
                    ],
                    status=PlanStatus.PENDING,
                )
            )

        # 阶段2: 数据检查
        phases.append(
            PlanPhase(
                phase_type="data_check",
                description="检查数据质量和摘要",
                actions=[
                    PlanAction(
                        action_type="summary",
                        skill="data_summary",
                        parameters={},
                        description="生成数据摘要",
                    )
                ],
                status=PlanStatus.PENDING,
            )
        )

        # 阶段3: 统计分析（根据意图选择）
        stat_phase = self._create_statistical_phase(intent, session)
        phases.append(stat_phase)

        # 阶段4: 可视化
        phases.append(
            PlanPhase(
                phase_type="visualization",
                description="生成可视化图表",
                actions=[
                    PlanAction(
                        action_type="create_chart",
                        skill="create_chart",
                        parameters={"journal_style": "nature"},
                        description="创建图表",
                    )
                ],
                status=PlanStatus.PENDING,
            )
        )

        # 阶段5: 报告（不再无条件添加，由 Agent 根据用户意图和提示词指导决定）
        # 移除自动报告生成，让 Agent 通过 strategy.md 指导自主判断
        # phases.append(PlanPhase(
        #     phase_type="report",
        #     description="生成分析报告",
        #     actions=[
        #         PlanAction(
        #             action_type="generate_report",
        #             skill="generate_report",
        #             parameters={},
        #             description="生成最终报告",
        #         )
        #     ],
        #     status=PlanStatus.PENDING,
        # ))

        return ExecutionPlan(
            user_intent=intent,
            phases=phases,
            status=PlanStatus.PENDING,
            must_haves=must_haves,
        )

    async def _analyze_intent_with_must_haves(
        self,
        session: Session,
        user_message: str,
    ) -> tuple[str, list[MustHave]]:
        """通过 LLM 分析用户意图，同时生成 must_haves 清单。

        失败时降级为关键词匹配，must_haves 返回空列表。
        """
        import json

        try:
            prompt = _INTENT_ANALYSIS_PROMPT.format(user_message=user_message)
            messages = [{"role": "user", "content": prompt}]
            full_text = ""
            # 显式传 purpose="planning" 以便后续可针对规划任务配置专用路由
            async for chunk in self._resolver.chat(
                messages,
                purpose="planning",
            ):
                if chunk.text:
                    full_text += chunk.text
            data = json.loads(full_text.strip())
            intent = str(data.get("intent", "数据分析")).strip() or "数据分析"
            raw_must_haves = data.get("must_haves", [])
            must_haves = []
            for item in raw_must_haves:
                if isinstance(item, dict) and "type" in item and "description" in item:
                    try:
                        must_haves.append(MustHave(**item))
                    except Exception:
                        pass
            return intent, must_haves
        except Exception:
            logger.debug("LLM 意图分析失败，降级为关键词匹配", exc_info=True)
            return self._keyword_intent(user_message), []

    def _keyword_intent(self, user_message: str) -> str:
        """关键词匹配兜底意图分析。"""
        message_lower = user_message.lower()
        if any(word in message_lower for word in ["差异", "不同", "比较", "对照"]):
            return "比较两组或多组数据的差异"
        elif any(word in message_lower for word in ["关系", "相关", "关联"]):
            return "分析变量间的相关性"
        elif any(word in message_lower for word in ["预测", "回归", "影响"]):
            return "建立预测模型"
        elif any(word in message_lower for word in ["分析", "统计", "检验"]):
            return "进行统计分析"
        else:
            return "数据分析"

    def _create_statistical_phase(
        self,
        intent: str,
        session: Session,
    ) -> PlanPhase:
        """根据意图创建统计分析阶段。"""
        # 根据数据集判断分析类型
        if len(session.datasets) > 0:
            # 检查第一个数据集的结构
            df = next(iter(session.datasets.values()))
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

            # 如果有分组列，使用比较分析
            if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                group_col = categorical_cols[0]
                unique_groups = df[group_col].dropna().nunique()

                if unique_groups == 2:
                    return PlanPhase(
                        phase_type="statistical_test",
                        description="两组比较分析",
                        actions=[
                            PlanAction(
                                action_type="statistical_analysis",
                                skill="complete_comparison",
                                parameters={
                                    "dataset_name": list(session.datasets.keys())[0],
                                    "value_column": numeric_cols[0],
                                    "group_column": group_col,
                                },
                                description="执行完整的两组比较分析",
                            )
                        ],
                        status=PlanStatus.PENDING,
                    )
                elif unique_groups >= 3:
                    return PlanPhase(
                        phase_type="statistical_test",
                        description="多组比较分析 (ANOVA)",
                        actions=[
                            PlanAction(
                                action_type="statistical_analysis",
                                skill="complete_anova",
                                parameters={
                                    "dataset_name": list(session.datasets.keys())[0],
                                    "value_column": numeric_cols[0],
                                    "group_column": group_col,
                                },
                                description="执行完整的 ANOVA 分析",
                            )
                        ],
                        status=PlanStatus.PENDING,
                    )

            # 如果有多个数值列，使用相关性分析
            if len(numeric_cols) >= 2:
                return PlanPhase(
                    phase_type="statistical_test",
                    description="相关性分析",
                    actions=[
                        PlanAction(
                            action_type="statistical_analysis",
                            skill="correlation_analysis",
                            parameters={
                                "dataset_name": list(session.datasets.keys())[0],
                                "columns": numeric_cols[:5],  # 最多5列
                            },
                            description="执行相关性分析",
                        )
                    ],
                    status=PlanStatus.PENDING,
                )

        # 默认：描述性统计
        return PlanPhase(
            phase_type="statistical_test",
            description="描述性统计分析",
            actions=[
                PlanAction(
                    action_type="summary",
                    skill="data_summary",
                    parameters={},
                    description="生成描述性统计",
                )
            ],
            status=PlanStatus.PENDING,
        )

    async def validate_plan(
        self,
        session: Session,
        plan: ExecutionPlan,
    ) -> dict[str, Any]:
        """验证执行计划的合理性。

        Args:
            session: 会话对象
            plan: 要验证的计划

        Returns:
            验证结果，包含 is_valid 和 suggestions
        """
        validation_result: dict[str, Any] = {
            "is_valid": True,
            "suggestions": [],
            "errors": [],
        }

        # 检查是否有阶段
        if not plan.phases:
            validation_result["is_valid"] = False
            validation_result["errors"].append("计划没有定义任何阶段")
            return validation_result

        # 检查数据集是否存在
        for phase in plan.phases:
            for action in phase.actions:
                if "dataset_name" in action.parameters:
                    dataset_name = action.parameters["dataset_name"]
                    if dataset_name not in session.datasets:
                        validation_result["is_valid"] = False
                        validation_result["errors"].append(f"数据集 '{dataset_name}' 不存在")

        # 生成建议
        if len(plan.phases) > 5:
            validation_result["suggestions"].append("计划包含较多阶段，考虑合并以提高效率")

        return validation_result

    async def revise_plan(
        self,
        session: Session,
        plan: ExecutionPlan,
        feedback: str,
    ) -> ExecutionPlan:
        """根据反馈修正执行计划。

        Args:
            session: 会话对象
            plan: 原始计划
            feedback: 用户反馈

        Returns:
            修正后的计划
        """
        # 记录反馈
        plan.add_suggestion(feedback)

        # 简单实现：标记为需要修订
        plan.status = PlanStatus.REQUIRES_REVISION

        return plan
