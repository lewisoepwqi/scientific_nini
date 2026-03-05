# Phase 1 QA 验收检查清单

**文档目的**: 为 Nini Agent 改进方案提供标准化的质量审查框架

**审查者**: QA Reviewer (Claude)

---

## 1. 现有测试结构概览

### 1.1 测试文件分类

| 类别 | 测试文件 | 覆盖范围 |
|------|----------|----------|
| **沙箱安全** | `test_phase3_run_code.py` | run_code 技能、导入白名单、危险函数拦截 |
| | `test_sandbox_executor_observability.py` | 图表配置日志、资源限制、序列化错误处理 |
| | `test_sandbox_import_fix.py` | 合法模块导入验证、pandas/numpy 集成 |
| **R 代码执行** | `test_r_policy.py` | R 包白名单、危险函数拦截、注释忽略 |
| | `test_r_executor.py` | R 标量结果、DataFrame 持久化、策略违规拦截 |
| **Prompt 安全** | `test_prompt_guardrails.py` | 系统提示词结构、注入防护、上下文过滤 |
| **核心技能** | `test_phase2_skills.py`, `test_phase6_skills.py` | 基础技能执行 |
| **会话管理** | `test_phase4_session_persistence.py` | 会话持久化 |
| **WebSocket** | `test_phase4_websocket_run_code.py` | WebSocket 实时执行 |
| **模型路由** | `test_phase5_model_resolver.py` | 多模型路由与降级 |
| **CLI** | `test_phase7_cli.py` | 命令行接口 |
| **图表渲染** | `test_chart_fonts.py`, `test_chart_style_consistency.py` | 图表字体、风格一致性 |
| **统计分析** | `test_multiple_comparison.py`, `test_interpretation.py` | 统计方法、结果解读 |
| **数据质量** | `test_data_quality.py`, `test_clean_data.py` | 数据清洗、质量诊断 |
| **工作区** | `test_workspace_panel.py`, `test_workspace_persistence.py` | 文件管理、持久化 |

### 1.2 测试运行配置

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**运行命令**:
```bash
# 全量测试
pytest -q

# 单文件测试
pytest tests/test_phase3_run_code.py -q

# 单个测试
pytest tests/test_phase3_run_code.py::test_run_code_blocks_disallowed_import -q

# 带覆盖率
pytest -q --cov=src/nini --cov-report=html
```

---

## 2. 三重沙箱安全机制审查

### 2.1 第一重：AST 静态分析 (`sandbox/policy.py`)

**白名单模块** (共 28 个):
- **Tier 1 (纯计算)**: `math`, `statistics`, `random`, `decimal`, `fractions`, `cmath`
- **Tier 2 (标准库)**: `datetime`, `time`, `collections`, `itertools`, `functools`, `json`, `csv`, `re` 等
- **Tier 3 (科学计算)**: `pandas`, `numpy`, `scipy`, `statsmodels`, `sklearn`, `matplotlib`, `plotly`, `seaborn`

**禁止函数调用**:
```python
BANNED_CALLS = {
    "__import__", "eval", "exec", "compile",
    "open", "input", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir", "type", "breakpoint"
}
```

**审查要点**:
- [ ] 白名单模块是否满足分析需求
- [ ] 是否存在绕过 AST 分析的可能
- [ ] 相对导入是否被完全禁止

### 2.2 第二重：受限 builtins (`sandbox/executor.py`)

**SAFE_BUILTINS 设计**:
- 保留安全内建函数：`abs`, `len`, `print`, `range`, `sum`, `isinstance` 等
- 移除危险函数：`open`, `input`, `eval`, `exec`, `__import__`
- 提供 `_safe_import()` 白名单版本

**审查要点**:
- [ ] builtins 移除是否完整
- [ ] `_safe_import()` 是否严格检查白名单
- [ ] 全局命名空间注入是否安全

### 2.3 第三重：进程隔离 (`sandbox/executor.py`)

