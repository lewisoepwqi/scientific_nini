## ADDED Requirements

### Requirement: 从 YAML 文件加载同义词映射
系统 SHALL 支持从外部配置文件 `config/intent_synonyms.yaml` 加载意图同义词映射；当配置文件存在时，其内容 SHALL 完整替换（而非合并）代码内置的 `_SYNONYM_MAP`；当配置文件缺失或加载失败时，系统 SHALL 自动回退到代码内置 `_SYNONYM_MAP`，并记录 WARNING 日志，不得抛出异常。

#### Scenario: 配置文件存在时使用外部同义词
- **WHEN** `config/intent_synonyms.yaml` 文件存在且格式合法
- **THEN** `OptimizedIntentAnalyzer` 初始化时 SHALL 从该文件加载同义词映射
- **AND** 加载的映射 SHALL 优先于代码内置 `_SYNONYM_MAP` 生效

#### Scenario: 配置文件缺失时自动回退
- **WHEN** `config/intent_synonyms.yaml` 文件不存在
- **THEN** 系统 SHALL 使用代码内置 `_SYNONYM_MAP`
- **AND** SHALL 记录 DEBUG 级别日志说明使用内置配置
- **AND** SHALL 不抛出异常，意图分析功能正常可用

#### Scenario: 配置文件格式错误时回退并告警
- **WHEN** `config/intent_synonyms.yaml` 存在但 YAML 格式非法或结构不符合预期
- **THEN** 系统 SHALL 回退到代码内置 `_SYNONYM_MAP`
- **AND** SHALL 记录 WARNING 级别日志，包含文件路径和错误原因
- **AND** SHALL 不抛出异常

### Requirement: 同义词配置文件格式
`config/intent_synonyms.yaml` SHALL 采用顶层 key 为 capability 名称、value 为字符串列表的结构；列表中每个字符串为该 capability 的一个同义词表达；value 非列表类型的条目 SHALL 被忽略（不报错）。

#### Scenario: 合法配置文件格式
- **WHEN** `intent_synonyms.yaml` 内容为 `difference_analysis:\n  - "差异"\n  - "t检验"`
- **THEN** `OptimizedIntentAnalyzer` SHALL 将"差异"和"t检验"识别为 `difference_analysis` 的匹配词
- **AND** 匹配逻辑和评分权重 SHALL 与内置同义词一致

#### Scenario: 配置文件中 value 非列表类型的条目被跳过
- **WHEN** 配置文件中某 capability 的 value 为字符串或数字而非列表
- **THEN** 系统 SHALL 跳过该条目，不将其加入同义词映射
- **AND** 其余格式合法的条目 SHALL 正常加载
