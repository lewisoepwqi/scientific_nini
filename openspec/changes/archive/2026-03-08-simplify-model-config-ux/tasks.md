## 1. 后端：试用模式基础设施

- [x] 1.1 在 `config.py` 中新增 `NINI_TRIAL_API_KEY`（默认空字符串）、`NINI_TRIAL_DAYS`（默认 14）配置字段
- [x] 1.2 在 `config_manager.py` 中实现 `get_trial_status()` — 读取 `trial_install_date` / `trial_activated`，计算剩余天数与是否到期
- [x] 1.3 在 `config_manager.py` 中实现 `activate_trial()` — 写入 `trial_install_date` 和 `trial_activated=true` 到 `app_settings`
- [x] 1.4 在 `api/models_routes.py` 中新增 `GET /api/trial/status` 端点，返回 `{ activated, days_remaining, expired }`

## 2. 后端：试用模式路由集成

- [x] 2.1 在 `agent/model_resolver.py` 中新增试用模式分支：若激活供应商为空且试用未到期，使用内嵌密钥构造 DeepSeek 客户端
- [x] 2.2 在 `agent/runner.py`（或 WebSocket 处理层）中新增前置检查：消息发送时若试用未激活且无密钥配置，调用 `activate_trial()` 并继续；若试用已到期且无密钥，推送 `{ type: "trial_expired" }` WebSocket 事件并中止
- [x] 2.3 编写单元测试覆盖试用状态计算逻辑（已激活/未激活/到期三种场景）

## 3. 后端：单一激活供应商与廉价模型路由

- [x] 3.1 在 `config_manager.py` 中实现 `set_active_provider(provider_id)` — 将指定供应商置为激活，其余置为非激活（单一激活约束）
- [x] 3.2 在 `agent/model_resolver.py` 中移除多提供商降级链逻辑，改为直接使用激活供应商的客户端
- [x] 3.3 在 `agent/model_resolver.py` 中新增 `_get_title_model(provider_id, available_models)` — 按 `TITLE_MODEL_PREFERENCE` 偏好顺序从可用列表匹配廉价模型，全不匹配时回退主模型
- [x] 3.4 在标题生成调用路径上应用 `_get_title_model()`，确保对用户透明
- [x] 3.5 收窄 `api/models_routes.py` 中供应商列表为 4 个（deepseek / zhipu / dashscope / ollama），移除其余供应商的注册与端点逻辑

## 4. 前端：删除旧组件

- [x] 4.1 删除 `web/src/components/model-config/RoutingTab.tsx`
- [x] 4.2 删除 `web/src/components/model-config/PriorityTab.tsx`
- [x] 4.3 移除 `ModelConfigPanel.tsx` 中对已删除 Tab 的引用和路由策略相关状态（第 5 组重写时完成）

## 5. 前端：重写 AI 设置面板

- [x] 5.1 重写 `ModelConfigPanel.tsx` 为三屏结构：已配置状态 / 供应商选择 / 密钥填写
- [x] 5.2 在供应商选择屏中实现四张供应商卡片（含供应商名称、简介、密钥获取外链）
- [x] 5.3 在密钥填写屏中实现：密钥输入框、粘贴按钮、"测试并保存"按钮
- [x] 5.4 在密钥验证成功后调用 `GET /api/models/{provider_id}/available`，拉取并展示动态模型列表
- [x] 5.5 在 `ModelConfigPanel.tsx` 中实现 `MODEL_DISPLAY_NAMES` 映射表（deepseek / zhipu / dashscope 三家已知模型的友好名称）
- [x] 5.6 将模型列表渲染逻辑应用映射表：已知模型显示友好名+描述，未知模型显示原始 ID
- [x] 5.7 实现本地 Ollama 配置屏：服务器地址输入框（默认 `http://localhost:11434`）、"检测可用模型"按钮、检测失败时显示安装引导链接

## 6. 前端：试用状态横幅

- [x] 6.1 新建 `web/src/components/TrialBanner.tsx`，从 `GET /api/trial/status` 获取状态
- [x] 6.2 实现三种显示逻辑：days_remaining > 3（灰色中性提示）/ ≤ 3（黄色警告）/ 已配置密钥（不渲染）
- [x] 6.3 在主布局（`ChatPanel` 或顶部区域）中挂载 `TrialBanner`
- [x] 6.4 处理 WebSocket `trial_expired` 事件：显示阻断提示并跳转 AI 设置面板

## 7. 前端：简化模型选择器

- [x] 7.1 重写 `ModelSelector.tsx`，仅显示当前激活供应商和已选主模型（去掉多供应商并排展示）
- [x] 7.2 点击模型选择器时跳转 AI 设置面板（而非展开下拉列表选其他供应商）

## 8. 验证与收尾

- [x] 8.1 端到端验证：首次启动 → 发消息 → 试用激活 → 正常响应（需运行时验证）
- [x] 8.2 端到端验证：配置 DeepSeek 密钥 → 拉取模型列表 → 选模型 → 保存 → 对话正常（需运行时验证）
- [x] 8.3 端到端验证：切换供应商（DeepSeek → 智谱）→ 旧供应商停用 → 新供应商生效（需运行时验证）
- [x] 8.4 端到端验证：模拟试用到期 → 发消息 → 显示阻断提示（需运行时验证）
- [x] 8.5 运行 `pytest tests/test_trial_mode.py` 确认试用逻辑 4 项全部通过
- [x] 8.6 运行 `tsc --noEmit` 确认前端 TypeScript 无报错
