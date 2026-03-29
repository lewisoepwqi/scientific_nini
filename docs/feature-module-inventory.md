# 功能模块与功能点清单

本文档基于对当前仓库的完整代码扫描整理，目标是从产品、后端、前端和运行时四个视角，对 Nini 的功能模块与功能点做一份可审阅、可维护、可继续补充的正式清单。

扫描基线：

- 仓库快照日期：`2026-03-29`
- 扫描范围：`src/nini/`、`web/src/`、`config/recipes/`、`.nini/skills/`、`tests/`、`docs/`
- 统计原则：以当前代码、已注册默认能力、前端实际入口和测试覆盖为准；环境级通用技能目录（如 `.claude/`、`.codex/`、`.opencode/`）不计入项目产品能力

## 1. 功能总览

| 层级 | 模块 | 说明 |
| --- | --- | --- |
| 平台层 | Web UI、FastAPI、WebSocket、CLI、MCP | 提供交互入口、接口协议和本地运行方式 |
| Agent 层 | ReAct Runtime、多模型路由、多 Agent、Recipe、上下文构建 | 负责理解任务、组织工具调用、管理分析流程 |
| 能力层 | Capability、Markdown Skill、Specialist Agent | 对外呈现科研任务能力，对内承接工作流和专业子任务 |
| 工具层 | Function Tools、隐藏内部工具、导出与工作区工具 | 提供具体可执行原子操作 |
| 数据层 | 会话、工作区、数据集、知识库、记忆、SQLite | 负责本地持久化与资产管理 |
| 横切层 | 安全沙箱、可观测、成本透明、推理可解释性 | 提供安全、稳定、可追踪和可审计能力 |

## 2. 核心平台与基础设施

| 一级模块 | 入口/子模块 | 功能点 | 当前状态 |
| --- | --- | --- | --- |
| 启动与交付 | `nini` CLI、`python -m nini`、`windows_launcher.py` | 启动服务、初始化环境、自检、导出记忆、运行 harness、管理工具与技能、启动 MCP、自动打开浏览器、Windows 宿主启动 | 已启用 |
| FastAPI 应用工厂 | `src/nini/app.py` | 注册 HTTP API、WebSocket、静态前端、SPA fallback、生命周期初始化、日志初始化、数据库初始化、插件初始化、工具注册 | 已启用 |
| 鉴权 | `auth_utils.py`、中间件、`/api/auth/*` | API Key 认证、认证状态查询、设置/清除认证会话 Cookie、WebSocket 鉴权 | 已启用 |
| 试用模式 | `models_routes.py`、事件流、前端模型设置页 | 系统内置模型额度、试用激活、试用到期阻断、前端额度展示与提示 | 已启用 |
| 会话管理 | `session.py`、`session_routes.py` | 创建会话、列出会话、分页、标题搜索、更新标题、删除会话、读取消息、压缩、回滚、导出整会话资产 | 已启用 |
| 工作区管理 | `workspace/manager.py`、`workspace_routes.py` | 会话工作区、文件树、资源摘要、项目级产物、导出任务、执行历史、文件夹管理、批量下载 | 已启用 |
| 数据集资产管理 | `routes.py`、`dataframe_io.py` | 文件上传、CSV/Excel 读取、Excel 多 sheet 模式、数据集预览、加载、导出、删除、序列日期修复 | 已启用 |
| SQLite 与文件存储 | `models/database.py`、`memory/storage.py`、`memory/db.py` | 本地数据库初始化、会话与资源持久化、文件产物写入、运行目录管理 | 已启用 |
| 日志与可观测 | `logging_config.py`、运行时日志 | 请求 ID、连接 ID、结构化日志、HTTP/WebSocket 运行日志、工具执行耗时日志 | 已启用 |
| 插件系统 | `plugins/base.py`、`plugins/registry.py`、`plugins/network.py` | 插件注册、可用性检测、生命周期初始化/关闭、网络能力探测、联网降级说明 | 已启用 |
| MCP 集成 | `mcp/server.py` | 通过 stdio 暴露架构层工具和 Function Tools，支持 Claude Code/Codex/OpenCode 接入 | 已启用 |

