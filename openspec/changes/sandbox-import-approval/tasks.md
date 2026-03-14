## 1. 沙盒导入策略分层

- [x] 1.1 在 `src/nini/sandbox/policy.py` 中新增 reviewable / hard-deny 导入分层与 `SandboxReviewRequired`
- [x] 1.2 扩展 `validate_code()` 支持 `extra_allowed_imports`，并覆盖多包聚合与高风险硬拒绝分支
- [x] 1.3 为导入分层与异常行为补充单元测试，覆盖 reviewable、unknown、hard-deny 三类导入

## 2. 执行器动态授权集合

- [x] 2.1 重构 `src/nini/sandbox/executor.py`，按本次执行动态构造 `allowed_import_roots`、`safe_import` 与 builtins
- [x] 2.2 将 `extra_allowed_imports` 贯穿 `SandboxExecutor.execute()`、`_execute_sync()`、`_sandbox_worker()` 与执行环境构造链路
- [x] 2.3 补充测试，验证 AST 校验与运行期 `_safe_import()` 在授权前后保持一致

## 3. run_code 审批结果契约

- [x] 3.1 在 `src/nini/tools/code_runtime.py` 捕获 `SandboxReviewRequired` 并返回 `_sandbox_review_required` 结构化结果
- [x] 3.2 将会话级已授权包集合传入 `sandbox_executor.execute()`，并保持普通策略错误与导入失败语义不变
- [x] 3.3 补充 `tests/test_phase3_run_code.py` 或相关测试，覆盖审批需求返回与授权后重试成功场景

## 4. 会话与永久授权持久化

- [x] 4.1 在 `src/nini/agent/session.py` 与 `SessionManager` 中新增 `sandbox_approved_imports` 的加载、规范化与持久化方法
- [x] 4.2 新增 `src/nini/sandbox/approval_manager.py`，实现永久审批集合的安全读写与 reviewable 白名单校验
- [x] 4.3 补充会话恢复与永久授权加载测试，确认新会话和同会话复用行为正确

## 5. Agent 审批交互与重试

- [x] 5.1 在 `src/nini/agent/runner.py` 增加沙盒审批 payload 构造、答案解析与单次受控重试逻辑
- [x] 5.2 复用现有 `ask_user_question` 事件流记录审批过程，并支持 `allow_once`、`allow_session`、`always_allow`、`deny`
- [x] 5.3 补充测试，验证拒绝授权、重复审批保护与错误回退行为

## 6. WebSocket 事件流与回归验证

- [x] 6.1 校验 `src/nini/api/websocket.py` 对审批问答链路的兼容性，必要时补充与原始 `tool_call_id` 绑定的细节
- [x] 6.2 补充 `tests/test_phase4_websocket_ask_user_question.py`，覆盖沙盒审批触发的事件流与恢复执行
- [ ] 6.3 运行回归验证：`pytest -q`、重点沙盒/事件流测试与 `cd web && npm run build`
