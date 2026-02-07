# 科研数据分析 AI Agent 平台重构计划

## Context

当前项目是典型的"系统 + AI 辅助"架构：复杂的 React 前端（6 页面、5 个 Zustand Store）+ FastAPI 后端（CRUD 服务）+ 独立 AI 服务（大部分是占位实现）。这种架构在 AI Agent 时代将迅速过时。

目标是重构为 **AI Agent 驱动**的架构：用户通过自然语言与 Agent 对话，Agent 自动规划和执行数据分析、图表生成等任务。借鉴 OpenClaw 的本地运行、工具化、Agent 驱动理念，但用 Python 独立实现，针对科研数据分析场景深度优化。

**核心变化**：从"用户操作 UI → 系统执行"变为"用户描述意图 → Agent 自主完成"。

---

## 架构设计

### 四层架构

```
Layer 1: Gateway         FastAPI HTTP(上传/下载) + WebSocket(实时对话) + 静态文件(前端)
Layer 2: Agent Runtime   ReAct 循环 + 多模型路由(OpenAI/Claude/Ollama) + Lane Queue(串行执行)
Layer 3: Skills          统计分析 | 数据可视化 | 数据操作 | 代码执行沙箱 | 报告生成
Layer 4: Memory          会话记忆(JSONL) + 知识记忆(Markdown) + SQLite 元数据 + 文件存储
```

**一个进程，一条命令启动**：`python -m nini` 同时启动后端和前端，无需 Redis/Celery/PostgreSQL/Docker。

### 目录结构

```
scientific_nini/
├── pyproject.toml
├── src/nini/
│   ├── __main__.py              # 入口: python -m nini
│   ├── app.py                   # FastAPI 应用工厂
│   ├── config.py                # Pydantic Settings 配置
│   ├── agent/
│   │   ├── runner.py            # Agent ReAct 主循环
│   │   ├── model_resolver.py    # 多 LLM 路由与故障转移
│   │   ├── lane_queue.py        # 串行执行队列
│   │   ├── session.py           # 会话管理
│   │   └── prompts/             # 系统/科研领域 Prompt
│   ├── skills/
│   │   ├── base.py              # Skill 基类 + SkillResult
│   │   ├── registry.py          # 技能注册中心
│   │   ├── statistics.py        # 统计分析(t检验/ANOVA/相关/回归)
│   │   ├── visualization.py     # 图表生成(7种类型 x 6种期刊风格)
│   │   ├── data_ops.py          # 数据加载/预览/清洗
│   │   ├── code_exec.py         # 代码执行(调用沙箱)
│   │   └── report.py            # 分析报告生成
│   ├── sandbox/
│   │   ├── executor.py          # 进程隔离执行器
│   │   ├── policy.py            # 安全策略(导入白名单)
│   │   └── capture.py           # 输出捕获
│   ├── memory/
│   │   ├── conversation.py      # JSONL 会话记忆
│   │   ├── knowledge.py         # Markdown 知识记忆
│   │   └── storage.py           # 文件/产物存储
│   ├── models/
│   │   ├── database.py          # SQLite 表(Session/Dataset/Artifact/ModelConfig)
│   │   └── schemas.py           # Pydantic 请求/响应模型
│   └── api/
│       ├── routes.py            # HTTP 端点(上传/下载/导出)
│       └── websocket.py         # WebSocket Agent 交互
├── web/                         # 轻量前端
│   ├── src/
│   │   ├── App.tsx              # 左右分栏布局
│   │   ├── store.ts             # 单一 Zustand Store
│   │   ├── components/
│   │   │   ├── ChatPanel.tsx    # 对话主面板
│   │   │   ├── MessageBubble.tsx # 消息渲染(Markdown/代码/图表)
│   │   │   ├── ChartViewer.tsx  # Plotly 图表交互展示
│   │   │   ├── DataViewer.tsx   # 数据表格预览
│   │   │   ├── FileUpload.tsx   # 拖拽上传
│   │   │   ├── SessionList.tsx  # 会话列表
│   │   │   └── SettingsModal.tsx # API Key/模型配置
├── data/                        # 本地数据(.gitignore)
│   ├── uploads/
│   ├── sessions/{id}/memory.jsonl + knowledge.md + artifacts/
│   └── db/nini.db
└── tests/
```

### 核心模块设计

