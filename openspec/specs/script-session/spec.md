# script-session Specification

## Purpose
TBD - created by archiving change consolidate-tool-foundation. Update Purpose after archive.
## Requirements
### Requirement: 代码执行必须通过持久化脚本会话完成
系统 SHALL 提供持久化脚本会话，用于管理 Python 与 R 代码的创建、读取、执行和历史记录，而不是仅支持一次性代码字符串执行。

#### Scenario: 创建脚本会话
- **WHEN** 用户或编排层发起新的代码任务
- **THEN** 系统创建脚本资源
- **AND** 返回脚本的 `resource_id`
- **AND** 持久化脚本内容与语言类型

#### Scenario: 运行已有脚本
- **WHEN** 用户或编排层请求执行已有脚本资源
- **THEN** 系统读取该脚本资源并执行
- **AND** 将执行结果与脚本资源关联保存

#### Scenario: 创建脚本后默认自动执行
- **WHEN** 编排层创建脚本且未显式关闭自动执行
- **THEN** 系统 SHALL 在创建成功后继续执行该脚本
- **AND** SHALL 直接返回包含执行结果或失败结果的脚本会话响应

#### Scenario: 显式关闭自动执行时保留待处理状态
- **WHEN** 编排层创建脚本并显式要求不自动执行
- **THEN** 系统 SHALL 保留该脚本资源而不立即执行
- **AND** SHALL 将该脚本登记为待处理动作，供后续恢复与完成校验使用

### Requirement: 未完成脚本必须显式登记为待处理动作
系统 SHALL 对已创建但未执行成功的脚本维护显式待处理状态，而不是仅通过文本警告提示模型继续执行。

#### Scenario: 自动执行失败后登记待处理脚本
- **WHEN** 创建脚本后的自动执行失败
- **THEN** 系统 SHALL 将该脚本登记为 `script_not_run` 或等价待处理动作
- **AND** 后续运行时摘要 SHALL 能引用该脚本的待处理状态

#### Scenario: 脚本执行成功后移除待处理状态
- **WHEN** 某个待处理脚本在后续运行中执行成功
- **THEN** 系统 SHALL 清除对应的待处理脚本状态
- **AND** SHALL 保留已执行结果供后续步骤引用

### Requirement: 脚本会话必须支持局部 patch 与增量重跑
系统 SHALL 支持对脚本内容进行局部修改，并在失败后只重跑修补后的脚本，而不是要求重新生成整段代码。

#### Scenario: 按行范围修补脚本
- **WHEN** 用户或编排层提供脚本 `resource_id` 与行范围 patch
- **THEN** 系统仅替换指定范围内容
- **AND** 保留脚本其他部分不变

#### Scenario: 脚本失败后增量重跑
- **WHEN** 某脚本执行失败且后续提供了 patch
- **THEN** 系统基于更新后的脚本再次执行
- **AND** 返回新的执行结果
- **AND** 保留失败记录供审计

### Requirement: 脚本输出必须显式注册为会话资源
系统 SHALL 要求脚本会话将输出数据集和产物显式注册到会话资源目录，而不是依赖脚本自由写入路径或隐式中间状态。

#### Scenario: 脚本输出数据集
- **WHEN** 脚本声明将结果提升为数据集资源
- **THEN** 系统将输出注册为新的数据集资源
- **AND** 后续步骤可通过其 `resource_id` 引用

#### Scenario: 脚本输出图表产物
- **WHEN** 脚本生成图表并声明产物输出
- **THEN** 系统将图表写入受管产物目录
- **AND** 返回对应产物资源摘要
- **AND** 不要求脚本自己管理最终输出路径

