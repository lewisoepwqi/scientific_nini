# API 与 WebSocket 协议

Nini 对外分为两类接口：

- HTTP：会话管理、上传、下载、健康检查
- WebSocket：Agent 实时对话与工具事件流

## HTTP API

基础路径：`/api`

### 1) `GET /api/health`

服务健康检查。

响应示例：

```json
{"status":"ok","version":"0.1.0"}
```

### 2) `GET /api/sessions`

获取会话列表（内存 + 磁盘持久化）。

响应示例：

```json
{
  "success": true,
  "data": [
    {"id": "abc123", "message_count": 12, "source": "memory"},
    {"id": "def456", "message_count": 4, "source": "disk"}
  ]
}
```

### 3) `POST /api/sessions`

创建新会话。

响应示例：

```json
{"success": true, "data": {"session_id": "abc123"}}
```

### 4) `DELETE /api/sessions/{session_id}`

删除会话，并清除持久化目录。

响应示例：

```json
{"success": true, "data": {"deleted": "abc123"}}
```

### 5) `POST /api/upload`

上传数据文件到指定会话（`multipart/form-data`）。

字段：

- `file`：文件对象
- `session_id`：目标会话 ID

支持后缀：`csv/xlsx/xls/tsv/txt`

成功响应示例：

```json
{
  "success": true,
  "dataset": {
    "id": "8d6d58b7a7cf",
    "session_id": "abc123",
    "name": "experiment.csv",
    "file_path": ".../data/uploads/8d6d58b7a7cf.csv",
    "file_type": "csv",
    "file_size": 12034,
    "row_count": 200,
    "column_count": 8
  }
}
```

### 6) `GET /api/artifacts/{session_id}/{filename}`

下载会话产物（图表/报告导出文件）。

### 7) `GET /api/sessions/{session_id}/messages`

获取会话历史的 canonical 消息序列。该接口同时服务于：

- 页面刷新后的历史恢复
- WebSocket 重连后的 session reconcile
- `retry` / `stop` 后的回合级对账

响应示例：

```json
{
  "success": true,
  "data": {
    "session_id": "abc123",
    "messages": [
      {
        "role": "assistant",
        "content": "这是完整回答",
        "_ts": "2026-03-03T10:00:02+00:00",
        "message_id": "turn_001-0",
        "turn_id": "turn_001",
        "event_type": "text",
        "operation": "replace"
      },
      {
        "role": "assistant",
        "content": "完整推理结论",
        "_ts": "2026-03-03T10:00:03+00:00",
        "turn_id": "turn_001",
        "event_type": "reasoning",
        "operation": "complete",
        "reasoning_id": "reason_001"
      },
      {
        "role": "tool",
        "content": "执行成功",
        "_ts": "2026-03-03T10:00:04+00:00",
        "message_id": "tool-result-call_001",
        "turn_id": "turn_001",
        "event_type": "tool_result",
        "operation": "complete",
        "tool_call_id": "call_001",
        "tool_name": "run_code",
        "status": "success",
        "intent": "计算均值"
      }
    ]
  }
}
```

字段约定：

| 字段 | 说明 |
|------|------|
| `_ts` | 消息写入时间，前端恢复历史时用于稳定排序 |
| `turn_id` | 一轮对话的稳定标识；重连、停止、重试都以它为边界 |
| `message_id` | assistant/tool 可见消息的稳定身份；前端用于 append/replace 去重 |
| `event_type` | `message` / `text` / `reasoning` / `tool_call` / `tool_result` / `chart` / `data` / `artifact` / `image` |
| `operation` | `append` / `replace` / `complete`；历史恢复默认应按最终态解释 |
| `reasoning_id` | reasoning 节点的稳定身份，用于合并流式推理与历史恢复 |

兼容说明：

- 旧 `memory.jsonl` 记录在读取时会自动补齐 `turn_id`、`message_id`、`event_type`、`operation`
- 前端应优先以 `message_id` / `reasoning_id` / `turn_id` 归并，不再依赖纯文本猜测
- WebSocket 重连后建议重新拉取该接口，对当前会话做全量 reconcile

## WebSocket

连接地址：`/ws`

### 客户端发送消息

#### `chat`

```json
{"type": "chat", "content": "帮我做 t 检验", "session_id": "abc123"}
```

说明：

