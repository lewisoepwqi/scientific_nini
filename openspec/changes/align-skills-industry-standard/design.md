## 背景

当前实现已经把 Skills 拆成扫描器、注册表、语义目录、说明层读取、资源清单读取、运行时上下文注入等多个环节，但它们之间缺少完整的架构闭环：

1. 扫描层只抽元数据，但这些元数据会被错误提升为 trusted prompt 内容
2. 激活层能读取 `SKILL.md`，但不会继续按引用读取真正的资源文件
3. 执行层会收集 `allowed-tools`，但不会把它落实成执行约束
4. 上下文层会注入整段 skill 正文，但没有为 Skill 本身建立独立预算和裁剪顺序

这使当前系统更像“半完成的分层披露接口”，而不是“可稳定运行的 industry-standard skill package runtime”。

## 目标架构

本提案将 Skills 约束为两个边界、四层披露。

### 一、两条边界

#### 1. Trusted boundary

只允许以下内容进入 trusted system prompt：

- 固定 prompt components
- 系统生成的技能摘要
- 项目级 `AGENTS.md`

不得进入 trusted boundary 的内容：

- Markdown Skill 正文
- Skill frontmatter 可编辑原文
- 运行时引用资源正文
- 用户数据、知识片段、记忆、工具结果

#### 2. Untrusted runtime boundary

以下内容统一走 canonical runtime context builder：

- Markdown Skill 正文摘要
- Markdown Skill 引用资源内容
- 数据集元信息
- 检索知识
- 记忆和研究画像

所有这些内容必须统一打上 untrusted header，并经过同一套清洗和预算控制。

### 二、四层渐进式披露

#### 1. 索引层

用途：

- 列表页
- 语义目录
- 技能匹配

特征：

- 只读轻量元数据
- 不读取资源正文
- 不读取 `SKILL.md` 正文主体之外的附属文件

#### 2. 说明层

用途：

- 显式 `/skill`
- 自动匹配后确认采用某技能

特征：

- 读取 `SKILL.md` 正文
- 生成可注入的说明摘要
- 不自动读取全部资源文件

#### 3. 资源清单层

用途：

- UI 文件树
- 运行时资源预览
- 后续引用解析

特征：

- 仅列出目录树、相对路径、类型、大小等元数据
- 不读取文件正文

#### 4. 引用内容层

用途：

- 技能正文明确引用资源
- 运行时必须读取该引用内容才能稳定执行

特征：

- 只按引用读取目标文件
- 只允许 skill 根目录内相对路径
- 不允许整目录展开
- 不允许未被引用的资源进入模型上下文
- 不允许未被引用的资源发生正文读取

## 关键设计决策

### 1. `SKILLS_SNAPSHOT` 的角色收缩

`SKILLS_SNAPSHOT` 继续保留，但角色改为：

- operator/debug artifact
- trusted 技能摘要来源

它不再承载用户可编辑原文，不再成为 Markdown Skill 正文进入 system prompt 的桥梁。

### 2. `AGENTS.md` trusted 化

项目级 `AGENTS.md` 与主流 Coding Agent 行为对齐，作为仓库约束进入 trusted assembly。

这样做的理由：

- 它本质上是仓库策略，不是运行时资料
- 当前系统已经把它和 runtime context 混放，导致优先级错误
- 如果继续当 untrusted 参考，会让“仓库级规则”失去约束力

层级与合并规则也需要固定：

- 根目录 `AGENTS.md` 为仓库级最高优先级约束
- 子目录 `AGENTS.md` 仅在对应作用域内补充更窄约束
- 子目录规则不得削弱或覆盖根目录 trusted 约束
- 当前“根目录与一级子目录统一拼接”的实现应被替换为可预测的优先级合并

### 3. `allowed-tools` 采用硬约束

激活 Skill 后，允许调用的工具集合由 Skill 白名单决定。

做硬约束而不是软提示的原因：

- 只有硬约束才能形成稳定技能包契约
- 只有硬约束才能让 Skill 的 review、审计和兼容性判断有意义
- 软提示会继续放大模型自由裁量，无法消除当前不稳定性

适用边界也需要锁定：

- 仅约束当前回合中由模型直接发起的工具调用
- 不约束系统内部非模型触发的维护、恢复、审计或兼容动作

### 4. Skill 独立预算

预算顺序需要显式化：

1. 先裁剪引用资源内容
2. 再裁剪 skill 正文摘要
3. 再裁剪其他低优先级 runtime context
4. 最后才裁剪历史消息

原因：

- Skill 是运行时辅助资料，不应无上限挤占对话历史
- 当前只裁剪 history，会导致“参考资料比真实上下文更稳定”，这是错误优先级

## 路径与安全策略

### 允许的路径

- Skill 根目录下的相对路径
- 由 `SKILL.md` 正文直接引用的路径
- 由系统显式请求的单文件路径

### 禁止的路径

- 绝对路径
- `..` 路径穿越
- Skill 根目录外部路径
- 一次性整目录内容展开

### 路径呈现

对模型和 API 默认返回：

- skill 内相对路径
- 或逻辑标识符

不返回服务端绝对路径。

## 兼容性

以下接口保留：

- `/api/skills/semantic-catalog`
- `/api/skills/markdown/{name}/instruction`
- `/api/skills/markdown/{name}/runtime-resources`
- `/api/skills/markdown/{name}/files`

兼容方式：

- `instruction` 继续返回正文层
- `runtime-resources` 继续返回资源清单层
- `files` 继续返回文件树，但默认使用 skill 相对路径与非绝对根标识
- 新增或调整的引用内容读取能力应建立在现有三层之上，而不是破坏原接口

## 风险与缓解

### 风险 1：硬约束白名单会暴露现有技能定义不完整

缓解：

- 在任务中先补齐 spec，再在实现阶段清点现有 Skill 的 `allowed-tools`
- 明确无白名单时的默认策略：未声明即不收缩，只有声明后才执行硬约束

### 风险 2：trusted / untrusted 重分层可能影响现有 prompt 表现

缓解：

- 将变化写入 `prompt-system-composition` 和 `prompt-runtime-context-safety`
- 通过验收场景明确 system prompt 中允许出现的技能内容类型

### 风险 3：引用展开可能带来上下文量波动

缓解：

- 把引用展开限制为单文件、按需、可裁剪
- 明确 deterministic ordering 和 budget policy
