# 《代码审查报告》

**项目**: Nini - 科研数据分析 AI Agent 平台
**审查日期**: 2026-02-13
**审查方法**: 静态代码审查 + 配置审查 + 架构分析
**审查团队**: Agent Team (Coordinator + 5 Specialists)

---

## 0. 审查概览

### 0.1 仓库地图

| 维度 | 内容 |
|-----|------|
| **后端技术栈** | Python 3.12+, FastAPI, Uvicorn, hatchling |
| **前端技术栈** | TypeScript, React 18, Vite, Tailwind CSS, Zustand |
| **核心依赖** | pandas, numpy, scipy, statsmodels, plotly, matplotlib, openai, anthropic, llama-index |
| **入口点** | `src/nini/__main__.py` (CLI), `src/nini/app.py:create_app()` (FastAPI) |
| **测试框架** | pytest + pytest-asyncio |
| **CI/CD** | GitHub Actions (ci.yml) |

### 0.2 核心架构

```
单进程架构：HTTP API + WebSocket + 静态文件服务

┌─────────────────────────────────────────────────────┐
│                    FastAPI App                       │
├──────────────┬──────────────┬───────────────────────┤
│  HTTP Routes │  WebSocket   │    Static Files       │
│  /api/*      │  /ws         │    (前端 SPA)          │
├──────────────┴──────────────┴───────────────────────┤
│                   AgentRunner                        │
│         (ReAct 循环：消息 → LLM → 技能 → 事件)         │
├──────────────────────────────────────────────────────┤
│  ModelResolver (多 LLM 客户端 + 故障降级)              │
├──────────────────────────────────────────────────────┤
│  SkillRegistry (统计/可视化/数据/代码执行/报告)         │
├──────────────────────────────────────────────────────┤
│  SandboxExecutor (进程隔离 + AST 策略 + 资源限制)      │
└──────────────────────────────────────────────────────┘
```

### 0.3 结论摘要（按重要性排序）

1. **🔴 P0 级风险**: 无（但 P1 问题需紧急处理）
2. **🟠 沙箱安全严重缺陷**: `SAFE_BUILTINS` 暴露 `__import__`，可完全绕过沙箱
3. **🟠 LLM 调用无超时**: 可能导致无限等待
4. **🟡 CI 缺失质量门禁**: 无覆盖率检查、无 lint 检查、无类型检查
5. **🟡 全局单例过多**: 导致测试困难、隐式耦合
6. **🟡 内存泄漏风险**: 多个全局字典未在会话结束时清理
7. **🟡 可观测性缺失**: 无 metrics 系统、日志非结构化
8. **🟢 文档质量良好**: CLAUDE.md 详尽，配置文档完整

---

## 1. 风险总览看板