**隔离机制**:
- `multiprocessing` spawn 模式创建子进程
- 资源限制：CPU 时间 (`RLIMIT_CPU`)、虚拟内存 (`RLIMIT_AS`)
- 超时终止：默认超时后强制 terminate

**审查要点**:
- [ ] 子进程是否完全隔离于主进程
- [ ] 资源限制是否在 Windows/Linux/macOS 均生效
- [ ] 超时处理是否无内存泄漏

### 2.4 R 代码沙箱 (`sandbox/r_policy.py`, `sandbox/r_executor.py`)

**R 包白名单** (共 47 个):
- Base: `base`, `utils`, `stats`, `graphics`, `methods`
- 数据处理：`dplyr`, `tidyr`, `data.table`, `readr`
- 可视化：`ggplot2`, `plotly`, `patchwork`
- 统计建模：`lme4`, `survival`, `forecast`, `MASS`
- 生物信息：`DESeq2`, `edgeR`, `limma`, `clusterProfiler`

**禁止调用**:
```r
BANNED_R_CALLS = {
    "system", "system2", "shell", "file.remove",
    "download.file", "eval", "parse", "source", ...
}
```

**审查要点**:
- [ ] R 包白名单是否满足生信分析需求
- [ ] 系统调用是否被完全禁止
- [ ] 自动安装机制是否安全

---

## 3. QA 验收检查清单模板

### 3.1 代码安全审查

| 检查项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| Python 导入白名单 | 尝试导入 `os`, `sys`, `subprocess` | 抛出 `SandboxPolicyError` | ☐ |
| Python 危险函数 | 尝试调用 `eval()`, `exec()` | 抛出 `SandboxPolicyError` | ☐ |
| R 包白名单 | 尝试加载 `devtools`, `inline` | 抛出 `RSandboxPolicyError` | ☐ |
| R 系统调用 | 尝试调用 `system()`, `shell()` | 抛出 `RSandboxPolicyError` | ☐ |
| 进程隔离 | 检查执行环境独立性 | 子进程无法访问父进程内存 | ☐ |
| 资源限制 | 执行大内存代码 | 触发内存限制或超时 | ☐ |
| 超时机制 | 执行死循环代码 | 在设定时间内终止 | ☐ |

### 3.2 功能正确性审查

| 检查项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| 标量计算 | `result = 1 + 2` | 返回 `{"success": true, "result": 3}` | ☐ |
| DataFrame 操作 | 对 `df` 进行转换 | 正确修改或返回新 DataFrame | ☐ |
| 图表生成 | Matplotlib/Plotly 绘图 | 检测到图表并序列化 | ☐ |
| 图表风格 | 默认样式应用 | 中文字体、科研风格正确 | ☐ |
| 结果持久化 | `persist_df=True` | 数据集被正确更新 | ☐ |
| 输出保存 | `save_as="normalized.csv"` | 新数据集被创建 | ☐ |

### 3.3 错误处理审查

| 检查项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| 语法错误 | 发送无效 Python 语法 | 返回友好错误信息 | ☐ |
| 运行时错误 | 除零、类型错误 | 返回 traceback 和错误原因 | ☐ |
| 超时错误 | 执行 `while True: pass` | 返回超时错误，非 hangs | ☐ |
| 内存超限 | 创建超大数组 | 返回内存不足错误 | ☐ |
| 缺失 R 包 | 使用未安装 R 包 | 提示安装或返回错误 | ☐ |
| R 执行超时 | R 代码死循环 | 在设定时间内终止 | ☐ |

### 3.4 兼容性审查

| 检查项 | 验证平台 | 预期结果 | 状态 |
|--------|----------|----------|------|
| Python 沙箱 | Windows 11 | 正常执行 | ☐ |
| Python 沙箱 | Linux (CI) | 正常执行 | ☐ |
| R 沙箱 | 已安装 R 环境 | 正常执行 | ☐ |
| R 沙箱 | 未安装 R 环境 | 友好提示 | ☐ |
| 资源限制 | Linux (有 resource) | 应用限制 | ☐ |
| 资源限制 | Windows (无 resource) | 降级为仅超时 | ☐ |