## 3. Agent Runtime 与执行编排

| 模块 | 子模块 | 功能点 | 当前状态 |
| --- | --- | --- | --- |
| ReAct Runtime | `agent/runner.py` | 对话驱动的思考-工具-结果循环、错误处理、输出拼装、流式事件发送 | 已启用 |
| 上下文构建 | `agent/components/context_*` | 构建数据集上下文、知识上下文、记忆上下文、工具上下文、AGENTS.md 项目上下文 | 已启用 |
| 上下文压缩 | `context_compressor.py`、`memory/compression.py` | 上下文窗口控制、滑动压缩、轻量压缩、LLM 压缩、压缩段落记录与回滚 | 已启用 |
| 分析阶段识别 | `analysis_stage_detector.py`、`detect_phase.py` | 识别实验设计、文献调研、数据分析、论文写作等阶段，用于导航和上下文增强 | 已启用 |
| 计划生成与解析 | `planner.py`、`plan_parser.py`、`event_builders.py` | 生成结构化分析计划、解析步骤列表、输出计划进度与任务尝试事件 | 已启用 |
| 循环守卫 | `loop_guard.py` | 检测异常重复推理/重复工具调用，避免死循环 | 已启用 |
| 工具执行调度 | `tool_executor.py`、`lane_queue.py` | 串行执行同会话工具、统一结果回收、异常与超时处理 | 已启用 |
| 任务管理 | `task_manager.py`、`task_write.py`、`task_state.py` | 管理任务列表、当前任务、状态推进，支撑长任务执行 | 已启用 |
| 标题生成 | `title_generator.py` | 自动根据会话内容生成会话标题 | 已启用 |
| 会话资源同步 | `session.py`、`models/session_resources.py` | 将图表、文档、代码执行、导出任务沉淀为受管资源 | 已启用 |

## 4. 多模型路由与供应商管理

### 4.1 后端支持的模型供应商

| 供应商 | 用途 | 功能点 |
| --- | --- | --- |
| OpenAI | 通用对话、规划、验证、标题、图像 | OpenAI 兼容函数调用、模型配置、可用模型管理 |
| Anthropic | 通用对话、规划、验证 | Claude 系列接入与工具调用适配 |
| Ollama | 本地模型 | 本地模型对话、开发/离线场景运行 |
| Moonshot | 通用对话 | Kimi 兼容接入 |
| Kimi Coding | 编码/规划 | Kimi Coding 兼容接入 |
| 智谱 GLM | 对话、Coding Plan | 标准模式与 Coding Plan 模式切换、模型候选列表 |
| DeepSeek | 对话、推理、代码 | 高性价比国内直连 |
| DashScope | 通义千问、Coding Plan | 标准模式与 Coding Plan 模式切换 |
| MiniMax | 对话 | MiniMax 供应商接入 |
| 内置 DashScope 模型 | 试用模式 | 快速/深度/图像/标题模型与调用额度管理 |

### 4.2 路由与管理功能

| 模块 | 功能点 | 当前状态 |
| --- | --- | --- |
| `model_resolver.py` | 模型优先级、按用途路由、故障转移、模型选择策略 | 已启用 |
| `model_lister.py` | 动态获取提供商可用模型列表 | 已启用 |
| `models_routes.py` | 列供应商、测试配置、保存配置、删除配置、设置优先级、设置用途路由、查询当前激活模型 | 已启用 |
| 前端设置页 | 供应商卡片、试用状态、配置表单、快速切换、输入框内嵌切换 | 已启用 |

## 5. WebSocket 事件与实时协同