| 编号 | 级别 | 问题标题 | 影响面 | 修复成本 | 证据定位 | 建议负责人 |
|-----|------|---------|-------|---------|---------|-----------|
| S01 | P1 | SAFE_BUILTINS 暴露 __import__ 导致沙箱完全绕过 | 大 | S | src/nini/sandbox/executor.py:36 | 沙箱模块 |
| S02 | P1 | BANNED_CALLS 列表不完整，缺少反射函数 | 大 | M | src/nini/sandbox/policy.py:22-29 | 沙箱模块 |
| S03 | P1 | LLM 调用无超时控制 | 中 | S | src/nini/agent/model_resolver.py:123-147 | Agent模块 |
| S04 | P1 | Windows 平台内存限制完全无效 | 中 | L | src/nini/sandbox/executor.py:29-32 | 沙箱模块 |
| S05 | P1 | CI 缺少覆盖率/lint/类型检查 | 中 | S | .github/workflows/ci.yml:20 | DevOps |
| S06 | P1 | 前端缺少 ESLint/Prettier 配置 | 中 | M | web/package.json | 前端 |
| S07 | P1 | 前端 E2E 测试覆盖不足 | 中 | L | web/e2e/ | 前端QA |
| S08 | P1 | 缺少性能指标收集系统 | 中 | L | 全局 | DevOps |
| S09 | P2 | 全局单例模式导致隐式耦合 | 中 | L | 多处 | 架构 |
| S10 | P2 | Session 类职责过多 | 中 | L | src/nini/agent/session.py:20-127 | Agent模块 |
| S11 | P2 | routes.py 文件过大(1098行) | 小 | M | src/nini/api/routes.py | API模块 |
| S12 | P2 | WorkspaceManager 职责过重 | 小 | L | src/nini/workspace/manager.py | 工作区模块 |
| S13 | P2 | 子模块导入限制不足 | 中 | M | src/nini/sandbox/policy.py:8-20 | 沙箱模块 |
| S14 | P2 | LaneQueue 内存泄漏风险 | 小 | S | src/nini/agent/lane_queue.py:18-24 | Agent模块 |
| S15 | P2 | SessionTokenTracker 内存泄漏 | 小 | S | src/nini/utils/token_counter.py:193-200 | 工具模块 |
| S16 | P2 | AnalysisMemory 内存泄漏 | 小 | S | src/nini/memory/compression.py:526-537 | 记忆模块 |
| S17 | P2 | 日志格式非结构化 | 小 | M | src/nini/app.py:34-37 | 基础设施 |
| S18 | P2 | 缺少请求追踪 ID | 小 | S | src/nini/api/routes.py, websocket.py | API模块 |
| S19 | P2 | Token 计数重复计算影响性能 | 小 | M | src/nini/agent/runner.py:486-490 | Agent模块 |
| S20 | P2 | ModelResolver 降级缺少退避机制 | 小 | M | src/nini/agent/model_resolver.py:795-828 | Agent模块 |
| S21 | P2 | WebSocket 无认证机制 | 小 | M | src/nini/api/websocket.py:41-42 | API模块 |
| S22 | P2 | 缺少 .env.example 文件 | 小 | S | 项目根目录 | 文档 |
| S23 | P3 | mypy 配置不够严格 | 小 | M | pyproject.toml:85-88 | 工程质量 |
| S24 | P3 | 后端缺少模块级测试文件映射 | 小 | M | tests/ | 测试 |
| S25 | P3 | API 文档缺少请求/响应 schema | 小 | M | docs/api_reference.md | 文档 |
| S26 | P3 | 缺少 CONTRIBUTING.md | 小 | M | 项目根目录 | 文档 |
| S27 | P3 | 依赖版本使用 >= 而非固定 | 小 | S | pyproject.toml:12-59 | 供应链 |
| S28 | P3 | 敏感数据可能泄露到日志 | 小 | S | 多处 | 安全 |

---

## 2. 关键问题详述

### 2.1 P1 级问题（紧急处理）

#### S01: SAFE_BUILTINS 暴露 __import__ 导致沙箱完全绕过

- **现象**: `SAFE_BUILTINS` 字典包含 `__import__` 函数
- **风险**: 恶意代码可通过 `__import__('os')` 或 `__builtins__['__import__']('os')` 导入任意模块，完全绕过 AST 静态检查
- **证据**: `src/nini/sandbox/executor.py:36`
  ```python
  SAFE_BUILTINS = {
      "__import__": py_builtins.__import__,  # 致命漏洞
      ...
  }
  ```
- **修复建议**: 立即从 `SAFE_BUILTINS` 中移除 `__import__`，或替换为始终抛出异常的受限函数
- **验证方式**: 测试 `__import__('os').system('echo pwned')` 应被阻止
- **修复成本**: S (10分钟)

#### S02: BANNED_CALLS 列表不完整

- **现象**: `BANNED_CALLS` 仅包含 `__import__, eval, exec, compile, open, input`
- **风险**: 缺少 `getattr/setattr/delattr`（反射）、`globals/locals/vars`（内省）、`dir`、`type` 等危险函数
- **证据**: `src/nini/sandbox/policy.py:22-29`
- **修复建议**: 扩展 `BANNED_CALLS` 或采用白名单策略
- **验证方式**: 测试 `getattr(__builtins__, 'eval')('1+1')` 应被阻止
- **修复成本**: M (1-2小时)

#### S03: LLM 调用无超时控制

- **现象**: OpenAI 和 Anthropic 客户端未设置 HTTP 超时
- **风险**: 网络故障可能导致无限等待，阻塞整个 Agent 循环
- **证据**: `src/nini/agent/model_resolver.py:123-147, 270-295`
- **修复建议**: 在 `AsyncOpenAI` 初始化时添加 `timeout` 参数
- **验证方式**: 模拟网络超时，验证请求能在设定时间内失败
- **修复成本**: S (15分钟)

#### S04: Windows 平台内存限制无效

- **现象**: `resource` 模块在 Windows 不存在，`_set_resource_limits()` 直接返回
- **风险**: Windows 上恶意代码可无限消耗内存
- **证据**: `src/nini/sandbox/executor.py:29-32, 169-188`
- **修复建议**: 使用 `psutil` 或 `pywin32` 实现 Windows 内存监控
- **验证方式**: 在 Windows 上测试内存超限代码被终止
- **修复成本**: L (需要跨平台方案)

