# Nini：本地优先的科研全流程 AI 伙伴

[![CI](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml/badge.svg)](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml)

Nini 是一个本地优先（local-first）的科研全流程 AI 伙伴，覆盖从选题立项到学术传播的 8 个研究阶段。核心优势在数据分析，并向文献调研、实验设计、论文写作等阶段持续延伸。

它提供 Web UI、HTTP/WebSocket API、Agent Runtime、工具系统、会话持久化与受限代码执行环境，目标是让用户通过对话完成数据导入、清洗、统计分析、可视化、知识检索、报告导出、文献综述草稿、实验方案设计等科研任务。

> 从选题到发表，让每位研究者都有一位懂方法、守规范、数据安全的 AI 科研伙伴。

当前仓库已完成从旧三服务结构到单仓单架构的收敛，开发重点集中在：

- `src/nini/`：后端、Agent Runtime、工具、存储与 API
- `web/`：React + TypeScript 前端
- `tests/`：后端与集成测试
- `docs/`：使用、开发、配置与架构文档

## 当前能力

### 核心优势：数据分析（L3/T3）

- 对话式分析：通过聊天驱动数据预览、清洗、统计检验、图表生成与报告整理
- 6 个核心数据分析 Capability：差异分析、相关性分析、回归分析、数据探索、数据清洗、可视化（5 个可直接执行）
- 证据链与可信输出：结论可追溯到具体分析步骤和统计依据

### 科研全流程扩展

- **实验设计（L2/T2）**：样本量估计、功效分析、实验方案模板
- **文献调研（L2/T2）**：文献检索（Semantic Scholar / CrossRef）、综述结构草稿、引用管理
- **论文写作（L2/T2）**：论文结构生成、结果段落草稿、引用格式转换、图表排版
- **基线阶段（L1/T1）**：选题建议、数据采集工具建议、投稿与学术传播方向性意见

> 能力成熟度采用 **Lx（自动化等级）/ Tx（可信度等级）** 双轴模型，详见 [产品愿景与架构演进纲领](docs/nini-vision-charter.md)。

### 平台能力

- 多模型路由：支持 OpenAI、Anthropic、Ollama、Moonshot、Kimi Coding、智谱、DeepSeek、阿里百炼、MiniMax
- 三层工具架构：Tools（原子工具）→ Capabilities（领域能力）→ Skills（工作流模板），Skill 支持步骤 DAG、降级策略与人工复核门
- 安全执行：`run_code` 使用 AST 检查、导入白名单、超时与资源限制；`run_r_code` 支持可选 R 环境
- 持久化与工作区：默认使用 `SQLite + 本地文件系统`，会话、上传文件、产物和记忆默认落在 `data/`
- API 与流式事件：提供 HTTP 接口、WebSocket 事件流，以及面向集成场景的 MCP Server
- 可观测与回放：内置 harness trace 存储、回放与评测聚合命令，便于回归分析
- 插件系统：联网能力作为可选插件增强，离线可运行、联网可降级

## 架构概览

运行链路如下：

`Web UI -> FastAPI Gateway(HTTP + WebSocket) -> Agent Runner(ReAct) -> Skills/Tools -> Memory/Storage`

仓库结构：

```text
scientific_nini/
├── src/nini/                 # 后端、Agent Runtime、工具、存储、CLI、MCP
├── web/                      # React + TypeScript + Vite 前端
├── tests/                    # pytest 测试
├── docs/                     # 使用与开发文档
├── openspec/                 # 变更提案与规格流程
├── data/                     # 本地运行时数据（默认 gitignored）
└── pyproject.toml
```

## 系统要求

- Python `>=3.12`
- Node.js `>=18`（前端开发与构建需要）
- Linux / macOS / Windows（建议 WSL2）
- 可选本地 R 环境：需要执行 `run_r_code` 时安装

## 快速开始

### 1. 安装依赖

推荐开发环境直接安装：

```bash
pip install -e ".[dev]"
```

常见可选依赖组：

| 依赖组 | 说明 |
| --- | --- |
| `[dev]` | 开发工具、测试工具与常用本地运行依赖 |
| `[pdf]` | PDF 导出所需依赖 |
| `[local]` | 本地模型与本地向量检索相关依赖 |
| `[local_vector]` | 本地向量检索增强 |
| `[advanced_retrieval]` | 高级检索能力 |
| `[mcp]` | MCP Server 支持 |
| `[webr]` | WebR 相关支持 |