| 事件类 | 事件类型 | 功能点 |
| --- | --- | --- |
| 基础交互事件 | `text`、`done`、`error`、`session`、`session_title` | 流式文本、完成通知、错误通知、会话元数据回传、自动标题 |
| 工具执行事件 | `tool_call`、`tool_result`、`code_execution` | 前端实时显示工具调用、工具返回和代码运行结果 |
| 数据与产物事件 | `data`、`chart`、`artifact`、`image`、`workspace_update` | 数据预览、图表、文件产物、图片、工作区刷新 |
| 推理与计划事件 | `reasoning`、`analysis_plan`、`plan_step_update`、`plan_progress`、`task_attempt` | 可解释推理展示、计划步骤、当前进度、重试轨迹 |
| 运行控制事件 | `pong`、`stopped`、`ask_user_question` | 保活、停止响应、挂起向用户提问 |
| 风险与预算事件 | `token_usage`、`model_fallback`、`budget_warning`、`completion_check`、`blocked` | Token 用量、模型降级、预算预警、完成校验、阻塞通知 |
| Trial 事件 | `trial_activated`、`trial_expired` | 首次激活和试用到期 |
| 多 Agent 事件 | `agent_start`、`agent_progress`、`agent_complete`、`agent_error`、`workflow_status` | 并行 Agent 生命周期可视化 |
| 假设驱动事件 | `hypothesis_generated`、`evidence_collected`、`hypothesis_validated`、`hypothesis_refuted`、`hypothesis_revised`、`paradigm_switched` | 展示假设生成、证据支持/反驳与范式切换 |

## 6. HTTP API 模块清单

### 6.1 会话、数据集、工作区与通用接口

| 路由模块 | 代表端点 | 功能点 |
| --- | --- | --- |
| `api/routes.py` | `/api/upload` | 上传数据文件、技能文件和其他工作区文件 |
| `api/routes.py` | `/api/datasets/{session_id}`、`/load`、`/preview`、`/export`、`DELETE` | 列数据集、加载激活、预览内容、导出原文件、删除数据集 |
| `api/routes.py` | `/api/sessions/{session_id}/messages` | 获取消息历史，包含图表、数据预览、产物和推理元信息 |
| `api/routes.py` | `/api/workspace/{session_id}/files/*` | 工作区文件读取、预览、写入、移动、重命名、删除、下载、打包下载 |
| `api/routes.py` | `/api/charts/{session_id}/{chart_id}.plotly.json` | 下载图表的 Plotly JSON 原始内容 |
| `api/routes.py` | `/api/sessions/{session_id}/export-all` | 导出整个会话的上传、产物、笔记和记忆 |
| `api/routes.py` | `/api/health` | 健康检查 |
| `api/routes.py` | `/api/auth/status`、`/api/auth/session` | 鉴权状态、设置会话认证、清除会话认证 |

### 6.2 会话管理

| 端点前缀 | 功能点 |
| --- | --- |
| `/api/sessions` | 会话列表、分页、标题过滤、创建、查询单会话、更新标题 |
| `/api/sessions/{session_id}/compress` | 轻量/自动/LLM 压缩 |
| `/api/sessions/{session_id}/rollback` | 回滚最近一次压缩 |
| `/api/sessions/{session_id}/token-usage` | 当前会话 Token 统计 |
| `/api/sessions/{session_id}/memory-files` | 记忆文件列表与内容读取 |
| `/api/sessions/{session_id}/context-size` | 上下文大小查看 |
| `/api/sessions/{session_id}/export-all` | 会话资产导出 |

### 6.3 模型、成本、知识、画像、记忆、Recipe

| 路由模块 | 代表端点 | 功能点 |
| --- | --- | --- |
| `models_routes.py` | `/api/models`、`/api/models/{provider_id}/available` | 查询供应商配置状态与候选模型 |
| `models_routes.py` | `/api/models/config`、`/test`、`/preferred`、`/routing`、`/priorities` | 模型配置保存、连通性测试、首选模型、用途路由、优先级 |
| `models_routes.py` | `/api/trial/status`、`/api/models/active`、`/api/models/default` | 试用状态、当前激活模型、默认模型 |
| `cost_routes.py` | `/api/cost/session/{id}`、`/api/cost/sessions`、`/api/cost/pricing` | 会话成本、全局成本聚合、模型定价与成本预警元数据 |
| `knowledge_routes.py` | `/api/knowledge/search`、`/documents`、`/index/*`、`/context`、`/stats` | 知识搜索、文档管理、索引重建/状态、知识上下文、统计信息 |
| `profile_routes.py` | `/api/research-profile*` | 获取/更新研究画像、画像叙述层、画像 Prompt、记录分析历史 |
| `profile_routes.py` | `/api/report/templates`、`/report/generate` | 报告模板列表、基础报告生成 |
| `memory_routes.py` | `/api/memory/long-term*` | 长期记忆列表、搜索、提取、删除、统计、初始化 |
| `recipe_routes.py` | `/api/recipes` | Recipe Center 模板列表 |
| `intent_routes.py` | `/api/intent/analyze`、`/api/intent/status` | 意图分析和状态查询 |

