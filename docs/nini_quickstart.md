# Nini 快速开始

本文档用于本地首次跑通 Nini。

## 1. 环境要求

- Python `3.12+`
- Node.js `18+`（仅前端构建需要）
- 可用模型路由之一：
  - OpenAI API Key
  - Anthropic API Key
  - Moonshot AI (Kimi) API Key
  - 智谱 AI (GLM) API Key
  - DeepSeek API Key
  - 阿里百炼（通义千问）API Key
  - 本地 Ollama（默认地址 `http://localhost:11434`）

## 2. 安装

```bash
pip install -e .[dev]
```

## 3. 初始化 `.env`

```bash
nini init
```

覆盖已有文件：

```bash
nini init --force
```

## 4. 配置模型

至少配置一条路由（多选时按优先级自动路由，失败自动降级）：

```env
# OpenAI
NINI_OPENAI_API_KEY=sk-...
NINI_OPENAI_MODEL=gpt-4o

# Anthropic
NINI_ANTHROPIC_API_KEY=...
NINI_ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Moonshot AI (Kimi)
NINI_MOONSHOT_API_KEY=sk-...
NINI_MOONSHOT_MODEL=moonshot-v1-8k

# 智谱 AI (GLM)
NINI_ZHIPU_API_KEY=...
NINI_ZHIPU_MODEL=glm-4

# DeepSeek
NINI_DEEPSEEK_API_KEY=sk-...
NINI_DEEPSEEK_MODEL=deepseek-chat

# 阿里百炼（通义千问）
NINI_DASHSCOPE_API_KEY=sk-...
NINI_DASHSCOPE_MODEL=qwen-plus

# Ollama（默认已填，确保本地服务在运行）
NINI_OLLAMA_BASE_URL=http://localhost:11434
NINI_OLLAMA_MODEL=qwen2.5:7b
```

## 5. 运行环境检查

```bash
nini doctor
```

预期关键项：

- `Python 版本 >= 3.12` 为 `OK`
- `数据目录可写` 为 `OK`
- `至少一个模型路由可用` 为 `OK`

`前端构建产物存在` 是可选项，缺失会显示 `WARN`，不阻塞服务启动。

## 6. 启动

```bash
nini start --reload
```

访问：`http://127.0.0.1:8000`

## 7. 最小验证流程

1. 在页面上传一个 `csv/xlsx` 文件。
2. 输入：`请先预览数据并总结列类型`。
3. 输入：`对 treatment 和 control 做 t 检验`。
4. 输入：`生成 nature 风格箱线图`。
5. 输入：`生成报告并导出图表为 svg`。

如果你能看到文本流式回复、图表渲染和下载链接，链路即跑通。

## 8. 常见问题

- 提示没有可用模型：检查 `.env` 是否设置 API Key，或确认 Ollama 已启动。
- 上传失败：检查文件扩展名是否为 `csv/xlsx/xls/tsv/txt`。
- 图表导出失败：确认安装了 `kaleido`（已包含在依赖中）。
