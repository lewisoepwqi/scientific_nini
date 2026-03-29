# 配置说明

Nini 使用 `pydantic-settings` 加载配置，默认读取项目根目录 `.env`，环境变量前缀为 `NINI_`。

## 加载优先级

1. 进程环境变量
2. `.env` 文件
3. 代码默认值

## 基础配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_DEBUG` | `false` | 是否启用调试日志 |
| `NINI_DATA_DIR` | `./data` | 数据根目录（上传、会话、数据库） |

## 模型配置

Nini 支持多种模型提供商，按优先级自动路由，失败自动降级。

### 打包版内置 / 试用密钥

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_TRIAL_API_KEY` | 空 | 试用模式使用的内嵌密钥；源码模式可写在 `.env`，Windows 发布版建议在构建机环境变量中注入 |
| `NINI_BUILTIN_DASHSCOPE_API_KEY` | 空 | “系统内置”模型使用的内嵌阿里百炼 Key；Windows 发布版建议仅在构建机注入 |

### 国际模型

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_OPENAI_API_KEY` | 空 | OpenAI Key |
| `NINI_OPENAI_BASE_URL` | 空 | OpenAI 兼容地址（可选） |
| `NINI_OPENAI_MODEL` | `gpt-4o` | OpenAI 模型 |
| `NINI_ANTHROPIC_API_KEY` | 空 | Anthropic Key |
| `NINI_ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude 模型 |

### 国产模型

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_MOONSHOT_API_KEY` | 空 | Moonshot AI (Kimi) Key |
| `NINI_MOONSHOT_MODEL` | `moonshot-v1-8k` | Moonshot 模型（可选 `moonshot-v1-32k`、`moonshot-v1-128k`） |
| `NINI_KIMI_CODING_API_KEY` | 空 | Kimi Coding Key |
| `NINI_KIMI_CODING_BASE_URL` | `https://api.kimi.com/coding/v1` | Kimi Coding OpenAI 兼容地址 |
| `NINI_KIMI_CODING_MODEL` | `kimi-for-coding` | Kimi Coding 模型 |
| `NINI_ZHIPU_API_KEY` | 空 | 智谱 AI Key |
| `NINI_ZHIPU_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | 智谱 OpenAI 兼容地址（Coding Plan 可改为 `https://open.bigmodel.cn/api/coding/paas/v4`） |
| `NINI_ZHIPU_MODEL` | `glm-4` | 智谱模型（可选 `glm-4.7`、`glm-4.6`、`glm-4.5`、`glm-4.5-air`、`glm-4-plus`、`glm-4-flash`） |
| `NINI_DEEPSEEK_API_KEY` | 空 | DeepSeek Key |
| `NINI_DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型（可选 `deepseek-coder`、`deepseek-reasoner`） |
| `NINI_DASHSCOPE_API_KEY` | 空 | 阿里百炼（通义千问）Key |
| `NINI_DASHSCOPE_MODEL` | `qwen-plus` | 通义千问模型（可选 `qwen-turbo`、`qwen-max`） |

### 本地模型

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服务地址 |
| `NINI_OLLAMA_MODEL` | `qwen2.5:7b` | Ollama 模型 |

## LLM 通用参数

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_LLM_TEMPERATURE` | `0.3` | 采样温度 |
| `NINI_LLM_MAX_TOKENS` | `4096` | 单次最大输出 token |
| `NINI_LLM_MAX_RETRIES` | `3` | 模型重试次数 |
| `NINI_LLM_TIMEOUT` | `120` | 单次模型 HTTP 请求超时（秒） |
| `NINI_LLM_TRUST_ENV_PROXY` | `false` | 是否信任 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量 |

