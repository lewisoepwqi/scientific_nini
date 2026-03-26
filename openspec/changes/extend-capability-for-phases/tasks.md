## 1. 新增 ResearchPhase 枚举

- [ ] 1.1 在 `src/nini/models/risk.py` 中新增 `ResearchPhase(str, Enum)` 枚举，包含八大研究阶段
- [ ] 1.2 在 `src/nini/models/__init__.py` 中导出 `ResearchPhase`

## 2. 扩展 Capability 数据类

- [ ] 2.1 在 `src/nini/capabilities/base.py` 的 `Capability` dataclass 中新增 `phase`、`risk_level`、`max_output_level` 三个可选字段
- [ ] 2.2 更新 `to_dict()` 方法，包含新增字段

## 3. 标注现有 Capability

- [ ] 3.1 在 `src/nini/capabilities/defaults.py` 中为全部 11 个 Capability 实例标注 phase、risk_level、max_output_level 属性

## 4. 测试与验证

- [ ] 4.1 编写测试：验证 ResearchPhase 枚举完整性、Capability 新字段默认值、to_dict 输出、现有 Capability 标注正确性
- [ ] 4.2 运行 `pytest -q` 确认全部测试通过且无回归
