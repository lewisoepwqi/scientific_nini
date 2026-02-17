# 代码审查报告（2026-02-17）

## 审查范围
- 后端核心：`src/nini/`（CLI、配置、沙箱执行与策略）。
- 前端构建：`web/`（Vite 打包结果与体积风险）。
- 工程质量：格式检查、类型检查、测试收集与构建链路。

## 执行检查
1. `black --check src tests`
   - 结果：失败，存在 3 个文件未符合格式规范。
2. `mypy src/nini`
   - 结果：失败，出现大量 `import-not-found` 与少量真实类型问题（如 `no-any-return`、`no-redef`）。
3. `pytest -q`
   - 结果：失败，测试在收集阶段被依赖缺失阻塞（`pandas/numpy/plotly` 等未安装）。
4. `cd web && npm run build`
   - 结果：通过，但输出告警显示超大 chunk（`plotly` 包约 4.7MB）。

## 关键发现（按优先级）

### P1：沙箱内存上限在默认配置下形同虚设
- 现象：`_set_resource_limits()` 仅在 `max_memory_mb >= 1024` 时才设置 `RLIMIT_AS`。
- 风险：默认配置为 `sandbox_max_memory_mb = 512`，意味着默认路径不会施加地址空间限制，无法有效约束内存膨胀。
- 证据：
  - 默认内存配置为 512MB：`src/nini/config.py`。
  - 限制条件写死为 `>=1024`：`src/nini/sandbox/executor.py`。
- 建议：
  1. 将条件从 `>=1024` 调整为 `>0`，并保留动态缓冲策略。
  2. 如果担心误杀，可使用 `max(requested_limit, runtime_usage + buffer)` 而非直接禁用低配限制。

### P1：沙箱图表采集存在大面积“吞错”
- 现象：`_collect_figures()` 多处 `except Exception: pass`，且未记录日志。
- 风险：生产环境中图表丢失、导出异常、对象序列化失败时无法定位根因，影响可观测性与问题恢复。
- 证据：`src/nini/sandbox/executor.py` 的 Plotly/Matplotlib 采集分支与 `gcf` 补采分支均为静默失败。
- 建议：
  1. 至少在 debug 级别记录异常类型与变量名。
  2. 对高频失败场景（如 `to_json/savefig`）增加错误计数，暴露到诊断接口。

### P2：类型检查配置与仓库现状不一致
- 现象：虽然 `pyproject.toml` 中对部分第三方模块配置了 `ignore_missing_imports`，并关闭了 `import-untyped`，但 `mypy` 仍出现大规模 `import-not-found`。
- 风险：CI/本地类型检查噪声过高，真实类型问题被淹没，降低规则可信度。
- 证据：`mypy src/nini` 输出中出现 49 个错误，覆盖 FastAPI、NumPy、Pydantic、Uvicorn 等核心依赖。
- 建议：
  1. 明确团队策略：在 dev 环境强制安装完整依赖 + stubs，或在 mypy 配置中按模块分层降噪。
  2. 将“环境缺依赖导致的 import-not-found”与“真实类型错误”分离统计。

### P2：测试体系对环境依赖较重，最小可运行基线不清晰
- 现象：`pytest -q` 在 collection 阶段即因依赖缺失中断，且出现 `asyncio_mode` 未识别、`@pytest.mark.asyncio` 未注册警告。
- 风险：新贡献者难以快速获得“可通过的最小检查集”；回归门槛依赖隐式环境。
- 建议：
  1. 在 `README` 或 `docs/development.md` 显式给出“审查/CI 最小依赖安装命令”。
  2. 增加一个 smoke test 集（无重型科学栈）用于快速健康检查。

### P3：前端构建体积偏大，首屏性能存在隐患
- 现象：生产构建中 `plotly` chunk 约 4.7MB（gzip 后约 1.4MB），Vite 触发 chunk 体积告警。
- 风险：弱网或低性能设备下加载变慢，影响图表相关页面交互体验。
- 证据：`npm run build` 输出体积告警。
- 建议：
  1. 将图表能力继续按路由/功能懒加载。
  2. 评估轻量图表替代、按需引入 Plotly 子模块或服务端导出。

## 正向观察
- CLI 子命令结构清晰，`start/init/doctor/tools/skills/export-memory` 分层较好，具备较完整可用性。
- 沙箱策略采用 AST 校验 + 受限 builtins + 子进程隔离的多层防护思路，安全基线设计合理。
- 前端已做 `plotly/markdown` 手动分包，说明性能优化已有方向。

## 建议落地顺序
1. **先修复 P1（沙箱内存限制 + 图表吞错）**，提升稳定性与可观测性。
2. **再清理工程质量噪声（mypy/pytest 环境一致性）**，恢复 CI 信号价值。
3. **最后推进前端体积优化**，在不影响功能的前提下逐步演进。

## 回滚说明
- 本次仅新增审查文档，不涉及运行时代码。
- 如需回滚，删除该文档即可，无业务风险。