### 3.5 回归测试审查

| 检查项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| 现有测试全通过 | `pytest -q` | 100% 通过 | ☐ |
| 沙箱测试覆盖 | `test_phase3_*.py` | 覆盖全部场景 | ☐ |
| R 测试覆盖 | `test_r_*.py` | 覆盖全部场景 | ☐ |
| Prompt 安全测试 | `test_prompt_guardrails.py` | 注入防护有效 | ☐ |

### 3.6 CI/CD 审查

| 检查项 | 验证方法 | 预期结果 | 状态 |
|--------|----------|----------|------|
| GitHub Actions | 推送 PR 触发 | 自动运行测试 | ☐ |
| 后端测试 | `ubuntu-latest + Python 3.12` | pytest 通过 | ☐ |
| 前端构建 | `ubuntu-latest + Node 20` | Vite 构建成功 | ☐ |
| 缓存配置 | pip + npm 缓存 | 加速依赖安装 | ☐ |

---

## 4. 回归测试流程

### 4.1 本地回归测试

```bash
# 1. 代码格式化检查
black --check src tests

# 2. 类型检查
mypy src/nini

# 3. 全量测试
pytest -q

# 4. 沙箱专项测试
pytest tests/test_phase3_run_code.py tests/test_sandbox_*.py -v

# 5. R 代码专项测试 (如已安装 R)
pytest tests/test_r_*.py -v

# 6. Prompt 安全测试
pytest tests/test_prompt_guardrails.py -v
```

### 4.2 CI 回归测试

GitHub Actions 自动执行:
1. 检出代码
2. 安装 Python 3.12 + 依赖
3. 运行 `pytest -q`
4. 前端构建验证

### 4.3 验收测试流程

```
1. 审查变更范围 → 确定影响的测试文件
2. 运行相关测试 → 验证功能正确性
3. 运行全量测试 → 确保无回归
4. 安全专项测试 → 验证沙箱安全性
5. 手动探索测试 → 边界场景验证
6. 输出审查报告 → 记录问题和风险
```

---

## 5. 风险评估与缓解

### 5.1 已知风险

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| 白名单模块不足 | 用户无法使用特定库 | 中 | 通过 `ALLOWED_IMPORT_ROOTS` 扩展 |
| 资源限制误杀 | 正常大计算被终止 | 低 | 调整 `sandbox_max_memory_mb` 配置 |
| R 包安装失败 | 依赖网络或镜像 | 中 | 配置 CRAN 镜像，支持离线预装 |
| Windows 资源限制失效 | 内存/CPU 无限制 | 中 | 依赖超时机制兜底 |

### 5.2 安全边界

**已防护**:
- ✅ 直接系统调用 (`os`, `subprocess`, `ctypes`)
- ✅ 动态代码执行 (`eval`, `exec`, `__import__`)
- ✅ 文件系统访问 (`open`, `pathlib`, `shutil`)
- ✅ 网络访问 (`socket`, `urllib`, `requests`)
- ✅ 进程注入 (`ptrace`, `gdb` 等)

**潜在绕过路径** (需持续监控):
- ⚠️ 通过已白名单库的间接系统访问 (如 `pandas.read_csv` 读任意文件)
- ⚠️ 通过 `matplotlib` 保存文件到磁盘
- ⚠️ 通过 `pickle` 反序列化执行任意代码

**缓解建议**:
1. 定期审计白名单模块的 API 文档
2. 考虑引入文件系统沙箱 (临时目录隔离)
3. 限制 `to_csv()`, `to_pickle()` 等写操作

---

## 6. 验收签字

**审查完成日期**: _______________

**审查者**: QA Reviewer

**验收结论**:
- [ ] 通过，无阻塞问题
- [ ] 有条件通过，需修复非阻塞问题
- [ ] 不通过，存在阻塞安全问题

**遗留问题清单**:
1. ...
2. ...

**建议改进项**:
1. ...
2. ...
