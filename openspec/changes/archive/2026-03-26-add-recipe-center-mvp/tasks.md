## 1. Recipe 契约与后端入口

- [x] 1.1 定义首批 3 个 Recipe 的元数据 schema、配置文件格式与加载校验逻辑
- [x] 1.2 在会话启动流程中接入规则优先的 quick task / deep task 分类与 `recipe_id` 绑定
- [x] 1.3 为 deep task 增加项目工作区初始化、步骤状态记录与最小失败回退逻辑

## 2. WebSocket 与前端体验

- [x] 2.1 扩展 WebSocket 事件载荷，支持 Recipe 生命周期、步骤进度与工作区初始化反馈
- [x] 2.2 在首页新增 Recipe Center 卡片入口、示例输入与普通会话兜底入口
- [x] 2.3 在会话视图复用现有计划/任务组件展示 deep task 当前步骤、重试状态与下一步提示

## 3. 验证与文档

- [x] 3.1 为 Recipe 配置加载、deep task 状态机与 WebSocket 事件补充后端测试
- [x] 3.2 为首页入口与任务进度展示补充前端测试或 E2E 用例
- [x] 3.3 运行 `pytest -q` 与 `cd web && npm run build`，并更新相关文档说明 Recipe MVP 的使用方式与回退方式
