## 1. 新建风险与输出等级模型

- [x] 1.1 创建 `src/nini/models/risk.py`，定义 `RiskLevel`、`TrustLevel`、`OutputLevel` 三个 `(str, Enum)` 枚举及其元数据字典
- [x] 1.2 在 `risk.py` 中定义 `TRUST_CEILING_MAP` 常量（T1→O1/O2, T2→O3, T3→O4）
- [x] 1.3 在 `risk.py` 中定义 `MANDATORY_REVIEW_SCENARIOS` 常量（7 个强制复核场景）和 `PROHIBITED_BEHAVIORS` 常量（8 条禁止性规则）
- [x] 1.4 在 `risk.py` 中实现 `validate_output_level(trust, output) -> bool` 和 `requires_human_review(risk_level, scenario_tags) -> bool` 工具函数
- [x] 1.5 在 `src/nini/models/__init__.py` 中导出新增枚举和函数

## 2. 事件模型扩展

- [x] 2.1 在 `src/nini/models/event_schemas.py` 的 `DoneEventData` 中新增可选字段 `output_level: OutputLevel | None = None`
- [x] 2.2 在 `src/nini/models/event_schemas.py` 的 `TextEventData` 中新增可选字段 `output_level: OutputLevel | None = None`

## 3. 测试

- [x] 3.1 编写 `tests/test_risk_model.py`：测试枚举值完整性、JSON 序列化、元数据查询、trust-ceiling 映射校验、人工复核判定逻辑
- [x] 3.2 运行 `pytest -q` 确认全部测试通过且无回归