### 6.4 技能、工具、能力目录与执行

| 端点前缀 | 功能点 |
| --- | --- |
| `/api/tools` | Function Tools 目录 |
| `/api/skills` | 技能目录、按类型筛选、语义目录 |
| `/api/skills/markdown/*` | Markdown Skill 列表、详情、instruction、runtime resources、文件树、文件内容、写入、上传附件、创建目录、删除路径、启停、打包下载 |
| `/api/skills/upload` | 上传 Markdown Skill |
| `/api/capabilities/suggest` | 基于用户消息推荐高层能力 |
| `/api/capabilities/{name}/execute` | 执行可直接执行的 Capability |

## 7. Function Tools 完整清单

### 7.1 默认注册并进入运行时的工具

| 工具名 | 分类 | 功能点 |
| --- | --- | --- |
| `task_write` | `utility` | 初始化和更新任务列表，支撑长任务执行与复盘 |
| `task_state` | `utility` | 查询全部任务、当前任务或更新任务状态 |
| `load_dataset` | `data` | 从上传数据集中读取 DataFrame，并支持 Excel sheet 模式 |
| `data_summary` | `data` | 输出数值列和分类列的统计摘要 |
| `dataset_catalog` | `data` | 统一查看数据集目录、预览、概况与质量摘要 |
| `dataset_transform` | `data` | 结构化数据变换、聚合、过滤、派生列和重跑 |
| `detect_phase` | `utility` | 检测当前研究阶段 |
| `t_test` | `statistics` | 独立样本、配对样本、单样本 t 检验 |
| `mann_whitney` | `statistics` | 两组独立样本非参数检验 |
| `anova` | `statistics` | 单因素 ANOVA 与 Tukey HSD 事后比较 |
| `kruskal_wallis` | `statistics` | 多组非参数检验 |
| `stat_test` | `statistics` | 统一统计检验入口，含多重比较校正 |
| `sample_size` | `statistics` | 样本量与功效分析 |
| `stat_model` | `statistics` | 相关分析、线性回归、多元回归统一入口 |
| `stat_interpret` | `statistics` | 统计结果与建模结果自然语言解释 |
| `code_session` | `utility` | 持久化 Python/R 脚本会话与执行历史 |
| `run_code` | `utility` | 在 Python 沙箱中执行代码 |
| `run_r_code` | `utility` | 在 R 沙箱中执行代码 |
| `chart_session` | `visualization` | 图表会话创建、更新、查询、导出 |
| `export_chart` | `export` | 图表导出为 PNG/JPEG/SVG/PDF/HTML/JSON |
| `export_document` | `export` | 工作区文档导出为 PDF 或 DOCX |
| `generate_report` | `report` | 生成结构化 Markdown 分析报告 |
| `report_session` | `report` | 报告会话的创建、更新、导出 |
| `export_report` | `export` | 分析报告或兼容 Markdown 文档导出为 PDF |
| `organize_workspace` | `utility` | 工作区整理、文件夹创建与文件移动 |
| `fetch_url` | `utility` | 抓取网页并转为 Markdown 文本 |
| `generate_widget` | `visualization` | 生成聊天内嵌可渲染的 HTML 小组件 |
| `search_literature` | `utility` | 学术文献检索，优先 Semantic Scholar，失败降级 CrossRef |
| `collect_artifacts` | `report` | 收集统计结果、图表、方法记录和摘要作为写作素材包 |
| `complete_comparison` | `workflow` | 两组比较全流程：质量检查、检验、解释、可视化 |
| `complete_anova` | `workflow` | 多组比较全流程：ANOVA、事后检验、效应量、图表 |
| `correlation_analysis` | `workflow` | 相关矩阵、显著性标记、解释与图表 |
| `regression_analysis` | `workflow` | 回归模型拟合、假设检查、结果解释与输出 |
| `edit_file` | `utility` | 工作区文件读取、写入、追加、局部编辑 |
| `workspace_session` | `utility` | 工作区列表、读写、编辑、整理、URL 抓取统一入口 |
| `analysis_memory` | `other` | 查询当前会话的分析记忆与关键发现 |
| `query_evidence` | `other` | 基于结论或关键词查询证据链 |
| `search_memory_archive` | `utility` | 在压缩归档对话中做关键词检索 |
| `update_profile_notes` | `utility` | 将稳定偏好与观察写入研究画像叙述层 |
| `search_tools` | `other` | 按需发现隐藏工具的完整 schema |
| `dispatch_agents` | `utility` | 将复杂任务并行分发给多个 Specialist Agent 并融合结果 |

