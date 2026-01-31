# 快速开始：任务化分析与多图表管理

> 本文用于本地开发与验证关键流程（任务、图表、建议、分享）。

## 1. 前置条件

- 已配置数据库与缓存（PostgreSQL、Redis）
- 已准备 AI（人工智能）服务所需环境变量（例如 API Key）
- 本地安装 Node.js 与 Python 运行环境

## 2. 启动后端

```bash
cd /home/lewis/coding/scientific_nini/scientific_data_analysis_backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

## 3. 启动 AI 服务

```bash
cd /home/lewis/coding/scientific_nini/ai_service
pip install -r requirements.txt
python -m ai_service.main
```

## 4. 启动前端

```bash
cd /home/lewis/coding/scientific_nini/frontend
npm install
npm run dev
```

## 5. 基本验证路径

1. 上传数据集 → 自动生成任务 → 查看任务阶段
2. 在任务下创建至少 2 个图表 → 查看图表列表与复用
3. 触发 AI 建议 → 选择采纳/不采纳 → 观察路径变化
4. 导出分享包 → 验证包内不含原始数据

## 6. 测试命令

```bash
# 后端
cd /home/lewis/coding/scientific_nini/scientific_data_analysis_backend
pytest

# 前端
cd /home/lewis/coding/scientific_nini/frontend
npm run lint
npm run type-check
```

## 7. 本次验证记录（2026-01-31）

- 基本验证路径：未执行（原因：未在本地启动依赖服务与前端环境）
- 前端 lint/type-check：已执行（无错误）
- 后端 pytest：已执行（19 passed, 1 skipped；tests/perf/test_chart_list_perf.py 跳过；警告：pytest_asyncio DeprecationWarning）
