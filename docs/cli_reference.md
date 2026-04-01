# CLI 参考

可执行入口：`nini`（等价 `python -m nini`）。

## 命令总览

```bash
nini start [--host 127.0.0.1] [--port 8000] [--reload] [--log-level info]
nini init [--env-file .env] [--force]
nini doctor [--surface] [--surface-stage profile|analysis|export]
nini debug summary <session_id>
nini debug snapshot <session_id> --turn-id <turn_id>
nini debug load-session <session_id>
```

## 1) `nini start`

启动 FastAPI + WebSocket + 静态前端。

常用参数：

- `--host`：监听地址，默认 `127.0.0.1`
- `--port`：监听端口，默认 `8000`
- `--reload`：热重载（开发模式）
- `--log-level`：日志级别，支持 `critical/error/warning/info/debug/trace`

示例：

```bash
nini start --host 0.0.0.0 --port 8010 --reload
```

## 2) `nini init`

生成首次运行 `.env` 模板。

参数：

- `--env-file`：输出路径，默认当前目录 `.env`
- `--force`：覆盖已有配置文件

示例：

```bash
nini init
nini init --env-file .env.dev --force
```

## 3) `nini doctor`

执行环境自检，检查：

- Python 版本（`>=3.12`）
- 数据目录可写
- 至少一条模型路由可用
- weasyprint（可选，用于报告 PDF 导出）
- 前端构建产物存在（可选，仅 `WARN`）

若 `weasyprint` 显示 `WARN`：
- 源码环境建议执行 `pip install -e .[dev]`（或仅补装 `pip install -e .[pdf]`）
- 发布包环境建议执行 `pip install nini[pdf]`

示例：

```bash
nini doctor
nini doctor --surface
nini doctor --surface --surface-stage export
```

`--surface` 会输出当前工具面与技能面的诊断快照，包含：

- 当前阶段（`profile / analysis / export`）
- 当前可见工具列表
- 被策略隐藏的工具
- 高风险工具摘要
- 会话级授权状态

## 4) `nini debug`

查看 harness 运行快照，用于排查 completion check、待处理动作和工具暴露问题。

### `nini debug summary <session_id>`

输出某个会话最近一轮的 `HarnessSessionSnapshot`。

### `nini debug snapshot <session_id> --turn-id <turn_id>`

输出指定轮次的快照；若轮次不存在，会返回明确的未找到提示。

### `nini debug load-session <session_id>`

输出最近快照以及其关联的 trace 明细，用于快速复盘某一轮为何进入 `done / blocked / error`。

示例：

```bash
nini debug summary 9f8e7d6c5b4a
nini debug snapshot 9f8e7d6c5b4a --turn-id 12ab34cd56ef
nini debug load-session 9f8e7d6c5b4a
```

## 向后兼容行为

`nini --port 9000` 会自动等价为 `nini start --port 9000`。

## 常见退出码

- `0`：命令成功
- `1`：检查失败或参数导致命令失败
- `130`：用户中断（`Ctrl+C`）
