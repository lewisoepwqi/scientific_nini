## Why

Nini 定位为本地优先平台，但文献调研（C7）等新阶段能力需要联网检索。根据架构决策，联网功能应以可选插件形式存在，离线时优雅降级并明确告知用户。当前代码中没有插件系统，外部服务调用（如 `fetch_url` 工具）是硬编码的。本 change 建立插件系统基础框架，为后续 C7（文献调研）等需要外部服务的 change 提供统一的注册、发现、降级机制。

## What Changes

- **定义插件接口**：在 `src/nini/plugins/` 中新建模块，定义 `Plugin` 基类（name、version、description、is_available、initialize、shutdown）。
- **实现插件注册表**：`PluginRegistry` 管理插件生命周期（注册、发现、启用/禁用、状态查询）。
- **实现可用性检测**：每个 Plugin 实现 `is_available()` 方法，运行时检测外部依赖是否就绪（如网络连通性、API key 配置）。
- **实现降级通知机制**：当 Plugin 不可用时，提供结构化的降级信息（原因、替代建议），通过事件通知 Agent 和前端。
- **新增网络插件骨架**：作为第一个插件示例，创建 `NetworkPlugin`，封装网络请求能力的可用性检测。

## Non-Goals

- 不实现具体的文献检索功能（属于 C7）。
- 不实现插件的热加载/卸载（V1 仅支持启动时加载）。
- 不实现插件市场或第三方插件分发。
- 不迁移现有 `fetch_url` 工具到插件系统（仅新建骨架）。

## Capabilities

### New Capabilities

- `plugin-system`: 插件系统框架——涵盖 Plugin 基类、PluginRegistry、可用性检测、降级通知机制
- `network-plugin`: 网络插件骨架——涵盖 NetworkPlugin 实现、网络可用性检测、离线降级信息

### Modified Capabilities

（无既有 spec 需要修改）

## Impact

- **影响文件**：`src/nini/plugins/`（新建模块）、`src/nini/app.py`（插件初始化注入点）
- **影响范围**：应用启动流程新增插件初始化步骤
- **API / 依赖**：无新增外部依赖，`/api/plugins` 端点（可选，供前端查询插件状态）
- **风险**：插件初始化失败不应阻断应用启动——需确保 try/except 保护
- **回滚**：删除 plugins 模块 + revert app.py 的初始化注入即可恢复
- **验证方式**：单元测试验证 Plugin 接口、Registry 注册/查询、可用性检测、降级信息生成
