# Nini：科研数据分析 AI Agent

[![CI](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml/badge.svg)](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml)

Nini 是一个本地优先（local-first）的科研数据分析 Agent。
用户通过对话上传并分析数据，Agent 自动调用统计、作图、清洗、代码执行与报告生成技能。

> **核心特点**：对话式交互、多模型自动路由、沙箱安全执行、零代码数据分析

## 核心能力

**统计分析**
- `t_test`、`anova`、`correlation`、`regression`、`mann_whitney`、`kruskal_wallis`、`multiple_comparison`
- 含自动降级：正态性不满足时 t_test → mann_whitney

**可视化**
- `create_chart`（7 种图表 + 6 种期刊风格）、`export_chart`

**数据处理**
- `load_dataset`、`preview_data`、`data_summary`、`clean_data`、`data_quality`、`diagnostics`

**代码执行**
- `run_code`：受限沙箱（AST 静态分析 + 受限 builtins + 进程隔离）
- `run_r_code`：R 语言沙箱执行（需本地安装 R 环境）

**网络 / 多模态**
- `fetch_url`（网页抓取）、`image_analysis`（图像分析）、`interpretation`（统计结果解读）

**任务规划**
- `task_write`：LLM 驱动的结构化任务列表，Agent 自动拆解并跟踪分析步骤

**产物生成**
- `generate_report`、`export_report`、`organize_workspace`

**基础设施**
- 对话式 WebSocket 流式交互（text / chart / data / tool_call / done 事件）
- 会话持久化：本地 `data/sessions/{session_id}`
- 多模型路由：OpenAI、Anthropic、Ollama、Moonshot、Kimi Coding、智谱、DeepSeek、阿里百炼，按优先级自动故障转移

## 项目结构

```text
scientific_nini/
├── src/nini/                 # 后端与 Agent Runtime
│   ├── agent/                # AgentRunner、模型路由、会话、任务规划
│   ├── tools/                # 全部技能实现（base、registry 及各技能文件）
│   ├── sandbox/              # Python/R 沙箱执行与安全策略
│   ├── charts/               # 图表渲染器与风格契约
│   ├── models/               # 数据模型（Schema、执行计划、用户画像）
│   ├── knowledge/            # RAG 向量检索
│   ├── memory/               # 对话历史压缩与存储
│   ├── workspace/            # 会话文件管理
│   └── api/                  # HTTP 路由与 WebSocket 端点
├── web/                      # 前端（React 18 + Vite + TypeScript + Tailwind）
├── tests/                    # 后端测试（pytest）
├── docs/                     # 使用文档
├── openspec/                 # 变更提案流程
├── data/                     # 运行时数据（会话、上传文件，gitignored）
└── pyproject.toml
```

## 系统要求

- **Python**: >= 3.12
- **Node.js**: >= 18（前端开发需要）
- **操作系统**: Linux, macOS, Windows (WSL2 推荐)
- **内存**: 建议 4GB+
- **R 环境**（可选）: 如需执行 R 代码，需本地安装 R

## 快速开始

### 1. 安装

**基础安装**（仅核心功能）：

```bash
pip install -e .
```

**开发安装**（推荐，包含测试和构建工具）：

```bash
pip install -e ".[dev]"
```

**完整安装**（包含本地检索增强和 R 代码执行，推荐）：

```bash
pip install -e ".[dev,local,webr]"
```

**可选依赖组说明**：

| 依赖组 | 说明 |
|--------|------|
| `[dev]` | 开发工具：pytest, black, mypy, weasyprint |
| `[local]` | 本地检索增强：jieba 中文分词 + rank-bm25 检索（零外部 API 依赖） |
| `[pdf]` | PDF 导出功能（weasyprint）|
| `[webr]` | WebR 支持（浏览器内运行 R）|
| `[mcp]` | MCP (Model Context Protocol) 服务器支持 |

