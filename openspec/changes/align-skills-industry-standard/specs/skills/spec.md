## MODIFIED Requirements

### Requirement: 混合技能发现机制
系统 SHALL 同时支持 Function Skill 与 Markdown Skill 的发现与聚合，形成统一技能视图供 Agent 与前端使用；Markdown Skill 的发现流程必须支持渐进式披露，不得在扫描阶段读取附属资源正文。

#### Scenario: 启动时扫描技能目录
- **WHEN** 服务启动或触发技能刷新
- **THEN** 系统扫描约定目录下的 `SKILL.md` 并解析技能元信息
- **AND** 与已注册 Function Skill 合并为统一技能清单
- **AND** 不读取 `references/`、`scripts/`、`assets/` 等附属资源的正文内容

#### Scenario: 技能定义异常时降级处理
- **WHEN** 某个 `SKILL.md` 缺失必要字段或解析失败
- **THEN** 系统记录告警并跳过该技能
- **AND** 不影响其他技能加载

### Requirement: Markdown 技能调用协议
系统 SHALL 对 Markdown Skill 执行“先读定义再执行”的协议约束，并将其扩展为四层渐进式披露：索引层、说明层、资源清单层、引用内容层。

#### Scenario: 正常执行 Markdown 技能
- **WHEN** Agent 决定使用某个 Markdown Skill
- **THEN** 首先读取该技能定义文件内容
- **AND** 按定义步骤调用受控工具完成任务

#### Scenario: 缺少定义文件时拒绝执行
- **WHEN** 目标 Markdown Skill 的定义文件不可读或不存在
- **THEN** 系统拒绝执行该技能并返回错误说明

#### Scenario: 引用内容按需展开
- **WHEN** 技能正文明确引用 `references/guide.md` 等单个资源文件
- **THEN** 系统仅按需读取被引用的单个文件内容
- **AND** 未被引用的其他资源文件不得进入模型上下文

#### Scenario: 资源目录只提供清单不自动展开正文
- **WHEN** 客户端或 Agent 获取 Markdown Skill 的运行时资源
- **THEN** 系统返回目录树、相对路径、类型和大小等元数据
- **AND** 不自动返回资源文件正文

### Requirement: 统一技能查询接口
系统 SHALL 提供统一技能查询 API，返回 Function/Markdown 双类型技能的可见状态与元数据；默认不得暴露服务端绝对路径。

#### Scenario: 获取技能列表
- **WHEN** 客户端调用技能列表接口
- **THEN** 返回技能数组，至少包含 `name`、`description`、`type`、`location`、`enabled`
- **AND** `location` 为相对 skill 根目录路径、逻辑标识或其他非绝对路径表示

#### Scenario: 按类型过滤技能
- **WHEN** 客户端请求按技能类型过滤（例如仅 `markdown`）
- **THEN** 接口返回匹配类型的技能子集

#### Scenario: 运行时资源接口不暴露绝对根路径
- **WHEN** 客户端调用 Markdown Skill 的运行时资源或文件树接口
- **THEN** 系统返回 skill 相对路径、逻辑根标识或其他非绝对路径表示
- **AND** 不返回服务端绝对文件系统根路径

### Requirement: 技能目录必须区分基础工具与内部编排
系统 SHALL 在技能目录与查询接口中明确区分“模型可见基础工具”和“内部编排能力”，并让 Markdown Skill 的 `allowed-tools` 成为执行期约束的一部分，而不是仅供提示。

#### Scenario: 查询技能目录
- **WHEN** 客户端或 Agent 请求技能清单
- **THEN** 每个条目包含其层级信息
- **AND** 能区分基础工具、内部编排与 Markdown 技能

#### Scenario: 构建模型上下文
- **WHEN** Agent 构建模型可见工具上下文
- **THEN** 仅注入基础工具层
- **AND** 内部编排能力仅作为运行时实现细节保留

#### Scenario: 激活技能后限制工具调用
- **WHEN** 当前回合激活的 Markdown Skill 声明了 `allowed-tools`
- **THEN** 后续工具调用必须属于该白名单
- **AND** 调用白名单外工具时系统必须阻断执行并返回清晰错误

#### Scenario: 白名单只约束模型发起的工具调用
- **WHEN** 系统执行当前回合的框架级恢复、兼容、审计或其他非模型发起动作
- **THEN** `allowed-tools` 白名单不应阻断这些内部动作
- **AND** 白名单仅用于约束激活技能后由模型直接发起的工具调用

#### Scenario: 未声明白名单时保持默认工具行为
- **WHEN** 当前回合激活的 Markdown Skill 未声明 `allowed-tools`
- **THEN** 系统不收缩默认基础工具集合
- **AND** 不得因为缺省值而产生误阻断

## ADDED Requirements

### Requirement: Markdown Skill 引用资源必须受控解析
系统 SHALL 只允许在 Skill 根目录内解析和读取被显式引用的资源路径，禁止路径穿越、绝对路径和整目录正文展开。

#### Scenario: 拒绝绝对路径
- **WHEN** Skill 正文或运行时请求引用绝对路径
- **THEN** 系统拒绝读取该路径
- **AND** 返回结构化错误说明

#### Scenario: 拒绝路径穿越
- **WHEN** Skill 正文或运行时请求引用包含 `..` 的路径
- **THEN** 系统拒绝读取该路径
- **AND** 不读取 Skill 根目录外部文件

#### Scenario: 引用文件缺失时失败可解释
- **WHEN** Skill 正文引用的相对路径文件不存在
- **THEN** 系统返回明确的“引用资源不存在”错误
- **AND** 不静默回退到猜测性执行

#### Scenario: 未引用资源不得发生正文读取
- **WHEN** 当前回合仅引用了部分 Skill 资源文件
- **THEN** 系统只允许读取被引用文件的正文内容
- **AND** 其他未被引用资源最多只能以目录元数据形式出现

### Requirement: 技能快照必须区分受信摘要与可编辑原文
系统 SHALL 继续生成技能快照用于审计和可见性，但快照进入 trusted prompt 时只能使用系统生成摘要，不得把可编辑 Markdown Skill 原文直接带入 trusted boundary。

#### Scenario: 快照文件用于审计与调试
- **WHEN** 技能列表发生变化（新增、删除、更新）
- **THEN** 系统刷新技能快照文件
- **AND** 快照可继续作为 operator 或审计工件保留

#### Scenario: Trusted prompt 只使用系统生成摘要
- **WHEN** Agent 构建 trusted system prompt
- **THEN** 可以使用基于技能目录生成的系统摘要
- **AND** 不得直接注入 Markdown Skill 的原始 `description`、frontmatter 或正文摘录

### Requirement: Markdown Skill 元数据与执行语义必须一致
系统 SHALL 让语义目录、技能详情接口和运行时执行路径使用一致的 `user-invocable`、`disable-model-invocation`、`allowed-tools` 等字段语义。

#### Scenario: 显式技能尊重 user-invocable
- **WHEN** 用户通过 `/skill` 显式调用 `user-invocable=false` 的 Markdown Skill
- **THEN** 系统拒绝激活该技能
- **AND** 返回清晰错误说明

#### Scenario: 自动匹配尊重 disable-model-invocation
- **WHEN** 技能声明 `disable-model-invocation=true`
- **THEN** 自动语义匹配流程不得激活该技能
- **AND** 该技能仍可作为索引项出现在管理或审计接口中
