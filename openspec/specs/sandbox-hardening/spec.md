## ADDED Requirements

### Requirement: df.eval / df.query 表达式拦截
沙箱执行器 SHALL 在 `_sandbox_worker` 中 monkey-patch `pd.DataFrame.eval` 和 `pd.DataFrame.query`，拦截包含 `__import__`、`exec`、`compile`、`open`、`os.`、`subprocess`、`sys.` 关键词的表达式字符串，抛出 `SandboxPolicyError` 并提供替代建议。

#### Scenario: df.eval 包含 __import__ 被拦截
- **WHEN** 用户代码执行 `df.eval("__import__('os').system('id')")`
- **THEN** 沙箱抛出 `SandboxPolicyError`，错误消息包含"不允许在 df.eval 中使用 __import__"

#### Scenario: df.eval 合法表达式正常执行
- **WHEN** 用户代码执行 `df.eval("age > 30")`
- **THEN** 表达式正常求值并返回过滤结果

#### Scenario: df.query 合法表达式正常执行
- **WHEN** 用户代码执行 `df.query("salary > 50000")`
- **THEN** 查询正常执行并返回过滤结果

### Requirement: pd.read_* 路径限制
沙箱执行器 SHALL hook `pd.read_csv`、`pd.read_excel`、`pd.read_json`、`pd.read_pickle` 等文件读取函数，将传入的路径参数限制在沙箱 `working_dir` 内。拒绝绝对路径、含 `..` 的路径、以及 resolve 后超出 `working_dir` 的路径。

#### Scenario: 读取工作目录内文件成功
- **WHEN** 用户代码执行 `pd.read_csv("data.csv")`，且 `data.csv` 在 `working_dir` 内
- **THEN** 正常读取并返回 DataFrame

#### Scenario: 读取绝对路径被拒绝
- **WHEN** 用户代码执行 `pd.read_csv("/etc/passwd")`
- **THEN** 抛出 `SandboxPolicyError`，错误消息包含"不允许读取工作目录之外的文件"

#### Scenario: 路径遍历被拒绝
- **WHEN** 用户代码执行 `pd.read_csv("../../../../etc/passwd")`
- **THEN** 抛出 `SandboxPolicyError`，错误消息包含"路径遍历"

### Requirement: type 内建限制
沙箱执行器 SHALL 从 `_BASE_SAFE_BUILTINS` 移除 `type`，替换为 `safe_type` 函数：仅支持单参数形式 `safe_type(obj)` 返回 `type(obj)`；调用多参数形式时抛出 `SandboxPolicyError`。

前提：AST 层已有 `__dunder__` 属性访问拦截（`policy.py:355-365`），`obj.__class__.__subclasses__()` 属性链逃逸路径已被阻断。`safe_type` 封堵的是 `type(lambda:0)(code,{},{})` 这条不依赖属性链的直接调用路径。

#### Scenario: 单参数 type 正常工作
- **WHEN** 用户代码执行 `type(42)`
- **THEN** 返回 `<class 'int'>`

#### Scenario: 多参数 type 被拦截
- **WHEN** 用户代码执行 `type("X", (), {})`
- **THEN** 抛出 `SandboxPolicyError`，错误消息包含"不允许动态创建类型"
