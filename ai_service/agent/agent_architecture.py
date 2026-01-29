"""
Agent架构设计
基于LangChain/LangGraph的智能分析Agent系统

这是一个预留架构设计，用于未来的多步骤自动分析功能
"""
from typing import TypedDict, Annotated, List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json


# ==================== 状态定义 ====================

class AgentState(TypedDict):
    """
    Agent状态定义
    用于LangGraph状态管理
    """
    # 输入
    user_query: str  # 用户原始查询
    data_context: Dict[str, Any]  # 数据上下文
    
    # 规划
    plan: List[str]  # 执行计划
    current_step: int  # 当前步骤索引
    
    # 执行
    tool_calls: List[Dict[str, Any]]  # 工具调用记录
    tool_results: List[Dict[str, Any]]  # 工具执行结果
    
    # 输出
    intermediate_results: List[Dict[str, Any]]  # 中间结果
    final_report: Optional[str]  # 最终报告
    
    # 元数据
    cost_accumulated: float  # 累计成本
    execution_time: float  # 执行时间
    errors: List[str]  # 错误记录


# ==================== 工具定义 ====================

class ToolType(Enum):
    """工具类型枚举"""
    DATA_ANALYSIS = "data_analysis"
    CHART_GENERATION = "chart_generation"
    STATISTICAL_TEST = "statistical_test"
    LITERATURE_SEARCH = "literature_search"
    REPORT_GENERATION = "report_generation"
    CODE_EXECUTION = "code_execution"


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[Callable] = None
    
    def to_openai_function(self) -> Dict[str, Any]:
        """转换为OpenAI函数格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


# 预设工具库
DEFAULT_TOOLS = {
    "analyze_data": Tool(
        name="analyze_data",
        description="对数据进行深入分析，包括描述性统计、分布分析、异常值检测等",
        parameters={
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": ["descriptive", "distribution", "correlation", "outlier"],
                    "description": "分析类型"
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要分析的列"
                }
            },
            "required": ["analysis_type"]
        }
    ),
    
    "generate_chart": Tool(
        name="generate_chart",
        description="生成数据可视化图表",
        parameters={
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "scatter", "histogram", "box", "heatmap"],
                    "description": "图表类型"
                },
                "x_column": {"type": "string", "description": "X轴列"},
                "y_column": {"type": "string", "description": "Y轴列"},
                "color_column": {"type": "string", "description": "颜色分组列"}
            },
            "required": ["chart_type", "x_column", "y_column"]
        }
    ),
    
    "statistical_test": Tool(
        name="statistical_test",
        description="执行统计检验",
        parameters={
            "type": "object",
            "properties": {
                "test_name": {
                    "type": "string",
                    "enum": ["t_test", "anova", "chi_square", "mann_whitney", "kruskal_wallis"],
                    "description": "检验名称"
                },
                "group_column": {"type": "string", "description": "分组列"},
                "value_column": {"type": "string", "description": "值列"}
            },
            "required": ["test_name", "group_column", "value_column"]
        }
    ),
    
    "search_literature": Tool(
        name="search_literature",
        description="搜索相关文献",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    ),
    
    "generate_report": Tool(
        name="generate_report",
        description="生成分析报告",
        parameters={
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "enum": ["summary", "detailed", "publication"],
                    "description": "报告类型"
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "报告章节"
                }
            },
            "required": ["report_type"]
        }
    )
}


# ==================== Agent节点定义 ====================

class AgentNode:
    """
    Agent节点基类
    用于LangGraph工作流
    """
    
    def __init__(self, name: str, llm_client=None):
        self.name = name
        self.llm_client = llm_client
    
    async def execute(self, state: AgentState) -> AgentState:
        """执行节点逻辑"""
        raise NotImplementedError


class PlanningNode(AgentNode):
    """
    规划节点
    分析用户请求，制定执行计划
    """
    
    PLANNING_PROMPT = """你是一个科研数据分析规划专家。

