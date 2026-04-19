# 代码档案面板重构设计

- 日期：2026-04-19
- 范围：工作区右侧「执行历史」面板从"工具调用日志"重定位为"可复现代码档案"
- 作者：oepwqi + Claude

## 背景

当前工作区 sidebar 的「执行历史」Tab（`web/src/components/CodeExecutionPanel.tsx`）面向"所有工具调用"混杂展示，存在三个问题：

1. **定位不清**：用户期望从这里查看 agent 完成任务过程中产出分析结果和图表的**完整代码**，以支撑科研场景的过程审计与复现，但当前 UI 强调时间线与工具多样性，真正可下载执行的代码反而被淹没。
2. **无法取回代码**：仅提供"复制"按钮，没有单文件下载和批量下载通道，离"下载到本地并执行"有一大步距离。
3. **文案不友好**：`REQUEST` / `RESPONSE` 英文混排、`脚本资源: script_xxx` / `输出资源: ds_xxx` 不透明哈希、`TOOL_NAME_DISPLAY` 中大量条目（`stat_test`、`chart_session`、`clean_data` 等）实际永远不会出现（僵尸映射），用户难以理解该面板的用途。

## 现状核查（后端真相）

核查 `src/nini/workspace/manager.py:2011 save_code_execution()` 的调用来源，发现：

- 真正写入 `workspace/executions/*.json` 的工具**只有** `run_code` / `run_r_code`（以及 `code_session` 作为二次落库入口，`tool_name` 仍是 `run_code`）。
- 图表、统计、数据清洗等高层工具的实际实现路径是 **agent 内部生成 Python/R 脚本并调用 `run_code` 执行**。也就是说用户看到的所有分析结果和图表，背后一定有对应的 `run_code` / `run_r_code` 记录，代码完整存在于磁盘。
- 前端 `TOOL_NAME_DISPLAY` 中 `stat_test`、`chart_session`、`clean_data` 等条目**从未被触发**，属于僵尸代码。

这意味着筛选 `tool_name ∈ {run_code, run_r_code}` 即可覆盖"所有结果和图表的可复现代码"，无需改动后端写路径。

**脚本中的代码不含 `pd.read_csv`**，而是使用 sandbox 注入的 `df` / `datasets` 变量（`src/nini/sandbox/executor.py:689` 附近）。例如 `data/sessions/b2bac9852f3a` 中的真实记录：

```python
output_df = df.copy()
output_df['x_norm'] = (output_df['x'] - output_df['x'].mean()) / output_df['x'].std()
```

要实现"开箱执行"，下载包必须生成前导代码离线等价重建 `df` / `datasets`，并附带原始数据文件与依赖清单。

## 完整工具调用时间线的审计通道（不在本设计范围内）

将面板聚焦代码后，"完整工具调用时间线"审计仍通过以下通道满足：

1. **聊天流（主要）**：`MessageBubble` 在助手消息里内联展示工具调用与结果，按消息顺序即天然完整时间线。
2. **后端 `memory.jsonl`（权威）**：每会话 `data/sessions/{id}/memory.jsonl`，所有工具调用持久化，经得起推敲——目前没有专门 UI 查看器，若未来需要可另立 feature。

## 目标

1. 面板重定位为**分析代码档案**——只展示可下载、可本地复现的 `run_code` / `run_r_code` 记录。
2. 用户可**单条下载**为自包含 zip，**批量下载**整个会话的代码档案。
3. 下载包"开箱可执行"——附带原始数据集、依赖清单、一键运行脚本。
4. 文案语义化、术语统一，让科研用户一眼理解面板用途。

## 非目标

- 不修改 `save_code_execution` 的字段结构或写入时机。
- 不打包已生成的产物（图表 PNG、输出 CSV）；这些已在工作区文件 Tab 与 `ArtifactGallery` 提供下载。
- 不提供"在线重跑"入口；只支持离线下载。
- 不新增独立的工具调用审计面板（依赖聊天流 + `memory.jsonl`）。

## 设计

### 一、面板重命名与文案