#### S05-S07: CI/CD 质量门禁缺失

- **现象**: CI 仅运行 `pytest -q`，无覆盖率、lint、类型检查
- **风险**: 代码质量问题可能在合并后才被发现
- **证据**: `.github/workflows/ci.yml:20`
- **修复建议**:
  1. 添加 `black --check src tests`
  2. 添加 `mypy src/nini`
  3. 添加 `pytest --cov=src/nini --cov-fail-under=60`
- **验证方式**: CI 流水线包含所有检查步骤
- **修复成本**: S (30分钟)

#### S08: 缺少性能指标收集

- **现象**: 系统未集成 Prometheus 或其他 metrics 机制
- **风险**: 无法监控系统健康状态和性能趋势
- **证据**: 整个代码库
- **修复建议**: 集成 `prometheus-client`，收集 LLM 延迟、技能执行时间、活跃会话数等
- **验证方式**: 访问 `/metrics` 端点可获取指标
- **修复成本**: L (需要系统设计)

---

### 2.2 P2 级问题（重要处理）

#### S09: 全局单例导致隐式耦合

- **现象**: `settings`, `session_manager`, `model_resolver`, `sandbox_executor` 均为全局单例
- **风险**: 测试困难，模块间隐式依赖
- **证据**: `src/nini/config.py:152`, `src/nini/agent/session.py:309`, `src/nini/agent/model_resolver.py:852`
- **修复建议**: 采用依赖注入模式
- **修复成本**: L (需要重构)

#### S14-S16: 内存泄漏风险

- **现象**: `LaneQueue._locks`, `SessionTokenTracker._trackers`, `AnalysisMemory._analysis_memories` 全局字典持续增长
- **风险**: 长期运行时内存缓慢增长
- **证据**: 多处
- **修复建议**: 在 `SessionManager.remove_session()` 中调用对应的清理函数
- **修复成本**: S (每个 15分钟)

#### S17-S18: 可观测性不足

- **现象**: 日志非结构化，无请求追踪 ID
- **风险**: 难以在日志聚合系统中过滤和分析
- **修复建议**: 使用 `python-json-logger` 或 `structlog`
- **修复成本**: M (1-2小时)

---

## 3. 架构与可维护性评估

### 3.1 模块边界与依赖方向

| 评估项 | 状态 | 说明 |
|-------|------|------|
| 分层架构 | ✅ 良好 | api → agent → skills → sandbox/utils，依赖方向清晰 |
| 模块职责 | ⚠️ 需改进 | Session、WorkspaceManager、routes.py 职责过重 |
| 依赖注入 | ⚠️ 需改进 | 过多全局单例 |
| 技能系统 | ✅ 良好 | Skill 基类抽象良好，统一接口 |
| 多模型路由 | ✅ 良好 | ModelResolver 设计优秀，故障降级机制完善 |

### 3.2 复杂度热点

1. `src/nini/api/routes.py` - 1098 行，需要按领域拆分
2. `src/nini/workspace/manager.py` - 800+ 行，职责过多
3. `src/nini/agent/runner.py` - 800+ 行，Agent 核心逻辑复杂
4. `src/nini/agent/session.py` - Session 类承载过多职责

### 3.3 建议的重构切分

**Quick Win (1周内)**:
- 从 `SAFE_BUILTINS` 移除 `__import__`
- 添加 LLM 调用超时配置
- CI 添加覆盖率/lint 检查
- 修复内存泄漏风险

**Mid-term (1-2月)**:
- 拆分 `routes.py` 为多个子模块
- 实现依赖注入模式
- 添加结构化日志
- 集成 Prometheus metrics

**Long-term (3月+)**:
- 重构 Session 类职责
- 实现插件化技能系统
- 完善沙箱安全机制

---

## 4. 安全与供应链评估

### 4.1 安全检查清单

| 检查项 | 状态 | 说明 |
|-------|------|------|
| 沙箱进程隔离 | ✅ | 使用 multiprocessing.spawn |
| AST 静态检查 | ⚠️ | 存在绕过向量 |
| 运行时限制 | ❌ | SAFE_BUILTINS 暴露 __import__ |
| 资源限制 | ⚠️ | Windows 无内存限制 |
| WebSocket 认证 | ⚠️ | 无认证机制 |
| 敏感信息保护 | ⚠️ | 可能泄露到日志 |
| 依赖安全 | ⚠️ | 使用 >= 版本约束 |