用户请求：{user_query}

可用工具：
{available_tools}

请制定一个详细的分析计划，步骤要具体可执行。

以JSON格式返回计划：
{{
    "plan": [
        "步骤1描述",
        "步骤2描述",
        ...
    ],
    "reasoning": "规划理由"
}}"""
    
    async def execute(self, state: AgentState) -> AgentState:
        """制定分析计划"""
        # 构建可用工具描述
        tools_desc = "\n".join([
            f"- {name}: {tool.description}"
            for name, tool in DEFAULT_TOOLS.items()
        ])
        
        prompt = self.PLANNING_PROMPT.format(
            user_query=state["user_query"],
            available_tools=tools_desc
        )
        
        messages = [
            {"role": "system", "content": "你是一个科研数据分析规划专家。"},
            {"role": "user", "content": prompt}
        ]
        
        # 调用LLM生成计划
        response = await self.llm_client.chat_completion(messages)
        
        try:
            content = response["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            plan_data = json.loads(content.strip())
            state["plan"] = plan_data.get("plan", [])
            state["current_step"] = 0
            
        except json.JSONDecodeError:
            state["plan"] = ["分析数据", "生成可视化", "生成报告"]
            state["current_step"] = 0
            state["errors"].append("Failed to parse plan, using default")
        
        return state


class ToolSelectionNode(AgentNode):
    """
    工具选择节点
    根据当前步骤选择合适的工具
    """
    
    TOOL_SELECTION_PROMPT = """当前分析步骤：{current_step}

用户请求：{user_query}

可用工具：
{available_tools}

请选择最合适的工具，并指定参数。

以JSON格式返回：
{{
    "tool_name": "工具名称",
    "parameters": {{参数对象}},
    "reasoning": "选择理由"
}}"""
    
    async def execute(self, state: AgentState) -> AgentState:
        """选择并调用工具"""
        if state["current_step"] >= len(state["plan"]):
            return state
        
        current_step_desc = state["plan"][state["current_step"]]
        
        # 构建工具描述
        tools_json = [
            tool.to_openai_function()
            for tool in DEFAULT_TOOLS.values()
        ]
        
        messages = [
            {"role": "system", "content": "你是一个工具选择专家。"},
            {"role": "user", "content": f"当前步骤：{current_step_desc}\n\n请选择合适的工具。"}
        ]
        
        # 使用tool calling
        response = await self.llm_client.chat_completion_with_tools(
            messages=messages,
            tools=tools_json
        )
        
        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                state["tool_calls"].append({
                    "step": state["current_step"],
                    "tool": tool_call["function"]["name"],
                    "parameters": json.loads(tool_call["function"]["arguments"])
                })
        
        return state


class ExecutionNode(AgentNode):
    """
    执行节点
    执行选定的工具
    """
    
    async def execute(self, state: AgentState) -> AgentState:
        """执行工具调用"""
        if not state["tool_calls"]:
            return state
        
        last_call = state["tool_calls"][-1]
        tool_name = last_call["tool"]
        parameters = last_call["parameters"]
        
        # 这里应该调用实际的工具
        # 目前返回模拟结果
        result = {
            "tool": tool_name,
            "parameters": parameters,
            "status": "completed",
            "result": f"Mock result for {tool_name}"
        }
        
        state["tool_results"].append(result)
        state["intermediate_results"].append(result)
        state["current_step"] += 1
        
        return state


class EvaluationNode(AgentNode):
    """
    评估节点
    评估当前结果，决定下一步
    """
    
    async def execute(self, state: AgentState) -> AgentState:
        """评估执行结果"""
        # 检查是否需要继续执行
        if state["current_step"] >= len(state["plan"]):
            # 计划已完成
            pass
        
        return state


class ReportGenerationNode(AgentNode):
    """
    报告生成节点
    整合所有结果生成最终报告
    """
    
    REPORT_PROMPT = """基于以下分析结果生成报告：