| 位置 | 现状 | 新文案 |
|---|---|---|
| Sidebar Tab | 执行历史 | 代码档案 |
| 面板空态标题 | 暂无执行历史 | 暂无代码记录 |
| 面板空态副标题 | 代码执行记录将显示在此处 | 当 Agent 运行分析或绘制图表时，执行过的 Python / R 代码会归档于此，可下载复现 |
| 计数行 | 共 N 步执行记录 | 共 N 份代码归档 |
| 卡片小节 `REQUEST` | REQUEST | 代码 |
| 卡片小节 `RESPONSE` | RESPONSE | 运行结果 |
| `脚本资源：script_xxx` | 原 hash | 隐去哈希，次要元信息一行展示（"脚本 ID · 执行时间 · 重试于 …"） |
| `输出资源：ds_xxx` | 原 hash | `生成产物`：通过 `index.json` 反查真实文件名（如 `normalized.csv`、`sales_chart.png`） |
| `TOOL ARGS` | 保留 | 移至"参数详情"折叠区，次要 |

### 二、卡片标题生成规则

按 `tool_args.purpose` + `intent`/`label` 生成可读标题（图标使用 `lucide-react`，不用 emoji，与项目 UI 一致）：

| purpose | 图标 | 标题格式 |
|---|---|---|
| `visualization` | `BarChart3` | 图表：\<intent 或 label 或 "未命名"\> |
| `export` | `Package` | 导出：\<intent 或 label\> |
| `transformation` | `Wrench` | 数据转换：\<intent 或 label\> |
| `exploration`（默认） | `Search` | 探索分析：\<intent 或 label\> |

同时显示语言角标（`python` / `r`）与执行状态图标（成功 / 失败 / 运行中），与当前 `StatusIcon` 保持一致。

### 三、过滤规则

`CodeExecutionPanel` 渲染时只保留 `tool_name ∈ {run_code, run_r_code}` 的记录。其他 `tool_name` 的记录即使已经持久化也不展示。

**清理**：删除 `TOOL_NAME_DISPLAY` 与 `TOOL_ICON_MAP` 中不会出现的条目（`stat_test`、`stat_model`、`stat_interpret`、`chart_session`、`create_chart`、`report_session`、`generate_report`、`export_report`、`workspace_session`、`fetch_url`、`image_analysis`、`load_dataset`、`preview_data`、`data_summary`、`clean_data`、`task_state`、`dataset_catalog`、`dataset_transform`）。仅保留 `run_code` / `run_r_code` 所需的配置。

### 四、可复现 bundle 结构

#### 单条下载

```
<intent-slug>-<short-id>.zip
├── README.md              # 意图、时间、输入/输出清单、运行方法、已知约束
├── script.py (或 .R)      # patched 脚本（含自动生成的头部与前导）
├── requirements.txt       # Python 依赖（R 脚本则为 install.R）
├── run.sh                 # 一键执行脚本
└── datasets/              # 从 workspace/datasets/ 复制的输入数据
    └── <dataset_name>.csv
```

#### 批量下载

```
code-archive-<session_id_short>-<YYYYMMDD>.zip
├── README.md              # 时间线索引，每步意图 + 输入 + 输出 + 脚本路径
├── requirements.txt       # 跨所有脚本去重合并（Python）
├── install.R              # 跨所有脚本去重合并（R；与 Python 并存）
├── datasets/              # 所有被引用的数据集去重复制
├── 01_<intent-slug>/
│   ├── script.py
│   └── README.md（简短，指向顶层索引）
├── 02_<intent-slug>/
│   └── script.R
└── run_all.sh             # 按时间顺序执行所有脚本
```

- 时间排序：按 `created_at` **升序**（便于按真实发生顺序复现）。
- 目录前缀 `NN_` 避免 intent slug 重名冲突。
- `slug` 生成规则：取 `intent`（或 `label`、或 `purpose`）→ 中文转拼音或直接保留（实现阶段定）→ 非字母数字替换为 `-` → 截断 40 字符。

#### 脚本 patch 模板（Python）

原代码不变，仅在前后追加：

