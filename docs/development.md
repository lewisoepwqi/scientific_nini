# 开发与发布指南

本文档面向仓库维护者，描述本地开发、测试与发布流程。

## 1. 本地开发

### 安装依赖

```bash
pip install -e .[dev]
cd web && npm install
```

说明：`dev` 依赖组已包含报告 PDF 导出依赖 `weasyprint`。
若当前环境仅需补装 PDF 导出能力，可执行 `pip install -e .[pdf]`。

### 启动方式

- 后端（含静态站点挂载）：

```bash
nini start --reload
```

- 前端独立开发（可选）：

```bash
cd web && npm run dev
```

## 2. 测试与质量检查

### 后端测试

```bash
pytest -q
```

### 前端构建验证

```bash
cd web && npm run build
```

建议在提交前至少执行以上两项。

### 提示词相关最小验证

涉及系统提示词、运行时上下文、知识注入、Markdown Skill 注入时，至少执行：

```bash
pytest tests/test_prompt_guardrails.py tests/test_prompt_contract.py tests/test_prompt_improvements.py tests/test_ecosystem_alignment.py -q
```

架构说明见 [prompt-architecture.md](./prompt-architecture.md)。

## 3. 代码组织约定

- 后端业务代码：`src/nini/`
- 前端代码：`web/src/`
- 测试代码：`tests/`
- 文档：`docs/`
- 本地数据：`data/`（不提交）

## 4. 会话与数据文件

运行中产生的数据默认写入：

```text
data/
├── uploads/
├── sessions/{session_id}/
└── db/nini.db
```

如需重置本地状态，可手动删除对应目录。

## 5. 打包发布流程

### 构建

```bash
python -m build
```

### 轮子安装验证（推荐）

```bash
python -m venv /tmp/nini-smoke
/tmp/nini-smoke/bin/pip install dist/nini-0.1.0-py3-none-any.whl
/tmp/nini-smoke/bin/nini doctor
/tmp/nini-smoke/bin/nini start --port 8011
```

再用健康检查确认：

```bash
curl http://127.0.0.1:8011/api/health
```

## 6. 常见维护任务

- 增加新工具：在 `src/nini/tools/` 继承 `Tool` 实现，并在 `tools/registry.py:create_default_tool_registry()` 中注册
- 扩展 WebSocket 事件：更新 `src/nini/agent/runner.py` 与 `web/src/store.ts`
- 新增配置项：更新 `src/nini/config.py`、`nini init` 默认模板与文档
- 升级模型路由：更新 `src/nini/agent/model_resolver.py` 与对应测试

## 7. Agent 可靠性运行时

当前运行时可靠性增强围绕三条主线展开：

- `pending_actions`：统一记录脚本未执行、工具失败未恢复、承诺产物未落地、等待用户确认、仅描述下一步未执行等待处理状态。
- `CompletionEvidence`：completion check 先收集结构化证据，再映射为校验项与 recovery prompt，不再仅靠关键词和零散提示。
- `HarnessSessionSnapshot`：每轮 harness 结束后写入轻量快照，供 `nini debug ...` 和问题复盘复用。

### `pending_actions` 边界

- 只记录“还需要继续处理的动作”，不复制完整 task manager 状态。
- 只保存摘要字段与最小元数据，不保存大对象或完整 trace。
- 真实来源仍在原始消息、工具结果和 trace；`pending_actions` 只是统一账本，不是新的业务事实源。

### Tool Exposure Policy 边界

- 策略只负责在运行前收缩不该出现的工具面。
- 策略不会替代模型对分析方法的语义判断。
- 当前只做最小三阶段裁剪：`profile / analysis / export`。
- 高风险工具是否重新暴露，仍受会话级授权状态约束。

### 非目标

- 不在本轮把 `runner.py` 拆成大规模模块化架构。
- 不把整个 `Session` 改造成不可变对象。
- 不引入新的通用 toolchain 框架来统一所有工具链路。
