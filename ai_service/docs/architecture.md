# AI服务架构设计文档

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端应用 (React/Vue)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP/WebSocket
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI 后端服务                                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         路由层 (Router)                                │
│  │  /api/ai/chart/*    /api/ai/data/*    /api/ai/experiment/*           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         API端点 (Endpoints)                            │
│  │  • recommend_chart      • analyze_data      • design_experiment       │  │
│  │  • recommend_chart_stream (流式)                                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         服务层 (Services)                              │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    AIAnalysisService                            │  │  │
│  │  │  • recommend_chart()    • analyze_data()    • design_experiment()│  │  │
│  │  │  • get_statistical_advice()    • analyze_omics()                │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         核心层 (Core)                                  │
│  │  ┌───────────────────┐    ┌───────────────────┐    ┌───────────────┐  │  │
│  │  │   LLMClient       │    │  PromptManager    │    │  CostTracker  │  │  │
│  │  │  • chat_completion│    │  • get_prompt()   │    │  • track()    │  │  │
│  │  │  • stream()       │    │  • templates      │    │  • summary()  │  │  │
│  │  │  • retry logic    │    │                   │    │               │  │  │
│  │  └───────────────────┘    └───────────────────┘    └───────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Agent层 (预留)                                 │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │                    AnalysisWorkflow (LangGraph)                 │  │  │
│  │  │  • PlanningNode → ToolSelectionNode → ExecutionNode → Report   │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ OpenAI API / Local Model
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              外部服务                                        │
│  ┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐   │
│  │   OpenAI API      │    │   Local LLM       │    │   Literature DB   │   │
│  │  • GPT-4          │    │  • LLaMA          │    │  • PubMed         │   │
│  │  • GPT-4 Turbo    │    │  • ChatGLM        │    │  • Google Scholar │   │
│  │  • GPT-3.5 Turbo  │    │  • etc.           │    │                   │   │
│  └───────────────────┘    └───────────────────┘    └───────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 模块详细设计

### 1. LLMClient 模块

**职责**：封装所有LLM调用，提供统一的接口

**核心功能**：
- 支持多种模型提供商（OpenAI、Azure、本地模型）
- 自动重试机制（指数退避）
- 流式响应支持
- 工具调用支持（Function Calling）
- 成本追踪

**类图**：
```
┌─────────────────────────────────────────┐
│              LLMClient                  │
├─────────────────────────────────────────┤
│ - config: LLMConfig                     │
│ - client: AsyncOpenAI                   │
│ - total_cost: float                     │
│ - cost_history: List[CostInfo]          │
├─────────────────────────────────────────┤
│ + chat_completion()                     │
│ + chat_completion_stream()              │
│ + chat_completion_with_tools()          │
│ + get_cost_summary()                    │
│ + reset_cost_tracking()                 │
└─────────────────────────────────────────┘
```

**设计模式**：
- 单例模式：全局共享一个LLMClient实例
- 策略模式：支持切换不同模型提供商

### 2. PromptManager 模块

**职责**：管理所有AI Prompt模板

**核心功能**：
- 预定义专业Prompt模板
- 动态变量替换
- 多语言支持（主要是中文）
- 版本管理

**Prompt类型**：
1. **图表推荐Prompt**
   - System Prompt：定义数据可视化专家角色
   - User Prompt：包含数据描述、样本、统计信息
   - 输出格式：JSON结构化推荐

2. **数据分析Prompt**
   - System Prompt：定义数据分析师角色
   - User Prompt：包含数据背景、统计结果
   - 输出格式：自由文本分析

3. **实验设计Prompt**
   - System Prompt：定义实验设计专家角色
   - User Prompt：包含研究背景、统计参数
   - 输出格式：结构化设计建议

4. **统计建议Prompt**
   - System Prompt：定义统计学专家角色
   - User Prompt：包含分析目标、变量信息
   - 输出格式：方法建议 + 代码示例

5. **多组学分析Prompt**
   - System Prompt：定义生物信息学专家角色
   - User Prompt：包含组学数据描述、分析目标
   - 输出格式：分析流程建议

### 3. AIAnalysisService 模块

**职责**：提供高层AI分析功能

**核心方法**：
```python
class AIAnalysisService:
    async def recommend_chart(...) -> Dict  # 图表推荐
    async def analyze_data(...) -> Dict      # 数据分析
    async def design_experiment(...) -> Dict # 实验设计
    async def get_statistical_advice(...) -> Dict  # 统计建议
    async def analyze_omics(...) -> Dict     # 组学分析
```

**设计模式**：
- 外观模式：封装底层LLM调用，提供简洁接口
- 工厂模式：创建不同类型的分析服务

### 4. Agent架构（预留）

**设计目标**：实现多步骤自动分析

**核心组件**：
1. **StateGraph**（LangGraph）
   - 定义分析工作流
   - 管理状态流转

2. **Nodes**
   - PlanningNode：制定分析计划
   - ToolSelectionNode：选择分析工具
   - ExecutionNode：执行工具
   - EvaluationNode：评估结果
   - ReportGenerationNode：生成报告

3. **Tools**
   - analyze_data：数据分析
   - generate_chart：图表生成
   - statistical_test：统计检验
   - search_literature：文献检索
   - generate_report：报告生成

**工作流**：
```
User Query → Planning → Tool Selection → Execution → Evaluation
                                                ↓
Report ← Report Generation ←─────────────── Continue?
```

## 数据流设计

### 图表推荐流程

```
用户上传Excel
    │
    ▼
前端提取数据特征
    │
    ▼
POST /api/ai/chart/recommend
    │
    ▼
AIAnalysisService.recommend_chart()
    │
    ▼
PromptManager.get_chart_recommendation_prompt()
    │
    ▼
LLMClient.chat_completion()
    │
    ▼
OpenAI API
    │
    ▼
解析JSON响应
    │
    ▼
返回推荐结果
```

### 流式响应流程

```
用户请求
    │
    ▼
POST /api/ai/data/analyze/stream
    │
    ▼
StreamingResponse
    │
    ▼
ai_service.analyze_data_stream()
    │
    ▼
LLMClient.chat_completion_stream()
    │
    ▼
OpenAI API (stream=True)
    │
    ▼
实时返回文本片段 (SSE)
    │
    ▼
前端实时渲染
```

## 错误处理策略

### 重试机制

```python
for attempt in range(max_retries):
    try:
        response = await api_call()
        return response
    except RateLimitError:
        # 指数退避
        await sleep(retry_delay * (2 ** attempt))
    except APIError:
        # 固定间隔重试
        await sleep(retry_delay)
    except TimeoutError:
        # 增加超时时间重试
        timeout *= 1.5
```

### 错误分类

| 错误类型 | 处理方式 | 是否重试 |
|---------|---------|---------|
| RateLimitError | 指数退避 | 是 |
| APIError | 固定间隔重试 | 是 |
| TimeoutError | 增加超时时间 | 是 |
| AuthenticationError | 立即报错 | 否 |
| InvalidRequestError | 立即报错 | 否 |

## 成本优化策略

### 1. 模型选择策略

```python
MODEL_SELECTION = {
    "chart_recommendation": "gpt-3.5-turbo",  # 简单任务
    "data_analysis": "gpt-4-turbo",            # 中等复杂度
    "experiment_design": "gpt-4-turbo",        # 需要准确性
    "omics_analysis": "gpt-4",                  # 复杂任务
}
```

### 2. Prompt优化

- 精简System Prompt
- 数据采样（只发送必要数据）
- 结果缓存

### 3. 批量处理

将多个小请求合并为一个大请求

### 4. 本地模型（预留）

高频任务使用本地部署模型

## 安全设计

### API Key管理

- 环境变量存储
- 不记录到日志
- 定期轮换

### 输入验证

- Pydantic模型验证
- SQL注入防护
- XSS防护

### 访问控制

- JWT认证（预留）
- 速率限制
- IP白名单（可选）

## 扩展性设计

### 新模型支持

```python
class ModelProvider(Enum):
    OPENAI = "openai"
    AZURE = "azure"
    LOCAL = "local"       # 预留
    ANTHROPIC = "anthropic"  # 预留
```

### 新功能添加

1. 在 `prompts.py` 添加新Prompt模板
2. 在 `ai_analysis_service.py` 添加新方法
3. 在 `endpoints.py` 添加新端点

### Agent扩展

```python
# 添加新工具
DEFAULT_TOOLS["new_tool"] = Tool(
    name="new_tool",
    description="...",
    parameters={...}
)

# 添加新节点
class NewNode(AgentNode):
    async def execute(self, state: AgentState) -> AgentState:
        # 实现逻辑
        return state
```

## 性能优化

### 异步处理

所有API调用使用 `async/await`

### 连接池

OpenAI客户端内部管理连接池

### 缓存（预留）

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_analysis(key):
    return cached_result
```

## 监控与日志

### 成本监控

- 实时成本追踪
- 月度报表
- 预算告警

### 性能监控

- 响应时间
- Token使用量
- 错误率

### 日志记录

- 请求/响应日志
- 错误日志
- 审计日志

## 部署架构

### Docker部署

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 环境配置

```yaml
# docker-compose.yml
version: '3.8'
services:
  ai-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_MODEL=gpt-4-turbo
    env_file:
      - .env
```

## 未来规划

### 短期（1-2个月）

- [x] 基础AI功能实现
- [x] 流式响应支持
- [x] 成本追踪
- [ ] 缓存机制
- [ ] 用户反馈收集

### 中期（3-6个月）

- [ ] Agent多步骤分析
- [ ] 本地模型支持
- [ ] 文献检索集成
- [ ] 报告模板系统

### 长期（6个月以上）

- [ ] 多模态分析（图片、PDF）
- [ ] 知识图谱集成
- [ ] 协作分析功能
- [ ] 模型微调
