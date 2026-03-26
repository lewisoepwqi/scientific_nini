## ADDED Requirements

### Requirement: 输出等级枚举定义
系统 SHALL 定义 `OutputLevel` 枚举，包含四个等级：O1（建议级）、O2（草稿级）、O3（可审阅级）、O4（可导出级），每个等级附带名称、定义和用户预期描述。

#### Scenario: 枚举值完整
- **WHEN** 导入 `OutputLevel` 枚举
- **THEN** 枚举包含 `o1`、`o2`、`o3`、`o4` 四个值

#### Scenario: 枚举可序列化为字符串
- **WHEN** 将 `OutputLevel.o3` 序列化为 JSON
- **THEN** 输出为字符串 `"o3"`

#### Scenario: 元数据可查询
- **WHEN** 查询 `OutputLevel.o2` 的元数据
- **THEN** 返回包含名称（「草稿级」）、定义（「可编辑初稿，结构较完整」）和用户预期（「需要用户修改和补充」）的字典

### Requirement: trust-ceiling 映射
系统 SHALL 定义 `TRUST_CEILING_MAP` 常量，建立 TrustLevel 到允许的最高 OutputLevel 的映射关系：T1 → O1/O2, T2 → O3, T3 → O4。

#### Scenario: T1 信任等级的输出上限
- **WHEN** 查询 T1 信任等级允许的输出等级
- **THEN** 仅允许 O1 和 O2

#### Scenario: T2 信任等级的输出上限
- **WHEN** 查询 T2 信任等级允许的输出等级
- **THEN** 允许 O1、O2 和 O3

#### Scenario: T3 信任等级的输出上限
- **WHEN** 查询 T3 信任等级允许的输出等级
- **THEN** 允许 O1、O2、O3 和 O4

### Requirement: 输出等级校验函数
系统 SHALL 提供 `validate_output_level(trust, output)` 函数，校验指定输出等级是否在信任等级的 ceiling 范围内。

#### Scenario: 合法组合校验通过
- **WHEN** 调用 `validate_output_level(TrustLevel.t2, OutputLevel.o3)`
- **THEN** 返回 `True`

#### Scenario: 非法组合校验失败
- **WHEN** 调用 `validate_output_level(TrustLevel.t1, OutputLevel.o4)`
- **THEN** 返回 `False`

### Requirement: DoneEventData 输出等级标注
`DoneEventData` SHALL 新增可选字段 `output_level: OutputLevel | None`，默认为 None，用于标注整轮回复的综合输出等级。

#### Scenario: 字段存在且可选
- **WHEN** 创建 `DoneEventData` 不传 output_level
- **THEN** 实例的 output_level 为 None

#### Scenario: 字段可赋值
- **WHEN** 创建 `DoneEventData(output_level=OutputLevel.o2, ...)`
- **THEN** 实例的 output_level 为 `OutputLevel.o2`

#### Scenario: 序列化向后兼容
- **WHEN** 将含 output_level 的 DoneEventData 序列化为 JSON
- **THEN** JSON 中包含 `"output_level": "o2"` 字段；旧版前端忽略未知字段不报错

### Requirement: TextEventData 输出等级标注
`TextEventData` SHALL 新增可选字段 `output_level: OutputLevel | None`，默认为 None，用于分片级输出标注（初期不启用，预留扩展）。

#### Scenario: 字段存在且默认为 None
- **WHEN** 创建 `TextEventData` 不传 output_level
- **THEN** 实例的 output_level 为 None
