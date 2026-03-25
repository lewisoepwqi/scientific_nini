## ADDED Requirements

### Requirement: 报告会话必须支持模板化导出格式

系统 SHALL 支持基于同一报告会话导出 Word、PPTX 与 LaTeX 等模板化格式，而不是仅生成单一文件。

#### Scenario: 导出 Word 报告
- **WHEN** 用户为报告会话选择 Word 模板导出
- **THEN** 系统生成对应 Word 文件
- **AND** 导出结果登记为项目产物

#### Scenario: 导出 PPTX 或 LaTeX 报告
- **WHEN** 用户为报告会话选择 PPTX 或 LaTeX 导出
- **THEN** 系统生成对应格式文件
- **AND** 保持与当前报告会话内容一致

### Requirement: 报告导出必须保留证据与 METHODS 结构

系统 SHALL 在模板化导出时保留已生成的 Evidence Block、METHODS 区块、结论验证状态和结构化资源引用，而不是在导出阶段丢失这些信息。

#### Scenario: 导出包含 Evidence Block 的报告
- **WHEN** 当前报告会话已包含 Evidence Block
- **THEN** 模板化导出结果保留这些区块或其等价表达

#### Scenario: 导出包含 METHODS 的报告
- **WHEN** 当前报告会话已包含 METHODS v1 区块
- **THEN** 模板化导出结果保留 METHODS 内容

#### Scenario: 导出保留结论验证状态
- **WHEN** 当前报告会话已区分 `verified`、`pending_verification` 或 `conflicted` 结论
- **THEN** 模板化导出结果保留这些状态标签或其等价表达