#### 1. Agent Runner (ReAct 循环)

`src/nini/agent/runner.py`

- 接收用户消息 → 构建上下文(系统Prompt + 知识记忆 + 数据摘要 + 历史对话) → 调用 LLM
- LLM 返回文本或工具调用 → 通过 Lane Queue 执行工具 → 将结果反馈给 LLM → 循环
- 所有事件通过 WebSocket 流式推送到前端
- 最大迭代次数 10 次防止无限循环
- 事件类型：TextEvent / ToolCallEvent / ToolResultEvent / ChartEvent / DataEvent / DoneEvent / ErrorEvent

#### 2. Model Resolver (多模型管理)

`src/nini/agent/model_resolver.py`

- 统一 LLMClient 协议：`chat_completion(messages, tools, stream)` → `AsyncGenerator[LLMChunk]`
- 三个适配器：OpenAIClient / AnthropicClient / OllamaClient
- 按 priority 排序，失败自动降级到下一个模型
- 成本追踪（复用现有 `ai_service/core/llm_client.py` 的 CostInfo 机制）

#### 3. Skill 系统

`src/nini/skills/`

- `Skill` 抽象基类：name / description / parameters(JSON Schema) / is_idempotent / execute()
- `SkillRegistry`：注册/注销/发现/执行，提供 `get_tool_definitions()` 转换为 LLM function calling 格式
- `SkillResult`：success / data / message / has_chart / chart_data / has_dataframe / artifacts

预置技能清单：
| 技能 | 来源 | 说明 |
|------|------|------|
| `load_dataset` | 新写 + 复用 data_service | 加载 CSV/Excel 到内存 |
| `preview_data` | 复用 data_service | 展示前 N 行和列信息 |
| `data_summary` | 复用 data_service | 描述性统计摘要 |
| `t_test` | 复用 analysis_service | 独立/配对/单样本 t 检验 |
| `anova` | 复用 analysis_service | 单因素 ANOVA + Tukey HSD |
| `correlation` | 复用 analysis_service | Pearson/Spearman/Kendall |
| `regression` | 复用 analysis_service | 线性/逻辑回归 |
| `create_chart` | 复用 visualization_service | 7种图表 x 6种期刊风格 |
| `export_chart` | 新写 | SVG/PNG/JPEG 导出 |
| `run_code` | 新写 | 沙箱执行自定义 Python |
| `clean_data` | 新写 | 缺失值/异常值/标准化 |
| `generate_report` | 新写 | Markdown 分析报告 |
| `update_knowledge` | 新写 | Agent 主动记录发现 |

#### 4. 代码执行沙箱

`src/nini/sandbox/executor.py`

- **进程隔离**：multiprocessing.Process 独立执行
- **AST 静态分析**：扫描禁止的 import（os/subprocess/shutil/socket 等）
- **导入白名单**：pandas/numpy/scipy/statsmodels/sklearn/matplotlib/plotly/seaborn
- **资源限制**：超时 30s、内存 512MB（resource.setrlimit）
- **文件系统隔离**：工作目录限制在会话临时目录
- 注：本地运行的威胁模型不同于服务器，主要防 Agent 幻觉导致的意外操作

#### 5. Memory 系统

- **ConversationMemory** (`memory.jsonl`)：append-only，记录消息/工具调用/结果
- **KnowledgeMemory** (`knowledge.md`)：Markdown 格式长期记忆，Agent 可通过 Skill 读写
- **SQLite**：会话列表、数据集注册、产物索引、模型配置
- **文件系统**：上传文件、数据快照、图表产物

#### 6. 前端

**设计理念**：对话是核心，其他都是辅助展示。

- 单一 Zustand Store（sessions + messages + wsConnected + isStreaming）
- WebSocket 实时通信，HTTP 仅用于文件上传/下载
- MessageBubble 支持 Markdown 渲染、代码语法高亮、Plotly 图表内嵌
- 比现有前端减少 80% 代码量

---

## 代码复用清单

### 直接复用（核心计算逻辑）

