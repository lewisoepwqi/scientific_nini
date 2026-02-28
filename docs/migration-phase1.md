# Phase 1 迁移文档

本文档记录从旧架构到新三层架构的迁移过程。

## 变更摘要

### 1. SkillRegistry → ToolRegistry

**变更原因**：澄清概念，区分 Tools（原子函数）和 Capabilities（用户能力）。

**影响范围**：仅内部实现，保持向后兼容。

**迁移前**：
```python
from nini.tools.registry import SkillRegistry, create_default_registry

registry = SkillRegistry()
```

**迁移后**：
```python
from nini.tools.registry import ToolRegistry, create_default_tool_registry
# 或继续使用旧名称（别名兼容）
from nini.tools.registry import SkillRegistry, create_default_registry

registry = ToolRegistry()  # 或 SkillRegistry()
```

**兼容性**：✅ 完全兼容，旧代码无需修改

---

### 2. 新增 Capabilities 模块

**新增文件**：
- `capabilities/base.py` - Capability 基类
- `capabilities/registry.py` - CapabilityRegistry
- `capabilities/defaults.py` - 默认能力定义
- `capabilities/implementations/difference_analysis.py` - 差异分析实现

**新增 API**：
- `GET /api/capabilities` - 列出所有能力
- `GET /api/capabilities/{name}` - 获取单个能力
- `POST /api/capabilities/suggest` - 基于意图推荐能力
- `POST /api/capabilities/{name}/execute` - 执行能力（仅限已实现的能力）

**新增前端组件**：
- `CapabilityPanel.tsx` - 能力面板（紫色 Sparkles 图标）

---

### 3. Skill 概念澄清

**明确**：`skills/` 目录存放完整的工作流项目，不是简单的提示词模板。

**典型 Skill 结构**：
```
skills/{skill-name}/
├── SKILL.md              # 元数据和说明
├── scripts/              # 可执行脚本
├── references/           # 参考文档
└── assets/               # 资源文件
```

**示例**：`skills/root-analysis`
- 包含 R/Python 分析脚本
- 包含批量处理工具
- 包含数据验证脚本
- 包含统计方法文档

---

## 架构对比

### 迁移前（旧认知）

```
SkillRegistry
├── Function Skills (26个)
│   ├── t_test
│   ├── anova
│   └── ...
└── Markdown Skills (提示词模板)
```

### 迁移后（新架构）

```
ToolRegistry (原 SkillRegistry)
├── t_test
├── anova
└── ... (26个原子工具)

CapabilityRegistry (新增)
├── difference_analysis (差异分析)
├── correlation_analysis (相关性分析)
├── data_exploration (数据探索)
└── ... (7个用户能力)

Skill 目录 (澄清概念)
├── root-analysis/ (完整项目：脚本+模板+文档)
└── ... (更多工作流项目)
```

---

## 开发者迁移指南

### 如果你是 Tool 开发者

**无需修改**。`ToolRegistry` 完全兼容旧接口。

**建议**：
- 更新文档注释，明确是 "Tool" 而非 "Skill"
- 参考新的架构概念说明

### 如果你是 API 消费者

**新端点可用**：

```bash
# 获取能力列表
curl /api/capabilities

# 获取单个能力
curl /api/capabilities/difference_analysis

# 基于意图推荐
curl -X POST /api/capabilities/suggest \
  -d "user_message=帮我比较两组数据的差异"

# 执行能力
curl -X POST /api/capabilities/difference_analysis/execute \
  -d '{
    "session_id": "xxx",
    "params": {
      "dataset_name": "data",
      "value_column": "score",
      "group_column": "group"
    }
  }'
```

### 如果你是前端开发者

**新增组件**：

```tsx
import CapabilityPanel from './components/CapabilityPanel'

// 在 App.tsx 中使用
<CapabilityPanel
  open={showCapabilities}
  onClose={() => setShowCapabilities(false)}
/>
```

**Store 更新**：

```tsx
// 获取能力列表
const capabilities = useStore(s => s.capabilities)
const fetchCapabilities = useStore(s => s.fetchCapabilities)

// 在组件加载时获取
useEffect(() => {
  fetchCapabilities()
}, [])
```

---

## 测试验证

### 运行 Capability 测试

```bash
python -m pytest tests/test_difference_analysis_capability.py -xvs
```

### 验证 API 端点

```bash
# 启动服务
nini start

# 测试端点
curl http://localhost:8000/api/capabilities
```

### 验证前端构建

```bash
cd web
npm run build
```

---

## 术语对照表

| 旧术语 | 新术语 | 说明 |
|--------|--------|------|
| Skill (泛指) | Tool | 模型可调用的原子函数 |
| Skill (泛指) | Capability | 用户层面的能力封装 |
| Function Skill | Tool | 明确为原子工具 |
| Markdown Skill | Skill | 完整工作流项目（保留原称） |
| SkillRegistry | ToolRegistry | 管理 Tools 的注册中心 |
| - | CapabilityRegistry | 管理 Capabilities 的注册中心（新增） |

---

## 下一步计划

### Phase 2（建议）

1. **更多 Capability 实现**
   - 相关性分析 Capability
   - 回归分析 Capability
   - 数据清洗 Capability

2. **Capability 与 Skill 关联**
   - Skill 声明实现的 Capability
   - 基于 Capability 推荐 Skill

3. **Capability 参数自动生成**
   - 根据 required_tools 聚合参数
   - 动态生成表单 schema

### Phase 3（建议）

1. **Capability 市场**
   - 用户可安装第三方 Capability
   - Capability 评分和评论

2. **可视化编排器**
   - 拖拽式 Capability 工作流编排
   - 自定义 Capability（组合现有 Capability）

---

## 参考文档

- `architecture-concepts.md` - 三层架构概念说明
- `capability-development-guide.md` - Capability 开发指南
- `src/nini/capabilities/` - Capability 实现代码