> 提示：
> - 若看到 "jieba 未安装" 或 "rank_bm25 未安装" 警告，需安装 `[local]` 依赖组
> - 若看到 "R 环境不可用" 警告，需安装 `[webr]` 依赖组或本地 R 环境

### 2. 初始化配置

```bash
nini init          # 生成 .env
nini init --force  # 覆盖已有 .env
```

编辑 `.env` 文件，至少配置一个模型提供商的 API Key：

```bash
# 示例：使用 OpenAI
NINI_OPENAI_API_KEY=sk-your-api-key
NINI_OPENAI_MODEL=gpt-4o
```

支持多种模型：OpenAI、Anthropic、Moonshot AI (Kimi)、DeepSeek、智谱 AI (GLM)、阿里百炼、Kimi Coding、Ollama 本地模型。
可同时配置多个，Nini 会按优先级自动路由并故障转移。

### 3. 环境检查

```bash
nini doctor
```

### 4. 启动服务

**生产模式**：

```bash
nini start
```

**开发模式**（热重载）：

```bash
nini start --reload
```

启动后访问：`http://127.0.0.1:8000`

**前端开发模式**（热更新，推荐开发时使用）：

另开终端执行：

```bash
cd web && npm install && npm run dev
```

访问 `http://localhost:3000`，API 和 WebSocket 请求自动代理到后端 8000 端口。

## 常用工作流

1. 上传 `CSV / Excel` 文件
2. 在对话框输入需求，例如：
   - `帮我预览数据并给出摘要`
   - `比较 treatment 和 control 的差异并做 t 检验`
   - `生成 Nature 风格箱线图`
   - `对数值列做清洗并标准化`
   - `用 R 跑一下线性混合模型`
3. 导出结果：
   - `帮我导出这张图为 SVG`
   - `生成一份完整分析报告并导出 PDF`

## 开发验证

```bash
# 格式检查
black --check src tests

# 类型检查
mypy src/nini

# 后端测试
pytest -q

# 前端构建（TypeScript 检查 + 打包）
cd web && npm run build

# E2E 测试（前端交互改动时）
cd web && npm run test:e2e
```

## 打包发布

```bash
python -m build
```

产物输出到 `dist/`，安装验证：

```bash
pip install dist/nini-0.1.0-py3-none-any.whl
nini doctor
nini start
```

## 故障排查

### 启动时提示 "jieba 未安装" 或 "rank_bm25 未安装"

安装 `[local]` 依赖组：
```bash
pip install -e ".[local]"
```

### 启动时提示 "R 环境不可用"

安装 `[webr]` 依赖组（无需本地安装 R）：
```bash
pip install -e ".[webr]"
```

或安装本地 R 环境：
- **Ubuntu/Debian**: `sudo apt-get install r-base`
- **macOS**: `brew install r`
- **Windows**: 从 [CRAN](https://cran.r-project.org/) 下载安装

安装后确保 `Rscript` 命令在 PATH 中可用。

### 前端开发服务器无法连接后端

检查 `web/vite.config.ts` 中的代理配置，确保后端服务已启动在 8000 端口。

### 模型调用失败

1. 检查 `.env` 中 API Key 是否正确配置
2. 运行 `nini doctor` 检查环境
3. 查看控制台详细错误日志（设置 `NINI_DEBUG=true`）

### 代码执行超时

调整 `.env` 中的沙箱超时配置：
```bash
NINI_SANDBOX_TIMEOUT=120  # 秒
```

### 更多问题

查看完整文档：
- [快速上手指南](docs/nini_quickstart.md)
- [配置说明](docs/configuration.md)
- [CLI 参考](docs/cli_reference.md)
- [API 与 WebSocket 协议](docs/api_reference.md)
- [开发与发布指南](docs/development.md)

## 贡献指南

欢迎提交 Issue 和 PR！请确保：

1. 代码通过 `black --check src tests` 格式检查
2. 类型检查 `mypy src/nini` 无错误
3. 测试 `pytest -q` 全部通过
4. 遵循 Conventional Commits 提交规范

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。
