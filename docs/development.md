# 开发与发布指南

本文档面向仓库维护者，描述本地开发、测试与发布流程。

## 1. 本地开发

### 安装依赖

```bash
pip install -e .[dev]
cd web && npm install
```

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

- 增加新技能：在 `src/nini/skills/` 实现并在 `create_default_registry()` 注册
- 扩展 WebSocket 事件：更新 `src/nini/agent/runner.py` 与 `web/src/store.ts`
- 新增配置项：更新 `src/nini/config.py`、`nini init` 默认模板与文档
- 升级模型路由：更新 `src/nini/agent/model_resolver.py` 与对应测试
