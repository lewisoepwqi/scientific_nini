# Nini：科研数据分析 AI Agent

[![CI](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml/badge.svg)](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml)

Nini 是一个本地优先（local-first）的科研数据分析 Agent。
用户通过对话上传并分析数据，Agent 自动调用统计、作图、清洗、代码执行与报告生成技能。

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

## 快速开始

### 1. 安装

```bash
pip install -e .[dev]
```

`dev` 依赖组已包含报告 PDF 导出依赖 `weasyprint`。
若使用发布包安装并需要 PDF 导出，可执行：

```bash
pip install nini[pdf]
```

### 2. 初始化配置

```bash
nini init          # 生成 .env
nini init --force  # 覆盖已有 .env
```

### 3. 环境检查

```bash
nini doctor
```

### 4. 启动服务

```bash
nini start --reload
```

启动后访问：`http://127.0.0.1:8000`

> **前端开发模式**（热更新）：另开终端执行 `cd web && npm run dev`，访问 `http://localhost:3000`，请求自动代理到后端。

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

## 文档导航

- 快速上手：`docs/nini_quickstart.md`
- 配置说明：`docs/configuration.md`
- CLI 参考：`docs/cli_reference.md`
- API 与 WebSocket 协议：`docs/api_reference.md`
- 开发与发布：`docs/development.md`
