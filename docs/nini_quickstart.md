# Nini 快速开始

本文档用于本地首次跑通 Nini。

## 1. 环境要求

- Python `3.12+`
- Node.js `18+`（仅前端构建需要）
- 可用模型路由之一（多选时按优先级自动降级）：
  - OpenAI API Key
  - Anthropic API Key
  - Moonshot AI (Kimi) API Key
  - Kimi Coding API Key
  - 智谱 AI (GLM) API Key
  - DeepSeek API Key
  - 阿里百炼（通义千问）API Key
  - 本地 Ollama（默认地址 `http://localhost:11434`）
- R 环境（可选，仅使用 `run_r_code` 技能时需要）

## 2. 安装

```bash
pip install -e .[dev]
```

`dev` 依赖组已包含报告 PDF 导出依赖 `weasyprint`。

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
# 可选：试用模式内嵌密钥（发布包建议构建机注入）
# NINI_TRIAL_API_KEY=sk-...

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
`weasyprint（报告 PDF 导出，可选）` 是可选项，缺失会显示 `WARN`，仅影响报告 PDF 导出。

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

## 8. Recipe Center（MVP）

首页现已提供 `Recipe Center`，用于把高频科研任务直接收敛成可执行模板。

当前内置 3 个 Recipe：

- `文献综述提纲`：适合开题前快速整理研究现状、检索方向和综述结构。
- `实验设计与统计计划`：适合把研究问题转成分组、终点和统计分析路径。
- `结果解读与下一步建议`：适合分析完成后整理主要发现、讨论要点和后续动作。

使用方式：

1. 打开首页，直接在 `Recipe Center` 中选择模板。
2. 填写最少必要输入，点击“以模板启动”。
3. 前端会创建 `deep task`，并在会话区展示当前步骤、重试状态与下一步提示。
4. 工作区会自动写入一份 `recipe_<recipe_id>_request.md`，用于记录本次模板输入摘要。

推荐入口：

- 如果你在输入框首句中命中模板触发词（如“文献综述”“实验设计”“结果解读”），输入区上方会出现可见推荐条。
- 你可以选择“按模板执行”，也可以继续自由对话，推荐不会强制覆盖普通会话。

回退方式：

- 如需回到普通对话，直接忽略推荐条或新建自由会话即可。
- 若模板任务失败，MVP 阶段只保留最小回退：提示当前阻塞原因、记录重试次数，并要求用户补充缺失上下文后再次发起。

## 9. 常见问题

- 提示没有可用模型：检查 `.env` 是否设置 API Key，或确认 Ollama 已启动。
- 上传失败：检查文件扩展名是否为 `csv/xlsx/xls/tsv/txt`。
- 图表导出失败：确认安装了 `kaleido`（已包含在依赖中）。
- 报告 PDF 导出失败：源码环境优先执行 `pip install -e .[dev]`（如仅补装可用 `pip install -e .[pdf]`）；发布包环境执行 `pip install nini[pdf]`。