### 4.2 安全基线建议

1. **沙箱强化**
   - 移除 `__import__`
   - 扩展 `BANNED_CALLS`
   - 添加子模块黑名单
   - 为 Windows 实现内存限制

2. **认证授权**
   - 添加可选的 API Key 认证
   - 文档中说明安全边界

3. **日志安全**
   - 实现敏感信息脱敏
   - 限制 debug 模式在生产环境使用

---

## 5. 性能、稳定性与可观测性

### 5.1 关键性能路径

| 路径 | 风险 | 建议 |
|-----|------|------|
| Agent ReAct 循环 | Token 计数重复计算 | 增量计算或缓存 |
| LLM 调用 | 无超时控制 | 添加 timeout 参数 |
| 上下文压缩 | 失败后无兜底 | 强制裁剪作为兜底 |
| DataFrame 深拷贝 | 内存峰值 | 按需拷贝 |

### 5.2 稳定性策略

| 机制 | 状态 | 建议 |
|-----|------|------|
| 超时控制 | ⚠️ 部分 | 添加 LLM 超时 |
| 重试退避 | ❌ 无 | 为短暂失败添加指数退避 |
| 降级策略 | ✅ 良好 | ModelResolver 故障降级 |
| 资源清理 | ⚠️ 泄漏 | 修复全局字典清理 |

### 5.3 可观测性改进

| 维度 | 当前状态 | 建议 |
|-----|---------|------|
| 日志 | 非结构化 | 使用 structlog |
| Metrics | 无 | 集成 Prometheus |
| 追踪 | 无 | 添加 Request ID |
| 健康检查 | 简单 | 增强为详细检查 |

---

## 6. 测试与交付工程评估

### 6.1 测试覆盖分析

| 维度 | 覆盖率 | 缺口 |
|-----|-------|------|
| 后端单元测试 | ~50-60% | agent/runner.py, workspace/manager.py, api/routes.py |
| 后端集成测试 | 良好 | 核心流程有覆盖 |
| 前端单元测试 | 0% | 需添加组件测试 |
| 前端 E2E 测试 | 少量 | 仅 2 个测试文件 |

### 6.2 CI/CD 改进

| 检查项 | 当前 | 建议 |
|-------|------|------|
| 格式检查 (black) | ❌ | 添加到 CI |
| 类型检查 (mypy) | ❌ | 添加到 CI |
| 覆盖率检查 | ❌ | 添加 --cov-fail-under=60 |
| 前端 lint | ❌ | 添加 ESLint/Prettier |
| 自动发布 | ❌ | 添加 release.yml |

---

## 7. 文档与开发体验（DX）

### 7.1 DX 评分

| 维度 | 评分 | 说明 |
|-----|------|------|
| README 质量 | B+ | 快速开始清晰，但缺少 Python 版本要求 |
| 配置文档 | A- | 完整且清晰 |
| 代码文档 | B+ | 核心模块 docstrings 完整 |
| 示例 | B | 缺少独立示例目录 |
| **整体** | **B+** | 可在 10 分钟内完成安装启动 |

### 7.2 缺失项

1. `.env.example` 文件
2. `CONTRIBUTING.md` 贡献指南
3. `examples/` 示例目录
4. 完整的 API 请求/响应 schema

### 7.3 优点

1. `nini init` + `nini doctor` 流程顺畅
2. `CLAUDE.md` 架构文档详尽
3. 配置文档按类别分组，易于查找

---

## 8. 整改路线图

### 8.1 24 小时内（止血项）

| # | 目标 | 负责人 | 验收标准 |
|---|------|-------|---------|
| 1 | 从 SAFE_BUILTINS 移除 __import__ | 沙箱模块 | `__import__('os')` 被阻止 |
| 2 | 添加 LLM 调用超时配置 | Agent模块 | 超时后正常失败 |
| 3 | CI 添加 black --check | DevOps | CI 包含格式检查 |
| 4 | CI 添加 mypy 检查 | DevOps | CI 包含类型检查 |
| 5 | 修复 LaneQueue 内存泄漏 | Agent模块 | 会话结束时清理锁 |
| 6 | 修复 SessionTokenTracker 泄漏 | 工具模块 | 会话结束时清理 |
| 7 | 修复 AnalysisMemory 泄漏 | 记忆模块 | 会话结束时清理 |
| 8 | 添加 .env.example | 文档 | 文件存在且完整 |

### 8.2 1-2 周内（修复项）