```python
# ========== Nini 代码档案 ==========
# 意图：<intent 或 "未命名">
# 执行时间：<created_at ISO>
# 来源会话：<session_id_short> / 执行 ID：<execution_id>
# 原始 tool：<tool_name> (purpose=<purpose>)
# ===================================

from pathlib import Path
import pandas as pd

# --- 自动加载输入数据（Nini 沙盒注入变量的离线等价） ---
_DATASETS_DIR = Path(__file__).parent / "datasets"
datasets = {p.stem: pd.read_csv(p) for p in _DATASETS_DIR.glob("*.csv")}

# --- 选定当前数据集（对应 tool_args.dataset_name） ---
<若 dataset_name 非空：df = datasets["<stem>"].copy()>
<若 dataset_name 为空：省略 df 绑定>

# --- 原始代码 ---
<exec.code 原文>

# --- 保存变更（若存在标准输出变量） ---
if "output_df" in dir():
    output_df.to_csv(Path(__file__).parent / "output.csv", index=False)
elif "result_df" in dir():
    result_df.to_csv(Path(__file__).parent / "result.csv", index=False)
```

**澄清**：末尾 `to_csv(...)` 是**本地重跑时产出新文件**，不是打包已有产物。这与"非目标：不打包产物"不冲突。

**已知约束（README 显式写明）**：对于 `purpose=visualization` 的脚本，sandbox 会自动捕获 `plotly` 的 figure 变量并导出图片，但离线脚本不含这层捕获。用户本地运行只会得到 figure 对象而看不到图，需要自行追加 `fig.show()` 或 `fig.write_html("chart.html")`。**不通过 patch 注入伪捕获代码**——那会冒充沙盒行为且不可靠。

#### 依赖识别（Python）

- 用 `ast.parse` 抽取脚本顶层 `import` / `from ... import`。
- 以 `src/nini/sandbox/policy.py:ALLOWED_IMPORT_ROOTS` 过滤 stdlib 与内置模块（不需要 pip 安装）。
- 经小型别名表映射为 pypi 包名：
  - `cv2` → `opencv-python`
  - `sklearn` → `scikit-learn`
  - `PIL` → `Pillow`
  - 其余保持原名（`pandas`、`numpy`、`plotly`、`matplotlib`、`scipy`、`seaborn` 等）
- 无法识别时保留原 import 名，生成 `requirements.txt` 时加 `# unknown: <name>` 注释供用户手工核对。

#### `run.sh`（Python 单条）

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python script.py
```

#### `run_all.sh`（批量）

按时间顺序逐步执行 `NN_*/script.py|.R`，遇错 `set -e` 立即停止。

#### R 脚本处理

结构对称（`script.R` + `install.R` + `run.sh` 或 `run.ps1`）。**R 端数据注入的具体方言**（`tidyverse::read_csv` vs `utils::read.csv`，列类型推断策略）延迟到实现阶段对照 `src/nini/sandbox/r_executor.py` 的实际注入代码再定。本 spec 不预先承诺 R patch 的具体代码模板。

### 五、README 生成

#### 单条 bundle 的 `README.md`

```markdown
# <intent 或 "未命名代码归档">

来源：Nini 会话 `<session_id_short>` · 执行 ID `<execution_id>`
时间：<created_at>
类型：<purpose 中文名>
语言：<python|r>

## 输入数据

- `datasets/<name>.csv`（<rows> 行 × <cols> 列）

## 预期产出

- <从 output_resource_ids 反查后的人类可读列表>

## 运行

```bash
bash run.sh
```

需要 Python >= 3.11。依赖见 `requirements.txt`。

## 已知约束

<若 purpose=visualization：包含图表渲染约束说明>
```

#### 批量 bundle 的 `README.md`

顶部索引 + 按时间顺序的步骤列表，每步一行：序号 / 时间 / 类型 / 意图 / 脚本路径 / 输入 / 输出。

### 六、接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `GET /api/sessions/{sid}/executions/{eid}/bundle` | 单条 zip 下载 |
| `GET /api/sessions/{sid}/executions/bundle` | 批量 zip 下载（整会话，按时间升序）|

两个端点均返回 `application/zip`，`Content-Disposition: attachment; filename=...`。使用 `io.BytesIO` 流式构建，无磁盘临时文件。

**选型说明**：保留两个端点以符合 REST 资源层级，而非合并为 `?ids=<csv>` 查询参数。差别轻微，层级表达更清晰。

### 七、后端模块拆分

新增 `src/nini/workspace/code_bundle.py`（不扩张 `manager.py` 2000+ 行的体量）：

```python
def build_single_bundle(ws: WorkspaceManager, execution_id: str) -> bytes: ...
def build_batch_bundle(ws: WorkspaceManager) -> bytes: ...