| 现有文件 | 目标文件 | 复用内容 |
|---------|---------|---------|
| `scientific_data_analysis_backend/app/services/analysis_service.py` | `src/nini/skills/statistics.py` | t检验/ANOVA/相关/回归计算逻辑(~400行) |
| `scientific_data_analysis_backend/app/services/visualization_service.py` | `src/nini/skills/visualization.py` | 7种图表创建 + 6种期刊风格(~600行) |
| `scientific_data_analysis_backend/app/core/publication_templates.py` | `src/nini/skills/templates.py` | TEMPLATES 字典和验证逻辑 |
| `scientific_data_analysis_backend/app/services/data_service.py` | `src/nini/skills/data_ops.py` | 数据加载/列信息/类型检测 |
| `ai_service/core/prompts.py` | `src/nini/agent/prompts/scientific.py` | 科研领域 Prompt 模板(~500行) |
| `ai_service/core/llm_client.py` | `src/nini/agent/model_resolver.py` | 重试逻辑/成本追踪/流式响应 |

### 不复用（架构不兼容）

- 整个 `frontend/`（范式不同，新前端只需对话界面）
- 后端 API 端点（从 CRUD → WebSocket 交互）
- SQLAlchemy 模型（耦合旧工作流，新模型更简单）
- Docker/Celery/Redis 配置（不再需要）
- `ai_service/agent/agent_architecture.py`（纯占位代码）
- `data_cleaning_service.py`（占位实现）

---

## 分阶段实施

### Phase 1：基础骨架
**目标**：浏览器中与 Agent 文字对话

- 项目初始化：pyproject.toml、目录结构、依赖
- 配置系统（Pydantic Settings）
- Model Resolver：OpenAI 客户端
- Agent Loop：基础 ReAct 循环（无工具）
- FastAPI + WebSocket 端点
- 最小 React 前端：ChatPanel + WebSocket
- 启动命令：`python -m nini`

### Phase 2：核心技能
**目标**：上传数据 → Agent 分析 → 生成图表

- Skill 基类、Registry、Lane Queue
- 数据操作技能：load_dataset / preview_data / data_summary
- 统计分析技能：t_test / anova / correlation / regression（移植现有代码）
- 可视化技能：create_chart + 期刊风格（移植现有代码）
- 文件上传 HTTP 端点 + FileUpload 组件
- ChartViewer + DataViewer 前端组件

### Phase 3：代码执行沙箱
**目标**：Agent 编写并执行自定义 Python 代码

- SandboxExecutor 进程隔离
- AST 安全分析 + 导入白名单
- 资源限制（超时/内存）
- CodeExec Skill
- 前端代码块渲染

### Phase 4：记忆系统
**目标**：会话持久化和多会话管理

- ConversationMemory (JSONL)
- KnowledgeMemory (Markdown)
- SQLite 元数据存储
- Session Manager
- 前端 SessionList 组件

### Phase 5：多模型支持
**目标**：Claude + Ollama 支持

- AnthropicClient 适配（工具调用格式差异）
- OllamaClient 适配（HTTP 本地调用）
- 故障转移逻辑
- 前端 SettingsModal（API Key/模型配置）

### Phase 6：科研深化
**目标**：专业科研分析体验

- 数据版本管理（DataSnapshot）
- 报告生成技能（Markdown 格式）
- 数据清洗技能
- 图表导出（SVG/PNG/JPEG）
- 科研 Prompt 优化

### Phase 7：打磨发布
**目标**：`pip install nini && nini start`

- 错误处理和恢复
- 测试（覆盖率 80%+）
- 用户文档
- pip 打包
- 首次运行向导

---

## 验证方式

### Phase 1 验证
```bash
python -m nini  # 启动后浏览器打开 localhost:8000
# 在对话框输入文字，Agent 正常回复
```

### Phase 2 验证
```
用户: [上传 experiment.csv]
用户: 帮我对 treatment 组和 control 组做 t 检验，然后画一个 Nature 风格的箱线图
Agent: [自动调用 load_dataset → t_test → create_chart]
       → 内嵌显示统计结果和可交互 Plotly 图表
```

### Phase 3 验证
```
用户: 帮我写一段代码，对所有数值列做 Z-score 标准化
Agent: [生成 Python 代码 → 沙箱执行 → 返回结果]
```

### 端到端验证
```
用户: 我有一个临床试验数据，想比较药物组和安慰剂组的疗效差异
Agent: 好的，让我先看看数据...
       [load_dataset → data_summary → 自动选择统计方法]
       [t_test → create_chart(箱线图, Nature风格)]
       [generate_report]
       → 完整分析报告 + 可交互图表 + 统计结论
```