| # | 目标 | 负责人 | 依赖 | 验收标准 |
|---|------|-------|------|---------|
| 1 | 扩展 BANNED_CALLS 列表 | 沙箱模块 | - | 反射函数被阻止 |
| 2 | 添加子模块导入限制 | 沙箱模块 | - | scipy.io 等被限制 |
| 3 | CI 添加覆盖率检查 | DevOps | - | CI 包含 --cov-fail-under=60 |
| 4 | 添加前端 ESLint/Prettier | 前端 | - | npm run lint 可执行 |
| 5 | 添加结构化日志 | 基础设施 | - | 日志为 JSON 格式 |
| 6 | 添加 Request ID | API模块 | - | 日志中包含 request_id |
| 7 | 增强 /api/health 端点 | API模块 | - | 返回详细健康状态 |
| 8 | 添加 WebSocket 保活日志 | API模块 | - | 退出原因有日志 |
| 9 | ModelResolver 添加退避机制 | Agent模块 | - | 短暂失败有重试 |
| 10 | 添加 CONTRIBUTING.md | 文档 | - | 文件存在 |
| 11 | 补充 E2E 测试用例 | 前端QA | - | 覆盖聊天流程 |

### 8.3 1-3 月（重构/体系化）

| # | 目标 | 负责人 | 依赖 | 验收标准 |
|---|------|-------|------|---------|
| 1 | 实现 Windows 内存限制 | 沙箱模块 | - | Windows 有内存限制 |
| 2 | 集成 Prometheus metrics | DevOps | - | /metrics 端点可用 |
| 3 | 重构 routes.py | API模块 | - | 文件拆分为子模块 |
| 4 | 实现依赖注入 | 架构 | - | 无全局单例 |
| 5 | 重构 Session 类 | Agent模块 | 依赖注入 | 职责拆分 |
| 6 | 添加沙箱安全测试套件 | 测试 | - | 覆盖逃逸尝试 |
| 7 | 添加 examples/ 目录 | 文档 | - | 含示例数据 |

---

## 9. 附录

### 9.1 仓库目录树（摘要）

```
scientific_nini/
├── src/nini/              # 后端核心 (72 Python files)
│   ├── agent/             # Agent 核心
│   ├── api/               # HTTP + WebSocket
│   ├── knowledge/         # RAG 检索
│   ├── memory/            # 对话压缩
│   ├── models/            # 数据模型
│   ├── sandbox/           # 代码执行器
│   ├── skills/            # 技能系统
│   ├── utils/             # 工具函数
│   ├── workflow/          # 工作流模板
│   └── workspace/         # 文件管理
├── web/                   # 前端 SPA (27 files)
│   └── src/               # React 组件
├── tests/                 # 测试套件 (36 files)
├── docs/                  # 文档
├── data/                  # 运行时数据
└── templates/             # 模板文件
```

### 9.2 发现清单原始记录（按 Agent 归档）

| Agent | 任务 | 发现数 | P1 | P2 | P3 |
|-------|------|-------|----|----|----|
| agent-arch | T1 仓库地图 | - | - | - | - |
| agent-arch | T2 架构审查 | 10 | 1 | 4 | 5 |
| agent-sec | T3 安全审查 | 9 | 1 | 3 | 5 |
| agent-sec | T6 沙箱审查 | 10 | 2 | 4 | 4 |
| agent-quality | T4 测试质量 | 8 | 3 | 3 | 2 |
| agent-docs | T5 文档DX | 7 | 1 | 3 | 3 |
| agent-perf | T5 性能审查 | 12 | 2 | 7 | 3 |
| agent-perf | T8 可观测性 | 12 | 1 | 6 | 5 |

**总计**: 78 项发现，其中 P1=11, P2=30, P3=27

### 9.3 建议补丁片段（仅供参考）

#### 修复 S01: 移除 __import__

```python
# src/nini/sandbox/executor.py
# 修改前
SAFE_BUILTINS = {
    "__import__": py_builtins.__import__,
    ...
}

# 修改后
SAFE_BUILTINS = {
    # "__import__": 已移除 - 安全漏洞
    ...
}
```

#### 修复 S03: 添加 LLM 超时

```python
# src/nini/agent/model_resolver.py
from httpx import AsyncClient, Limits

# 在 AsyncOpenAI 初始化时添加
client = AsyncOpenAI(
    api_key=api_key,
    timeout=httpx.Timeout(60.0, connect=10.0),  # 添加超时
    ...
)
```

---

**报告生成时间**: 2026-02-13
**审查团队**: Coordinator + agent-arch + agent-sec + agent-quality + agent-perf + agent-docs
