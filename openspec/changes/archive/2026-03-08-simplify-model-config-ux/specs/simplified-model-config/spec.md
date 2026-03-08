## ADDED Requirements

### Requirement: 供应商范围限定为四个
系统 SHALL 在 AI 设置面板中仅展示以下四个供应商，其余供应商不在 UI 中暴露：
- DeepSeek（`provider_id: "deepseek"`）
- 智谱 GLM（`provider_id: "zhipu"`）
- 阿里百炼·通义千问（`provider_id: "dashscope"`）
- 本地 Ollama（`provider_id: "ollama"`）

#### Scenario: 设置面板只显示四个供应商卡片
- **WHEN** 用户打开 AI 设置面板
- **THEN** 界面展示且仅展示上述四个供应商的选择卡片，每张卡片包含供应商名称和密钥获取链接

---

### Requirement: 单一激活供应商
系统 SHALL 在同一时间只允许一个供应商处于激活状态。用户切换供应商后，旧供应商立即停用，所有新请求（含标题生成）均走新供应商。

#### Scenario: 切换供应商后立即生效
- **WHEN** 用户在 AI 设置面板选择新供应商并保存
- **THEN** 系统将新供应商标记为激活，旧供应商标记为非激活，后续所有 LLM 请求使用新供应商

#### Scenario: 任何时刻最多一个供应商激活
- **WHEN** 查询激活供应商列表
- **THEN** 结果中激活的供应商数量 ≤ 1

---

### Requirement: 密钥配置后动态拉取模型列表
系统 SHALL 在用户完成密钥填写并点击"测试并保存"后，调用 `GET /api/models/{provider_id}/available` 从供应商 API 实时拉取可用模型列表，在 UI 中展示供用户选择。Ollama 供应商通过检测本地服务自动获取已安装模型。

#### Scenario: 密钥有效时展示动态模型列表
- **WHEN** 用户填写 DeepSeek 密钥并点击"测试并保存"
- **THEN** 系统验证密钥有效性，成功后拉取模型列表并以选择列表形式展示，用户可从中选择主模型

#### Scenario: 密钥无效时提示错误不展示模型
- **WHEN** 用户填写无效密钥并点击"测试并保存"
- **THEN** 系统显示"密钥无效，请检查后重试"，不展示模型列表，不保存配置

#### Scenario: 模型列表拉取失败时提供降级
- **WHEN** 密钥有效但供应商模型 API 请求失败
- **THEN** 系统保存密钥配置，显示"模型列表获取失败"提示，并提供手动输入模型名的文本框

---

### Requirement: 前端友好名称映射层
前端 SHALL 维护静态模型名称映射表，将已知模型 ID 翻译为用户友好的显示名称和描述。未在映射表中的模型显示原始 ID。映射表不影响实际调用的模型 ID（始终使用原始 ID）。

#### Scenario: 已知模型显示友好名称
- **WHEN** 动态拉取的模型列表中包含 `deepseek-chat`
- **THEN** UI 展示为"DeepSeek V3  快速、经济"而非原始 ID

#### Scenario: 未知模型显示原始名称
- **WHEN** 动态拉取的模型列表中包含映射表未收录的模型 ID
- **THEN** UI 直接展示该模型 ID，不报错

---

### Requirement: 标题生成自动使用廉价模型
系统 SHALL 在触发标题生成时，自动从当前激活供应商的可用模型列表中，按预定义偏好顺序选择第一个匹配的廉价模型。此行为对用户完全透明，不在 UI 中暴露任何配置项。

偏好顺序（按 provider_id）：
- `deepseek`：`["deepseek-chat"]`
- `zhipu`：`["glm-4-flash", "glm-4-air", "glm-4"]`
- `dashscope`：`["qwen-turbo", "qwen-plus"]`
- `ollama`：`null`（使用用户选择的主模型）

若偏好列表所有模型均不可用，则回退到用户选择的主模型。

#### Scenario: 偏好廉价模型可用时自动选择
- **WHEN** 系统触发标题生成，激活供应商为 DeepSeek，`deepseek-chat` 在可用模型列表中
- **THEN** 标题生成请求使用 `deepseek-chat`，不使用用户可能选择的 `deepseek-reasoner`

#### Scenario: 偏好廉价模型不可用时回退主模型
- **WHEN** 系统触发标题生成，偏好列表中所有模型均不在可用列表中
- **THEN** 标题生成请求使用用户选择的主模型

#### Scenario: Ollama 供应商始终使用主模型
- **WHEN** 系统触发标题生成，激活供应商为 Ollama
- **THEN** 标题生成使用与主对话相同的本地模型

---

### Requirement: 本地 Ollama 自动检测已安装模型
系统 SHALL 在用户选择本地模型供应商时，通过 Ollama API（默认 `http://localhost:11434`）自动枚举已安装模型，无需用户手动输入模型名。用户可修改服务器地址。

#### Scenario: Ollama 服务运行时自动检测模型
- **WHEN** 用户选择本地模型，Ollama 服务在默认地址运行
- **THEN** 系统自动拉取已安装模型列表展示给用户，默认选中第一个

#### Scenario: Ollama 服务未运行时给出引导
- **WHEN** 用户选择本地模型，Ollama 服务无响应
- **THEN** 系统显示"未检测到 Ollama 服务，请确认已安装并启动"，并提供官方安装文档链接

---

### Requirement: 删除路由策略和优先级配置 UI
系统 SHALL 不在任何 UI 中暴露路由策略（用途级别供应商指定）和优先级排序（降级链）配置。

#### Scenario: AI 设置面板不含路由/优先级入口
- **WHEN** 用户打开 AI 设置面板
- **THEN** 界面中不存在"路由策略"、"优先级"、"用途配置"等任何入口或提示

---

### Requirement: 供应商密钥获取引导
系统 SHALL 在每个供应商的配置界面中，提供该供应商获取 API 密钥的官方页面链接，格式为可点击的外部链接。

#### Scenario: 配置 DeepSeek 时显示官方密钥获取地址
- **WHEN** 用户点击 DeepSeek 供应商卡片进入配置界面
- **THEN** 界面显示可点击链接指向 `platform.deepseek.com`，并标注"在此获取密钥"

#### Scenario: 各供应商链接指向正确官网
- **WHEN** 用户进入任一供应商配置界面
- **THEN** 展示的链接与该供应商实际密钥管理页面一致（DeepSeek/智谱/阿里百炼/Ollama 官网）
