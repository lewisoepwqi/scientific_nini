## ADDED Requirements

### Requirement: 本地试用状态初始化
系统 SHALL 在用户首次发送消息且未配置任何供应商密钥时，自动激活试用模式：将当前 UTC 日期写入本地持久化存储（`app_settings.trial_install_date`），并将 `trial_activated` 标记置为 true。内嵌试用密钥由 `NINI_TRIAL_API_KEY` 环境变量或 `config.py` 默认值提供，供应商固定为 DeepSeek。

#### Scenario: 首次发消息触发试用激活
- **WHEN** 用户发送第一条消息，且本地无供应商密钥配置，且 `trial_activated` 为 false
- **THEN** 系统写入 `trial_install_date`（当前日期）和 `trial_activated = true`，使用内嵌密钥处理该消息，并在 UI 显示"试用已开始，剩余 14 天"提示

#### Scenario: 已配置密钥时不激活试用
- **WHEN** 用户发送消息，且已存在有效供应商密钥配置
- **THEN** 系统不修改试用状态，直接使用用户配置的密钥

---

### Requirement: 试用剩余天数计算
系统 SHALL 通过 `GET /api/trial/status` 端点返回试用状态，包含：`activated`（布尔）、`days_remaining`（整数，0 表示已到期）、`expired`（布尔）。天数基于 `trial_install_date` 与当前日期的差值计算，总时限 14 天。

#### Scenario: 查询试用中的剩余天数
- **WHEN** 客户端请求 `/api/trial/status`，试用已激活且在有效期内
- **THEN** 返回 `{ activated: true, days_remaining: N, expired: false }`，N 为正整数

#### Scenario: 查询已到期试用
- **WHEN** 客户端请求 `/api/trial/status`，当前日期超过 `trial_install_date + 14 天`
- **THEN** 返回 `{ activated: true, days_remaining: 0, expired: true }`

#### Scenario: 查询未激活试用
- **WHEN** 客户端请求 `/api/trial/status`，试用从未激活
- **THEN** 返回 `{ activated: false, days_remaining: 14, expired: false }`

---

### Requirement: 试用到期阻断
系统 SHALL 在试用到期且用户未配置任何自有供应商密钥时，拒绝处理用户消息，并通过 WebSocket 推送 `trial_expired` 事件引导用户配置密钥。

#### Scenario: 试用到期时发送消息被阻断
- **WHEN** 用户发送消息，试用已过期，且无自有密钥配置
- **THEN** 系统不调用任何 LLM，通过 WebSocket 推送 `{ type: "trial_expired" }` 事件，前端展示"试用已结束，请配置自己的密钥"并跳转配置面板

#### Scenario: 试用到期但已配置密钥时正常使用
- **WHEN** 用户发送消息，试用已过期，但存在有效自有密钥配置
- **THEN** 系统使用用户配置的密钥正常处理消息，不触发试用阻断逻辑

---

### Requirement: 试用倒计时 UI 提示
前端 SHALL 在主界面展示试用状态横幅（`TrialBanner` 组件），规则如下：
- 试用剩余 > 3 天：显示中性提示"试用中 · 剩余 N 天 | 配置自己的密钥"
- 试用剩余 ≤ 3 天：显示警告提示"试用将在 N 天后到期，建议现在配置密钥"（黄色高亮）
- 试用到期：不显示横幅（由阻断流程处理）
- 已配置自有密钥：不显示横幅

#### Scenario: 剩余天数充足时显示中性横幅
- **WHEN** 前端加载，试用激活且 `days_remaining > 3`，无自有密钥
- **THEN** 显示灰色/蓝色横幅，内容包含剩余天数和"配置密钥"入口链接

#### Scenario: 剩余天数不足时显示警告横幅
- **WHEN** 前端加载，试用激活且 `days_remaining <= 3`，无自有密钥
- **THEN** 显示黄色警告横幅，突出剩余天数，引导立即配置

#### Scenario: 已配置密钥时隐藏横幅
- **WHEN** 前端加载，用户已有激活的自有供应商配置
- **THEN** `TrialBanner` 不渲染