## Agent 与沙箱

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_AGENT_MAX_ITERATIONS` | `0` | 单轮对话最大 ReAct 迭代次数；`<=0` 表示不限制 |
| `NINI_AGENT_ACTIVE_EXECUTION_TIMEOUT_SECONDS` | `null` | Agent 主动执行预算（秒），不计 `ask_user_question` 等人工等待；未配置时回退到 `NINI_AGENT_MAX_TIMEOUT_SECONDS` |
| `NINI_AGENT_RUN_WALL_CLOCK_TIMEOUT_SECONDS` | `0` | Agent 整轮 wall-clock 兜底超时（秒），包含人工等待；`0` 表示不限制 |
| `NINI_AGENT_MAX_TIMEOUT_SECONDS` | `300` | 兼容旧字段；现仅作为主动执行预算的回退值 |
| `NINI_SANDBOX_TIMEOUT` | `60` | `run_code` 超时时间（秒），含代码执行与 DataFrame 序列化时间 |
| `NINI_SANDBOX_MAX_MEMORY_MB` | `512` | `run_code` 内存上限（MB） |
| `NINI_SANDBOX_IMAGE_EXPORT_TIMEOUT` | `60` | 图片导出（kaleido）专用超时（秒） |

### Agent 超时分层建议

- `NINI_LLM_TIMEOUT`：单次模型 HTTP 请求超时。建议保持 `60~180` 秒。
- `NINI_SANDBOX_TIMEOUT` / 其它工具级超时：单次工具执行上限。建议按工具类型分别设置，不要与 Agent 总预算混用。
- `NINI_AGENT_ACTIVE_EXECUTION_TIMEOUT_SECONDS`：限制 Agent 实际推理、工具编排、模型调用所消耗的时间，不包含等待用户回答。
- `NINI_AGENT_RUN_WALL_CLOCK_TIMEOUT_SECONDS`：可选兜底，用于防止会话在人工等待、前端离线或异常挂起时永久占用运行态。

推荐默认策略：

- 前台交互型部署：`NINI_AGENT_ACTIVE_EXECUTION_TIMEOUT_SECONDS=300`
- 含多步分析/导出任务：`NINI_AGENT_ACTIVE_EXECUTION_TIMEOUT_SECONDS=600` 或 `900`
- `NINI_AGENT_RUN_WALL_CLOCK_TIMEOUT_SECONDS` 默认保持 `0`

若需要强制回收长时间挂起的会话，可单独配置 wall-clock 兜底，例如：

```env
NINI_AGENT_ACTIVE_EXECUTION_TIMEOUT_SECONDS=600
NINI_AGENT_RUN_WALL_CLOCK_TIMEOUT_SECONDS=7200
```

上述配置表示：

- Agent 实际执行累计超过 10 分钟时终止
- 无论是否在等待用户输入，整轮会话总时长超过 2 小时时终止

## 上传配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `NINI_MAX_UPLOAD_SIZE` | `52428800` | 单文件最大字节数（50MB） |
| `NINI_ALLOWED_EXTENSIONS` | `csv,xlsx,xls,tsv,txt` | 上传允许后缀 |

## 目录结构（默认）

```text
data/
├── uploads/                 # 原始上传文件
├── sessions/{session_id}/
│   ├── memory.jsonl         # 对话与工具调用记录
│   ├── knowledge.md         # 长期知识笔记
│   └── artifacts/           # 图表/报告导出产物
└── db/nini.db               # SQLite 元数据库
```

## 最小可用 `.env` 示例

使用 OpenAI：

```env
NINI_OPENAI_API_KEY=sk-xxx
NINI_OPENAI_MODEL=gpt-4o
```

使用国产模型（以 DeepSeek 为例）：

```env
NINI_DEEPSEEK_API_KEY=sk-xxx
NINI_DEEPSEEK_MODEL=deepseek-chat
```

使用阿里百炼（通义千问）：

```env
NINI_DASHSCOPE_API_KEY=sk-xxx
NINI_DASHSCOPE_MODEL=qwen-plus
```

使用 Moonshot AI (Kimi)：

```env
NINI_MOONSHOT_API_KEY=sk-xxx
NINI_MOONSHOT_MODEL=moonshot-v1-8k
```

使用智谱 AI (GLM)：

```env
NINI_ZHIPU_API_KEY=xxx.xxx
NINI_ZHIPU_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
NINI_ZHIPU_MODEL=glm-4.7
```

使用 Kimi Coding：

```env
NINI_KIMI_CODING_API_KEY=sk-xxx
NINI_KIMI_CODING_BASE_URL=https://api.kimi.com/coding/v1
NINI_KIMI_CODING_MODEL=kimi-for-coding
```

> 提示：可同时配置多个模型，Nini 会按优先级自动路由，失败时自动降级到下一个可用模型。
