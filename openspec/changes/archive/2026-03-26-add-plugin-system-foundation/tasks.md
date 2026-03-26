## 1. 插件框架

- [x] 1.1 创建 `src/nini/plugins/__init__.py`、`src/nini/plugins/base.py`，定义 `Plugin` 抽象基类和 `DegradationInfo` 模型
- [x] 1.2 创建 `src/nini/plugins/registry.py`，实现 `PluginRegistry`（register、get、list_available、list_unavailable、initialize_all、shutdown_all）
- [x] 1.3 在 initialize_all 中实现单插件失败隔离和超时保护

## 2. 网络插件

- [x] 2.1 创建 `src/nini/plugins/network.py`，实现 `NetworkPlugin`（is_available、initialize、shutdown、get_degradation_info）
- [x] 2.2 实现网络可用性检测逻辑
- [x] 2.3 从 `config.py` 读取网络相关配置（超时、代理等）

## 3. 应用集成

- [x] 3.1 在 `src/nini/app.py` 的 lifespan 中集成 PluginRegistry 初始化和清理
- [x] 3.2 将 PluginRegistry 实例存储在 app.state 中供路由和 Agent 访问

## 4. 测试与验证

- [x] 4.1 编写 `tests/test_plugin_system.py`：Plugin 接口约束、Registry 注册/查询/生命周期、失败隔离
- [x] 4.2 编写 `tests/test_network_plugin.py`：可用性检测（mock 网络）、降级信息生成
- [x] 4.3 运行 `pytest -q` 确认全部测试通过且无回归