### 7.2 代码中存在但未全部默认暴露的内部/隐藏工具

| 工具名/模块 | 功能点 |
| --- | --- |
| `clean_data` | 缺失值处理、异常值处理、归一化、自动策略执行 |
| `recommend_cleaning_strategy` | 根据列画像推荐清洗策略 |
| `evaluate_data_quality`、`data_quality_report` | 完整性、一致性、准确性、有效性、唯一性评分与清洗建议 |
| `image_analysis` | 从图片或图表中提取结构化数据、图表信息和文本结论 |
| `save_workflow`、`list_workflows`、`apply_workflow` | 从历史操作沉淀工作流模板并复用 |
| `analysis_workflow` | 内部编排层，用于将多个数据与统计工具串联 |

## 8. 高层能力层清单

| Capability 名称 | 显示名 | 是否可直接执行 | 功能点 | 所属阶段 |
| --- | --- | --- | --- | --- |
| `difference_analysis` | 差异分析 | 是 | 比较两组或多组差异，自动选择检验 | 数据分析 |
| `correlation_analysis` | 相关性分析 | 是 | 探索变量相关关系，生成相关矩阵与解释 | 数据分析 |
| `regression_analysis` | 回归分析 | 是 | 建立回归模型并解释结果 | 数据分析 |
| `data_exploration` | 数据探索 | 否 | 了解数据分布、缺失值、异常值 | 数据分析 |
| `data_cleaning` | 数据清洗 | 是 | 缺失值/异常值处理与质量提升 | 数据分析 |
| `visualization` | 可视化 | 是 | 创建各类科研图表 | 通用 |
| `report_generation` | 报告生成 | 否 | 生成分析报告与文档产物 | 数据分析 |
| `article_draft` | 科研文章初稿 | 否 | 多章节论文草稿编排与生成 | 论文写作 |
| `citation_management` | 引用管理 | 否 | 参考文献整理与格式转换 | 论文写作 |
| `peer_review` | 同行评审辅助 | 否 | 审稿意见整理与回复草拟 | 论文写作 |
| `research_planning` | 研究规划 | 否 | 研究设计、实验方案、样本量规划 | 实验设计 |

## 9. Recipe Center 清单

| Recipe ID | 名称 | 结构化输入 | 默认输出 | 执行步骤 |
| --- | --- | --- | --- | --- |
| `experiment_plan` | 实验设计与统计计划 | 研究问题、研究对象、主要终点 | 实验设计清单、统计分析计划 | 抽取研究结构；匹配统计分析路径；输出实验与统计计划 |
| `literature_review` | 文献综述提纲 | 研究主题、综述范围、目标输出 | 综述提纲、检索计划 | 明确综述范围；规划检索与证据框架；输出综述提纲 |
| `results_interpretation` | 结果解读与下一步建议 | 主要结果、对照关系、当前疑问 | 讨论提纲、下一步建议 | 抽取主要发现；建立解释框架；输出结论与下一步 |

## 10. 项目内 Markdown Skills 清单

