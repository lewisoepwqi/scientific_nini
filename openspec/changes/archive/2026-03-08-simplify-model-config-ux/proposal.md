## Why

当前模型配置界面（三 Tab：凭证管理/路由策略/优先级）面向开发者设计，暴露了 API Key、Base URL、路由策略、降级优先级等大量技术概念，科研用户无法独立完成配置，严重阻碍产品外部分发与付费转化。需要一次彻底的 UX 简化，配合本地试用机制降低用户启动门槛。

## What Changes

- **新增** 14 天本地试用模式：内嵌试用密钥，首次发消息时自动激活，倒计时提示，到期后软阻断
- **新增** AI 设置面板（替换现有模型配置面板），仅保留 4 个供应商卡片（DeepSeek / 智谱 GLM / 通义千问 / 本地 Ollama）
- **新增** 密钥配置后动态从供应商 API 拉取可用模型列表，前端覆盖友好名称映射
- **修改** 单一激活供应商逻辑：同一时间只有一个供应商激活，切换即生效
- **删除** 路由策略 Tab（6 种用途路由配置）
- **删除** 优先级 Tab（拖拽排序降级链）
- **内部保留** 标题生成廉价模型自动选择（用户不可见，后端按供应商偏好顺序从动态模型列表中选最便宜的）
- **新增** 首次使用软提示：用户可进入 App 浏览，发送第一条消息时触发配置引导

## Capabilities

### New Capabilities

- `trial-mode`: 本地试用机制——安装日期记录、内嵌密钥管理、试用状态查询与到期判断
- `simplified-model-config`: 面向科研用户的 AI 设置面板——4 供应商卡片、单一激活、动态模型列表、友好名称映射

### Modified Capabilities

（无现有 spec 需要变更，模型配置功能此前未建立 spec）

## Impact

**后端：**
- `src/nini/config.py`：新增试用配置字段（内嵌密钥、试用天数）
- `src/nini/config_manager.py`：新增试用状态持久化（安装日期、激活标志）
- `src/nini/agent/model_resolver.py`：新增试用模式路由分支；移除多提供商降级链（单一激活）；新增廉价模型自动选择（标题生成）
- `src/nini/api/models_routes.py`：收窄提供商为 4 个；新增试用状态端点；移除路由策略和优先级相关端点

**前端：**
- `web/src/components/ModelConfigPanel.tsx`：完全重写
- `web/src/components/model-config/CredentialsTab.tsx`：改写为供应商卡片选择 + 动态模型列表
- `web/src/components/model-config/RoutingTab.tsx`：**删除**
- `web/src/components/model-config/PriorityTab.tsx`：**删除**
- `web/src/components/ModelSelector.tsx`：简化，反映单一供应商状态
- 新增试用状态横幅组件（`TrialBanner.tsx`）
- 新增供应商密钥获取引导链接

**数据：**
- SQLite `app_settings` 表新增 `trial_install_date`、`trial_activated` 字段
- `model_configs` 表的多提供商并存数据在迁移后退化为单一激活记录