- `session_id` 可选，不传时服务端创建新会话
- `content` 不能为空

#### `ping`

```json
{"type": "ping"}
```

### 服务端事件类型

统一结构：

```json
{
  "type": "text|tool_call|tool_result|chart|data|artifact|image|done|error|reasoning|analysis_plan|plan_step_update|plan_progress|task_attempt|context_compressed|retrieval|iteration_start|session|pong",
  "data": {},
  "session_id": "abc123",
  "tool_call_id": "call_xxx",
  "tool_name": "t_test",
  "turn_id": "turn_001",
  "metadata": {
    "message_id": "turn_001-0",
    "operation": "append"
  }
}
```

### 消息去重与语义操作（metadata 字段）

从 v0.2.0 开始，WebSocket TEXT 事件支持 `metadata` 字段，用于消息去重和语义操作控制。

| 字段                  | 类型   | 说明                                          |
|-----------------------|--------|-----------------------------------------------|
| `metadata.message_id` | string | 消息唯一标识，格式为 `{turn_id}-{sequence}`   |
| `metadata.operation`  | string | 操作类型：`append`\|`replace`\|`complete`      |

#### operation 类型说明

| 操作类型   | 说明                     | 使用场景                     |
|------------|--------------------------|------------------------------|
| `append`   | 追加内容到现有消息       | LLM 流式输出片段             |
| `replace`  | 替换整个消息内容         | 工具生成完整内容（如报告）   |
| `complete` | 标记消息完成并清理缓冲区 | 流式结束标记                 |

#### 消息ID格式

```
{turn_id}-{sequence}

示例：
- turn_abc123-0    # 某轮对话的第一条消息
- turn_abc123-1    # 同轮对话的第二条消息
```

#### 向后兼容性

- 新客户端收到带 `metadata` 的事件：使用新的去重逻辑
- 旧客户端收到带 `metadata` 的事件：忽略新字段，正常显示内容
- 新客户端收到无 `metadata` 的事件：回退到传统追加逻辑

事件说明：

| 事件类型 | 说明 |
|---------|------|
| `session` | 返回当前会话 ID（连接建立时） |
| `text` | 模型流式文本片段 |
| `tool_call` | 准备调用某个技能 |
| `tool_result` | 技能执行结果 |
| `chart` | 图表 JSON（Plotly 格式） |
| `data` | 数据预览（表格） |
| `artifact` | 可下载产物（报告、图表文件等） |
| `image` | 图像内容（base64 或 URL） |
| `reasoning` | Agent 决策推理过程（方法选择、参数判断等） |
| `analysis_plan` | 结构化分析步骤列表（任务规划） |
| `plan_step_update` | 单个分析步骤状态变更 |
| `plan_progress` | 整体计划进度（当前步骤 / 下一步提示） |
| `task_attempt` | 任务执行尝试记录（含重试轨迹） |
| `context_compressed` | 上下文自动压缩通知 |
| `retrieval` | 知识库检索触发通知 |
| `iteration_start` | ReAct 迭代开始 |
| `done` | 本轮执行结束 |
| `error` | 错误信息 |
| `pong` | `ping` 响应 |

## 技能清单（默认注册）

**任务规划**
- `task_write`：LLM 驱动的结构化任务列表生成

**数据操作**
- `load_dataset`、`preview_data`、`data_summary`
- `clean_data`、`recommend_cleaning_strategy`、`data_quality`

**统计分析**
- `t_test`、`mann_whitney`（t_test 自动降级目标）
- `anova`、`kruskal_wallis`（anova 自动降级目标）
- `correlation`、`regression`、`multiple_comparison`

**代码执行**
- `run_code`：Python 沙箱（AST 静态检查 + 进程隔离）
- `run_r_code`：R 语言沙箱（需本地 R 环境，运行时条件注册）

**可视化**
- `create_chart`（7 种图表 + 6 种期刊风格）、`export_chart`

**网络 / 多模态**
- `fetch_url`（网页抓取）

**产物生成**
- `generate_report`、`export_report`、`organize_workspace`

**复合技能（多步流程）**
- `complete_comparison`、`complete_anova`、`correlation_analysis`、`interpret_statistical_result`

## 错误码说明（HTTP）

- `400`：参数错误、文件解析失败、不支持扩展名
- `404`：会话或产物不存在
- `413`：上传文件超过限制
- `500`：服务端异常
