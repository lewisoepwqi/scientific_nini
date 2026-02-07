# Nini：科研数据分析 AI Agent

[![CI](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml/badge.svg)](https://github.com/lewisoepwqi/scientific_nini/actions/workflows/ci.yml)

Nini 是一个本地优先（local-first）的科研数据分析 Agent。
用户通过对话上传并分析数据，Agent 自动调用统计、作图、清洗、代码执行与报告生成技能。

## 当前状态

- 架构重构已完成 `Phase 1-7`（截至 `2026-02-07`）
- 旧三服务代码（`frontend/`、`scientific_data_analysis_backend/`、`ai_service/`）已清理
- 当前仅保留单架构实现：`src/nini + web`

## 核心能力

- 对话式分析：WebSocket 流式返回文本、工具调用、图表、数据预览
- 数据分析技能：`t_test`、`anova`、`correlation`、`regression`
- 可视化技能：`create_chart`（7 种图表 + 6 种期刊风格）
- 数据处理技能：`clean_data`、`run_code`（受限沙箱）
- 产物能力：`generate_report`、`export_chart`
- 会话持久化：本地 `data/sessions/{session_id}`
- 多模型路由：OpenAI → Anthropic → Ollama 自动故障转移

## 项目结构

```text
scientific_nini/
├── src/nini/                 # 后端与 Agent Runtime
├── web/                      # 轻量前端（React + Vite）
├── data/                     # 本地数据（上传、会话、SQLite）
├── tests/                    # 新架构测试
├── docs/                     # 使用文档
├── dynamic-leaping-cray.md   # 重构设计与阶段说明
└── pyproject.toml
```

## 快速开始

### 1. 安装

```bash
pip install -e .[dev]
```

### 2. 初始化配置

```bash
nini init
```

默认生成 `.env`。如果文件已存在并希望覆盖：

```bash
nini init --force
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

## 常用工作流

1. 上传 `CSV/Excel` 文件
2. 直接在对话框输入需求，例如：
   - `帮我预览数据并给出摘要`
   - `比较 treatment 和 control 的差异并做 t 检验`
   - `生成 Nature 风格箱线图`
   - `对数值列做清洗并标准化`
3. 让 Agent 导出结果：
   - `帮我导出这张图为 SVG`
   - `生成一份分析报告`

## 文档导航

- 快速上手：`docs/nini_quickstart.md`
- 配置说明：`docs/configuration.md`
- CLI 参考：`docs/cli_reference.md`
- API 与 WebSocket 协议：`docs/api_reference.md`
- 开发与发布：`docs/development.md`

## 开发验证

```bash
# 后端测试
pytest -q

# 前端构建
cd web && npm install && npm run build
```

## 打包发布

```bash
python -m build
```

产物输出到 `dist/`，可通过以下方式安装验证：

```bash
pip install dist/nini-0.1.0-py3-none-any.whl
nini doctor
nini start
```
