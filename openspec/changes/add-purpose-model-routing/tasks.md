# 任务清单：按用途模型路由

## 1. 后端路由能力

- [x] 1.1 在 `config_manager` 增加用途路由配置读写（持久化到 `app_settings`）。
- [x] 1.2 在 `model_resolver` 增加用途首选路由与 `purpose` 参数透传。
- [x] 1.3 在 `reload_model_resolver` 启动流程加载用途路由配置。

## 2. API 与数据模型

- [x] 2.1 新增用途路由请求模型（schema）。
- [x] 2.2 新增 `GET /api/models/routing`。
- [x] 2.3 新增 `POST /api/models/routing` 并实现校验与持久化。
- [x] 2.4 保持现有 `/api/models/active`、`/api/models/preferred` 兼容。

## 3. 技能接入

- [x] 3.1 图片识别技能改造为走用途路由（`image_analysis`）。
- [x] 3.2 标题生成调用改造为用途路由（`title_generation`）。
- [x] 3.3 主对话调用改造为用途路由（`chat`）。

## 4. 前端配置

- [x] 4.1 在模型配置面板新增“用途模型路由”配置区。
- [x] 4.2 支持保存用途路由并即时刷新显示。
- [x] 4.3 保持现有提供商配置编辑体验不回归。

## 5. 测试与验证

- [x] 5.1 增加 resolver 用途优先级测试。
- [x] 5.2 增加 config_manager 用途配置读写测试。
- [x] 5.3 增加 image_analysis 使用用途路由测试。
- [x] 5.4 最小语法/类型校验通过。
