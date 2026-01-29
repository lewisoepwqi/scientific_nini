# 科研数据分析AI服务

为科研数据分析Web工具提供AI能力的后端服务。

## 功能特性

### 已实现功能

1. **智能图表推荐**
   - 分析Excel数据结构
   - 推荐最适合的图表类型
   - 解释推荐理由
   - 提醒可视化陷阱

2. **AI辅助数据分析**
   - 数据解读和洞察
   - 统计方法建议
   - 结果解释（用通俗语言）

3. **实验设计助手**
   - 样本量计算建议
   - 统计功效分析
   - 实验设计优化

4. **多组学数据AI分析**
   - 单细胞数据解读
   - 基因表达模式识别
   - 生物学意义解释

### 预留功能

5. **Agent能力**（LangChain/LangGraph架构预留）
   - 多步骤分析流程
   - 自动选择分析方法
   - 生成完整分析报告

## 技术架构

```
ai_service/
├── core/                    # 核心模块
│   ├── llm_client.py        # LLM客户端封装
│   └── prompts.py           # Prompt模板库
├── services/                # 服务层
│   └── ai_analysis_service.py  # AI分析服务
├── api/                     # API层
│   └── endpoints.py         # FastAPI端点
├── agent/                   # Agent架构（预留）
│   └── agent_architecture.py
├── docs/                    # 文档
│   └── cost_estimation.md   # 成本估算
├── main.py                  # FastAPI主入口
├── .env.example             # 环境变量示例
└── README.md                # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install openai fastapi uvicorn pydantic
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑.env文件，填入你的OpenAI API Key
```

### 3. 启动服务

```bash
python -m ai_service.main
```

服务将在 http://localhost:8000 启动

### 4. 查看API文档

访问 http://localhost:8000/docs 查看交互式API文档

## API端点

### 图表推荐

```bash
# 非流式
POST /api/ai/chart/recommend

# 流式
POST /api/ai/chart/recommend/stream
```

请求示例：
```json
{
  "data_description": "包含100个样本的基因表达数据",
  "data_sample": "SampleID,GeneA,GeneB,Group\nS001,2.5,3.1,Control\nS002,2.8,3.5,Treatment",
  "data_types": {
    "SampleID": "string",
    "GeneA": "float",
    "GeneB": "float",
    "Group": "categorical"
  },
  "statistics": {
    "row_count": 100,
    "column_count": 4
  },
  "user_requirement": "比较不同组的基因表达差异"
}
```

### 数据分析

```bash
# 非流式
POST /api/ai/data/analyze

# 流式
POST /api/ai/data/analyze/stream
```

请求示例：
```json
{
  "context": "研究药物对基因表达的影响",
  "data_description": "RNA-seq数据，包含对照组和治疗组",
  "statistics": {
    "control_mean": 2.5,
    "treatment_mean": 3.2,
    "p_value": 0.003
  },
  "question": "结果有什么统计学意义？"
}
```

### 实验设计

```bash
# 非流式
POST /api/ai/experiment/design

# 流式
POST /api/ai/experiment/design/stream
```

请求示例：
```json
{
  "background": "研究新药对肿瘤生长的抑制效果",
  "objective": "评估药物疗效",
  "study_type": "随机对照试验",
  "primary_endpoint": "肿瘤体积变化",
  "effect_size": 0.5,
  "alpha": 0.05,
  "power": 0.8,
  "test_type": "two-sided",
  "num_groups": 2
}
```

### 成本统计

```bash
GET /api/ai/cost/summary
POST /api/ai/cost/reset
```

## 成本估算

详见 [docs/cost_estimation.md](docs/cost_estimation.md)

### 月度成本预估（轻度使用）

| 模型 | 月度成本 |
|------|---------|
| GPT-4 | ~$25 |
| GPT-4 Turbo | ~$13 |
| GPT-3.5 Turbo | ~$1.4 |

## 流式响应

所有主要端点都支持流式响应，使用SSE格式：

```javascript
const eventSource = new EventSource('/api/ai/data/analyze/stream');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.chunk) {
    // 处理文本片段
    console.log(data.chunk);
  }
  if (data.done) {
    eventSource.close();
  }
};
```

## 前端集成示例

```javascript
// 图表推荐
async function recommendChart(dataInfo) {
  const response = await fetch('/api/ai/chart/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataInfo)
  });
  return await response.json();
}

// 流式数据分析
async function analyzeDataStream(dataInfo, onChunk) {
  const response = await fetch('/api/ai/data/analyze/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dataInfo)
  });
  
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    const lines = text.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.chunk) onChunk(data.chunk);
      }
    }
  }
}
```

## 配置选项

### 模型选择

在 `.env` 文件中配置：

```bash
# 选项: gpt-4, gpt-4-turbo, gpt-3.5-turbo
OPENAI_MODEL=gpt-4-turbo
```

### 温度参数

代码中配置（`core/llm_client.py`）：

```python
config = LLMConfig(
    temperature=0.3,  # 科研场景建议较低温度
    max_tokens=4096
)
```

## 错误处理

服务实现了自动重试机制：
- 最多重试3次
- 指数退避策略
- 区分可重试错误和致命错误

## 成本追踪

内置成本追踪功能：

```python
from ai_service import get_ai_service

service = get_ai_service()
summary = service.get_cost_summary()
print(summary)
# {
#     "total_cost_usd": 12.58,
#     "total_calls": 200,
#     "average_cost_per_call": 0.063
# }
```

## 本地模型部署（预留）

支持本地模型部署接口，可在 `core/llm_client.py` 中扩展：

```python
class ModelProvider(Enum):
    OPENAI = "openai"
    LOCAL = "local"  # 预留
```

## 开发计划

- [x] LLM客户端封装
- [x] Prompt模板库
- [x] 图表推荐功能
- [x] 数据分析功能
- [x] 实验设计功能
- [x] 多组学分析功能
- [x] 流式响应支持
- [x] 成本追踪
- [ ] Agent多步骤分析
- [ ] 本地模型支持
- [ ] 缓存机制
- [ ] 用户反馈收集

## 许可证

MIT License