如果只想安装最小运行依赖，可执行：

```bash
pip install -e .
```

### 2. 初始化配置

```bash
nini init
```

生成 `.env` 后，至少配置一个模型提供商。例如：

```bash
NINI_OPENAI_API_KEY=sk-your-api-key
NINI_OPENAI_MODEL=gpt-4o
```

也可以配置多家提供商，让 Nini 按优先级自动路由与故障转移。

### 3. 环境检查

```bash
nini doctor
```

该命令会检查 Python 版本、数据目录可写性、模型路由配置，以及 `weasyprint`、R 环境、前端构建产物等可选项。

### 4. 启动服务

开发模式：

```bash
nini start --reload
```

生产模式：

```bash
nini start
```

默认访问地址：`http://127.0.0.1:8000`

如果希望前端单独热更新，另开终端执行：

```bash
cd web
npm install
npm run dev
```

此时前端开发服务器默认运行在 `http://localhost:3000`，并代理后端 API / WebSocket。

## 常用 CLI

`nini` 等价于 `python -m nini`。当前常用命令包括：

- `nini start`：启动 FastAPI、WebSocket 与静态前端
- `nini init`：生成 `.env` 模板
- `nini doctor`：执行环境自检
- `nini export-memory <session_id>`：导出会话记忆
- `nini harness list|show|replay|eval`：查看与分析 harness 运行记录
- `nini tools list|create|export`：管理 Function Tools 与 Markdown Skills
- `nini mcp`：以 stdio 方式启动 MCP Server，供 Claude Code / Codex 等工具接入

更多参数见 [CLI 参考](docs/cli_reference.md)。

## 典型使用流程

1. 启动服务并打开 Web UI。
2. 上传 `CSV / Excel` 数据集。
3. 通过对话提出分析需求，例如：
   - `帮我预览数据并总结关键字段`
   - `比较 treatment 和 control 的差异，并选择合适的统计检验`
   - `生成适合论文插图的箱线图和散点图`
   - `清洗缺失值并输出一份分析报告`
4. 按需导出图表、报告或工作区文件。

## 开发验证

最小回归建议执行：

```bash
black --check src tests
mypy src/nini
pytest -q
cd web && npm run build
```

按需补充：

```bash
python -m build
cd web && npm run test:e2e
```

## 打包

```bash
python -m build
```

构建产物输出到 `dist/`。本地烟测建议使用实际文件名安装：

```bash
pip install dist/nini-*.whl
nini doctor
nini start
```

## 文档导航

### 产品与架构

- [产品愿景与架构演进纲领](docs/nini-vision-charter.md) — 产品方向、能力矩阵、风险分级与实施路线图
- [Skill 执行契约规范](docs/skill-contract-spec.md) — Skill DAG、降级策略、人工复核门详细规范
- [高风险能力评审规范](docs/high-risk-capability-review.md) — 高风险能力三维评审流程

### 使用与开发

- [快速开始](docs/nini_quickstart.md)
- [配置说明](docs/configuration.md)
- [CLI 参考](docs/cli_reference.md)
- [API 与 WebSocket 参考](docs/api_reference.md)
- [开发与发布指南](docs/development.md)
- [架构概念](docs/architecture-concepts.md) — Tools / Capabilities / Skills 三层架构说明
- [能力开发指南](docs/capability-development-guide.md)
- [添加 Skills](docs/adding-skills.md)
- [功能模块清单](docs/feature-module-inventory.md)

## 常见问题

### `nini doctor` 提示未配置模型

检查 `.env` 中是否至少设置了一组有效的模型配置，例如 `NINI_OPENAI_API_KEY`，或确保本地 `Ollama` 配置完整。

### PDF 导出不可用

安装带 PDF 依赖的环境：

```bash
pip install -e ".[pdf]"
```

如果是开发环境，通常直接安装 `.[dev]` 即可。

### R 工具不可用

若需要 `run_r_code`，请安装本地 `Rscript`，或根据场景补装 `.[webr]`。

### 前端页面无法连接后端

确认后端已经启动在 `8000` 端口，并检查 `web/vite.config.ts` 中的代理配置。

## 贡献

请遵循仓库内 `AGENTS.md` / Git 工作流要求：

- 不在 `main` 直接开发
- 使用 `feature/fix/chore/docs` 分支
- 提交前至少完成 `pytest -q` 与 `cd web && npm run build`
- 提交信息使用 Conventional Commits，例如 `docs(readme): refresh project overview`

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