| 技能目录 | 技能名 | 分类 | 功能点 |
| --- | --- | --- | --- |
| `.nini/skills/article-draft` | `article_draft` | `report` | 基于现有分析结果逐章生成论文初稿，并保存到工作区 |
| `.nini/skills/experiment-design-helper` | `experiment-design-helper` | `experiment_design` | 覆盖问题定义、设计选择、样本量计算、方案生成的实验设计引导 |
| `.nini/skills/literature-review` | `literature-review` | `workflow` | 检索、筛选、综合和输出的文献调研工作流，在线/离线双路径 |
| `.nini/skills/literature_chart_driven_analysis` | `literature_chart_driven_analysis` | `workflow` | 基于上传论文 PDF 或参考图表提炼分析方法，再对用户数据做复现分析 |
| `.nini/skills/publication_figure` | `publication_figure` | `visualization` | 生成符合顶级学术期刊风格的科研图表 |
| `.nini/skills/root-analysis` | `root-analysis` | `statistics` | 面向植物根长度实验数据的 ANOVA、Tukey HSD 与发表级可视化 |
| `.nini/skills/writing-guide` | `writing-guide` | `workflow` | 将已有分析结果桥接为论文写作素材包、章节结构和撰写提示 |

## 11. Specialist Agent 清单

| Agent ID | 功能点 |
| --- | --- |
| `literature_search` | 文献检索、论文搜索、引用获取 |
| `literature_reading` | 文献精读、批注、深度理解 |
| `data_cleaner` | 数据清洗、缺失值与异常值处理 |
| `statistician` | 统计检验、回归分析、方差分析、显著性判断 |
| `viz_designer` | 数据可视化、图表选择与制作 |
| `writing_assistant` | 科研写作、摘要/引言/讨论等章节辅助 |
| `citation_manager` | 引用格式、参考文献管理与规范转换 |
| `research_planner` | 研究规划、实验设计、研究思路梳理 |
| `review_assistant` | 同行评审意见整理与回复辅助 |

## 12. 知识库、记忆与证据链

| 模块 | 功能点 | 当前状态 |
| --- | --- | --- |
| 知识库文档管理 | 文档上传、删除、详情、列表、元数据持久化 | 已启用 |
| 混合检索 | 语义检索、关键词检索、混合融合、结果去重 | 已启用 |
| 层次化检索 | Markdown 文档解析、层次化索引、重排、缓存、统一检索接口 | 已启用 |
| 知识上下文注入 | 将检索结果包装为不可信运行时上下文注入模型提示词 | 已启用 |
| 会话记忆 | `memory.jsonl`、`knowledge.md`、压缩段记录 | 已启用 |
| 长期记忆 | 跨会话记忆提取、去重、重要性评分、向量搜索、按会话/数据集/类型过滤 | 已启用 |
| 研究画像 | 研究领域、常用方法、输出语言、报告细节级别、样本量偏好、最近数据集、研究备注 | 已启用 |
| 证据链 | 结论到证据的映射查询、证据追踪、Methods 归一化辅助 | 已启用 |

## 13. 安全、沙箱与风险控制

| 模块 | 功能点 | 当前状态 |
| --- | --- | --- |
| Python 沙箱 | AST 静态检查、导入白名单、受限执行、超时和内存限制、输出捕获 | 已启用 |
| R 沙箱 | 包白名单、危险调用检测、原生 R 与 WebR 路由 | 已启用 |
| Guardrail | 危险命令/危险模式拦截、需确认操作阻断 | 已启用 |
| 鉴权 | API Key 与 WebSocket 鉴权 | 已启用 |
| 风险模型 | 研究阶段、风险等级、输出等级建模 | 已启用 |

## 14. 成本透明与可解释性

| 模块 | 功能点 | 当前状态 |
| --- | --- | --- |
| Token 跟踪 | 输入/输出/总 Token 统计 | 已启用 |
| 成本换算 | USD/CNY 估算、模型分项拆分、会话汇总、历史聚合 | 已启用 |
| 定价配置 | `pricing.yaml` 模型定价、层级定义、成本预警 | 已启用 |
| 推理展示 | 思考过程、决策理由、推理类型、关键决策、置信度 | 已启用 |
| 导出与复制推理 | 前端复制分析思路、导出到报告入口 | 部分接口仍在演进 |
| 模型降级提示 | 模型回退事件与前端提示 | 已启用 |