# 内部工具
def _patch_script(code: str, language: str, tool_args: dict, meta: dict) -> str: ...
def _extract_dependencies(code: str, language: str) -> list[str]: ...
def _resolve_dataset_files(ws: WorkspaceManager, tool_args: dict) -> list[Path]: ...
def _resolve_output_names(ws: WorkspaceManager, output_resource_ids: list[str]) -> list[str]: ...
def _make_slug(intent: str | None, label: str | None, purpose: str) -> str: ...
def _render_single_readme(record: dict, resolved: ResolvedMeta) -> str: ...
def _render_batch_readme(records: list[dict], resolved_list: list[ResolvedMeta]) -> str: ...
```

API 路由新增在 `src/nini/api/workspace_routes.py`（或就近的 executions 路由文件），仅负责参数校验与流式 response，业务逻辑全部委托 `code_bundle`。

### 八、前端改动

- **`web/src/components/CodeExecutionPanel.tsx` 大改**：
  - 按 `tool_name ∈ {run_code, run_r_code}` 过滤
  - 新的卡片标题（`purpose` → 图标 + 中文前缀 + `intent`）
  - 新的展开区块：代码 / 输入数据 / 生成产物 / 运行结果 / 参数详情（折叠）
  - 每卡片新增 `Download` 图标按钮 → 调 `/bundle` 单条接口
  - 面板顶部新增 `全部下载` 按钮 → 调批量接口
  - 删除僵尸 `TOOL_NAME_DISPLAY` / `TOOL_ICON_MAP` 条目

- **`web/src/components/WorkspaceSidebar.tsx`**：Tab 名 `执行历史` → `代码档案`。`workspacePanelTab` 枚举值保持 `executions` 不变（避免状态迁移）。

- **新增 util** `web/src/components/downloadBundle.ts`：封装调用 `/bundle` 接口并触发浏览器下载，复用 `downloadUtils.ts` 的 blob 下载模式。

### 九、测试

#### 后端 `tests/test_code_bundle.py`

- 单条 bundle：
  - 含 `README.md` / `script.py` / `requirements.txt` / `run.sh` / `datasets/<name>.csv`
  - 脚本头部含意图、时间、执行 ID 注释
  - `dataset_name` 非空时注入 `df = datasets[...]`
  - `dataset_name` 为空时省略 `df` 绑定
- 批量 bundle：
  - 按 `created_at` 升序排列目录 `01_*` → `NN_*`
  - `requirements.txt` 跨脚本去重
  - `datasets/` 跨脚本去重
  - 含 `run_all.sh`，顺序与目录一致
- `_extract_dependencies`：
  - stdlib 过滤（`os`、`json`、`pathlib`）
  - 别名映射（`cv2` → `opencv-python`、`sklearn` → `scikit-learn`、`PIL` → `Pillow`）
  - 未识别项保留原名并加注释
- `_make_slug`：中文、特殊字符、空值

#### 前端 `web/src/components/CodeExecutionPanel.test.tsx`

- 非 `run_code` / `run_r_code` 记录被过滤不渲染
- 卡片标题按 `purpose` 切换图标与前缀
- 下载按钮触发正确 URL（`/api/sessions/{sid}/executions/{eid}/bundle`）
- 批量下载按钮触发 `/api/sessions/{sid}/executions/bundle`
- 空态文案更新

## 风险与缓解

1. **数据集隐私**：bundle 会包含用户原始数据。按用户决策，不加下载确认弹窗。在 README 中保留"本压缩包含输入数据集"一行提示，便于用户后续分享时警觉。
2. **依赖识别不准**：未知 import 保留原名 + 注释，用户可手工修正。不阻断下载。
3. **plotly 图表离线不显示**：README 明确说明，不注入伪捕获代码。
4. **R 脚本实现不确定性**：spec 不预先承诺 R patch 模板，实现时对照 `r_executor.py` 定。计划阶段会拆一个专门任务覆盖。

## 实施顺序建议

1. 后端 `code_bundle.py` + 单条 bundle + 单元测试
2. 后端 批量 bundle + 测试
3. API 路由 + 集成测试
4. 前端面板文案与过滤
5. 前端下载按钮与接口对接
6. R 脚本支持（如果 MVP 不涵盖 R，可作为单独迭代）
7. `CodeExecutionPanel.test.tsx` 更新与补齐
