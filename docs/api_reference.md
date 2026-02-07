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
  "type": "text|tool_call|tool_result|chart|data|done|error|session|pong",
  "data": {},
  "session_id": "abc123",
  "tool_call_id": "call_xxx",
  "tool_name": "t_test"
}
```

关键事件：

- `session`：返回当前会话 ID
- `text`：模型流式文本片段
- `tool_call`：准备调用某个技能
- `tool_result`：技能执行结果
- `chart`：图表 JSON（Plotly）
- `data`：数据预览
- `done`：本轮执行结束
- `error`：错误信息
- `pong`：`ping` 响应

## 技能清单（默认注册）

- `load_dataset`
- `preview_data`
- `data_summary`
- `t_test`
- `anova`
- `correlation`
- `regression`
- `create_chart`
- `export_chart`
- `clean_data`
- `generate_report`
- `run_code`

## 错误码说明（HTTP）

- `400`：参数错误、文件解析失败、不支持扩展名
- `404`：会话或产物不存在
- `413`：上传文件超过限制
- `500`：服务端异常
