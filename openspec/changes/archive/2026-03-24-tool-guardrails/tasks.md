## 1. 核心框架实现

- [x] 1.1 新建 `src/nini/tools/guardrails.py`，定义 `GuardrailDecision` 数据类（decision 枚举 + reason 字符串）
- [x] 1.2 定义 `ALLOW`、`BLOCK`、`REQUIRE_CONFIRMATION` 三种枚举值
- [x] 1.3 定义 `ToolGuardrail` 抽象基类，方法签名：`evaluate(tool_name: str, kwargs: dict) -> GuardrailDecision`

## 2. 规则实现

- [x] 2.1 实现 `DangerousPatternGuardrail`，检测并 BLOCK 以下模式：
  - `clean_data` + `inplace=True` + dataset 名含 `_raw`/`_original`/`original`
  - `organize_workspace` + `delete_all=True` 或 `pattern="*"`
  - 任意工具参数中包含系统路径（`/etc/`、`/sys/`、`~/.ssh/`）

## 3. Registry 集成

- [x] 3.1 在 `src/nini/tools/registry.py` 的 `ToolRegistry.__init__` 中初始化 guardrail 链，默认包含 `DangerousPatternGuardrail`
- [x] 3.2 添加 `ToolRegistry.add_guardrail(guardrail: ToolGuardrail)` 方法
- [x] 3.3 修改 `ToolRegistry.execute()`：调用 Tool.execute() 前遍历 guardrail 链，遇到非 ALLOW 决策立即返回失败 dict（含拦截原因），并写 warning 日志

## 4. 测试

- [x] 4.1 新建 `tests/test_guardrails.py`
- [x] 4.2 测试 `DangerousPatternGuardrail`：clean_data + inplace=True + raw dataset → BLOCK
- [x] 4.3 测试 `DangerousPatternGuardrail`：clean_data + inplace=False → ALLOW
- [x] 4.4 测试 `DangerousPatternGuardrail`：organize_workspace + delete_all=True → BLOCK
- [x] 4.5 测试 `DangerousPatternGuardrail`：参数含 /etc/ 路径 → BLOCK
- [x] 4.6 测试 registry 集成：BLOCK 时 `execute()` 返回 success=False dict，不调用 Tool.execute()
- [x] 4.7 测试 registry 集成：ALLOW 时 `execute()` 正常调用 Tool.execute()
- [x] 4.8 运行 `pytest tests/test_guardrails.py -q` 全部通过

## 5. 验收

- [x] 5.1 运行 `pytest -q` 确认全量测试无回归
- [x] 5.2 运行 `black --check src/nini/tools/guardrails.py tests/test_guardrails.py`
- [x] 5.3 运行 `mypy src/nini/tools/guardrails.py` 无类型错误