## 15. 前端功能模块清单

| 前端区域 | 主要组件 | 功能点 |
| --- | --- | --- |
| 应用壳层 | `App`、`GlobalNav`、`SessionList`、`AuthGate` | 三栏布局、移动端适配、导航切换、主题切换、会话选择、认证门禁 |
| 聊天区 | `ChatPanel`、`MessageBubble`、`ChatInputArea` | 消息流、流式输出、重试、引导提示、输入区、待回答提示 |
| Recipe 与长任务 | `RecipeCenter`、`AnalysisPlanCard`、`DeepTaskProgressCard`、`SkillProgressPanel` | 模板启动、计划进度、步骤展示、技能进度、长任务状态 |
| 工作区 | `WorkspaceSidebar`、`FileTreeView`、`ArtifactGallery`、`FilePreviewPane`、`CodeExecutionPanel` | 文件列表/树/画廊、搜索、预览、执行历史、任务面板、拖拽上传、全部下载 |
| 知识库 | `KnowledgePanel`、`KnowledgeRetrievalView`、`Citation*` | 文档上传删除、检索结果可视化、引用标记与引用详情 |
| 模型配置 | `ModelConfigPanel`、`ModelSelector`、`InlineModelSwitch` | 模型供应商配置、试用模式额度、快速模型切换、可用模型加载 |
| 能力与技能 | `CapabilityPanel`、`SkillCatalogPanel`、`MarkdownSkillManagerPanel` | 展示能力目录、技能目录、管理 Markdown Skill 文件和启停 |
| 研究画像与记忆 | `ResearchProfilePanel`、`MemoryPanel` | 画像查看/编辑、画像叙述层、会话记忆文件、长期记忆筛选/删除 |
| 报告与初稿 | `ArticleDraftPanel`、`ArtifactDownload` | 期刊模板选择、章节配置、导出 Markdown/Word/PDF、产物下载 |
| 可解释性与成本 | `ReasoningPanel`、`DecisionTag`、`CostPanel`、`OutputLevelExplainer` | 推理展开、复制、导出；成本统计与历史汇总；输出等级说明 |
| 多 Agent 与 Hypothesis | `AgentExecutionPanel`、`WorkflowTopology`、`HypothesisTracker`、`TaskTree`、`InspectorPanel` | 并行 Agent 状态、拓扑图、假设置信度、证据链折叠、任务树检查 |
| 稳定性组件 | `ErrorBoundary`、Confirm Dialog、Store 状态机 | 错误兜底、确认弹窗、事件归一化、WebSocket 状态、认证状态、计划状态机 |

## 16. 当前仍在演进或部分保留兼容的功能

| 项目 | 说明 |
| --- | --- |
| `report_generation`、`article_draft`、`citation_management`、`peer_review`、`research_planning` | 高层 Capability 已建模，但并非全部都已接成可直接执行入口 |
| `profile_routes.py` 中的 `report/export`、`report/preview` | 当前返回待迁移提示；现行主路径是 `report_session + export_document/export_report` |
| 内部工具 `clean_data`、`data_quality`、`image_analysis`、`workflow_tool` | 代码与测试存在，但不是全部都对默认 LLM 工具列表公开 |
| 一些 Markdown Skill | 已可发现和管理，但更多用于工作流引导，不一定对应单个直接执行 API |

## 17. 维护建议

| 建议项 | 说明 |
| --- | --- |
| 保持文档同步 | 新增 Tool、Capability、Recipe、Markdown Skill 或前端面板时，同步更新本清单 |
| 区分“默认公开”和“内部可用” | 建议后续在工具与技能目录中明确标注默认公开范围，减少理解偏差 |
| 为演进项增加状态字段 | 对“已建模未接执行器”的能力增加明确状态，如 `planned`、`guided_only`、`direct_execute_ready` |
| 增加自动生成能力清单 | 可考虑后续从 ToolRegistry、CapabilityRegistry、RecipeRegistry 自动导出本文档的结构化部分 |

