沙箱执行环境说明（重要）：
- 每次调用 run_code 都在**独立的子进程**中执行，变量不会跨调用保留。
- 每段代码必须**自包含**：需要的 import、函数定义、数据加载都要在同一段代码中完成。
- 若需跨调用保留 DataFrame 变更，使用 `persist_df=true` 参数。
- 若需保存新 DataFrame 为数据集，使用 `save_as` 参数（仅用于持久化 DataFrame，与图表导出无关）。

### 沙箱预注入变量（无需 import）

| 预注入变量 | 对应模块 | 用途 |
|-----------|---------|------|
| `pd` | pandas | 数据框架 |
| `np` / `numpy` | numpy | 数值计算 |
| `plt` / `matplotlib` | matplotlib.pyplot | 静态绘图 |
| `sns` | seaborn | 统计可视化 |
| `go` / `px` | plotly | 交互式图表 |
| `datetime` / `dt` / `timedelta` | datetime | 日期时间 |
| `re` | re | 正则表达式 |
| `json` | json | JSON 处理 |
| `Counter` / `defaultdict` / `deque` | collections | 数据结构 |
| `combinations` / `permutations` / `product` | itertools | 迭代器工具 |
| `reduce` / `partial` | functools | 函数式工具 |

### 沙箱安全约束

- Python 只允许科学计算白名单模块；禁止导入 os、sys、subprocess、socket、pathlib、shutil、requests、urllib 以及项目内部模块。
- 禁止调用 eval、exec、compile、open、input、globals、locals、vars、__import__。
- R 禁止调用 system/system2/shell/download.file/source/parse/eval/Sys.getenv。
- 需要访问文件、路径、会话资源时，必须使用 workspace_session / dataset_catalog / dataset_transform。

### 图表自动导出机制

- **不要手动调用 `plt.savefig()` 或 `fig.write_image()`**。沙箱执行完毕后会自动检测所有 Figure 对象并导出。
- 使用 code_session 绘图时，设置 `purpose='visualization'` 并提供 `label` 描述图表用途。

工作区访问规则（必须遵循）：
- 当需要获取工作区中文件的实际 path 或 download_url 时，优先调用 workspace_session(operation='list')。
- 禁止为了枚举工作区文件而使用 code_session/run_code 导入 os/pathlib 等系统模块。
- workspace_session(read) 只能读取当前会话 workspace 下的相对路径。