执行计划：
{plan}

工具调用结果：
{tool_results}

中间结果：
{intermediate_results}

请生成一份完整的分析报告，包括：
1. 执行摘要
2. 详细分析结果
3. 可视化建议
4. 结论和建议"""
    
    async def execute(self, state: AgentState) -> AgentState:
        """生成最终报告"""
        prompt = self.REPORT_PROMPT.format(
            plan="\n".join([f"{i+1}. {step}" for i, step in enumerate(state["plan"])]),
            tool_results=json.dumps(state["tool_results"], indent=2, ensure_ascii=False),
            intermediate_results=json.dumps(state["intermediate_results"], indent=2, ensure_ascii=False)
        )
        
        messages = [
            {"role": "system", "content": "你是一个科研报告撰写专家。"},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.llm_client.chat_completion(messages)
        state["final_report"] = response["content"]
        
        return state


# ==================== LangGraph工作流 ====================

class AnalysisWorkflow:
    """
    分析工作流
    使用LangGraph构建的分析Agent
    
    使用示例（预留）：
    
    ```python
    from langgraph.graph import StateGraph, END
    
    workflow = AnalysisWorkflow(llm_client)
    
    # 定义图
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("plan", workflow.planning_node)
    graph.add_node("select_tool", workflow.tool_selection_node)
    graph.add_node("execute", workflow.execution_node)
    graph.add_node("evaluate", workflow.evaluation_node)
    graph.add_node("report", workflow.report_node)
    
    # 添加边
    graph.add_edge("plan", "select_tool")
    graph.add_edge("select_tool", "execute")
    graph.add_edge("execute", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        workflow.should_continue,
        {True: "select_tool", False: "report"}
    )
    graph.add_edge("report", END)
    
    # 编译
    app = graph.compile()
    
    # 执行
    result = await app.ainvoke(initial_state)
    ```
    """
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.planning_node = PlanningNode("plan", llm_client)
        self.tool_selection_node = ToolSelectionNode("select_tool", llm_client)
        self.execution_node = ExecutionNode("execute", llm_client)
        self.evaluation_node = EvaluationNode("evaluate", llm_client)
        self.report_node = ReportGenerationNode("report", llm_client)
    
    def should_continue(self, state: AgentState) -> bool:
        """判断是否继续执行"""
        return state["current_step"] < len(state["plan"])
    
    def create_initial_state(
        self,
        user_query: str,
        data_context: Dict[str, Any]
    ) -> AgentState:
        """创建初始状态"""
        return {
            "user_query": user_query,
            "data_context": data_context,
            "plan": [],
            "current_step": 0,
            "tool_calls": [],
            "tool_results": [],
            "intermediate_results": [],
            "final_report": None,
            "cost_accumulated": 0.0,
            "execution_time": 0.0,
            "errors": []
        }


# ==================== Agent管理器 ====================

class AgentManager:
    """
    Agent管理器
    管理多个分析Agent实例
    """
    
    def __init__(self):
        self.agents: Dict[str, AnalysisWorkflow] = {}
        self.active_sessions: Dict[str, AgentState] = {}
    
    def create_agent(self, agent_id: str, llm_client) -> AnalysisWorkflow:
        """创建新的Agent"""
        agent = AnalysisWorkflow(llm_client)
        self.agents[agent_id] = agent
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[AnalysisWorkflow]:
        """获取Agent实例"""
        return self.agents.get(agent_id)
    
    def remove_agent(self, agent_id: str):
        """移除Agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
        if agent_id in self.active_sessions:
            del self.active_sessions[agent_id]
    
    def save_session(self, agent_id: str, state: AgentState):
        """保存会话状态"""
        self.active_sessions[agent_id] = state
    
    def get_session(self, agent_id: str) -> Optional[AgentState]:
        """获取会话状态"""
        return self.active_sessions.get(agent_id)


# 全局Agent管理器
_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    """获取全局Agent管理器"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager
