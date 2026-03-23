## Context

当前 `src/nini/tools/base.py` 定义了 `Skill` 类作为所有原子工具的基类：

```python
class Skill(ABC):
    """工具基类（历史原因命名为 Skill）"""
    name: str
    description: str
    parameters: dict

    @abstractmethod
    async def execute(self, session, **kwargs) -> SkillResult:
        ...
```

这与项目架构中的三层概念产生混淆：
1. **Tools**（`tools/`）：原子函数层，可直接被 LLM 调用
2. **Skills**（`skills/`）：完整工作流项目（预留扩展）
3. **Capabilities**（`capabilities/`）：用户层面能力元数据

`Skill` 类实际上属于 Tools 层，命名错误导致代码可读性下降。

## Goals / Non-Goals

**Goals:**
- 将 `Skill` 类重命名为 `Tool`，`SkillResult` 重命名为 `ToolResult`
- 更新所有继承 `Skill` 的子类（约 20+ 个工具）
- 更新所有导入语句和类型注解
- 更新文档和注释
- 不保留向后兼容别名（一次性彻底重构，避免技术债务）

**Non-Goals:**
- 不改变任何工具的功能逻辑
- 不改变外部 API 接口
- 不涉及 `skills/` 目录的重构（那是另一个变更）
- 不修改数据库 schema 或存储格式

## Decisions

### 1. 是否保留 Skill 别名？
**决定**：**不保留别名**，一次性彻底重构

**理由**：
- 这是内部代码重构，非公开 SDK；代码库完全可控
- 保留别名会延长技术债务，导致混乱（旧代码继续使用旧命名）
- Python 的 `@deprecated` 需额外依赖，增加复杂性
- 全仓一次性修改后，所有代码统一使用新命名，最干净
- 如真有外部依赖，CI 测试会立即暴露，修复简单

### 2. 重命名策略
**决定**：使用直接重命名而非继承链

```python
# 新方式
class Tool(ABC):
    ...

class DataAnalysisTool(Tool):  # 直接继承
    ...
```

**理由**：
- 干净、无技术债务
- IDE 重构工具支持良好
- 一次性修改，长期受益

### 3. 文件结构变更
**决定**：不移动文件，仅修改类名

`base.py` 保持位置，只是内部类名变更。

**理由**：
- `tools/base.py` 作为基类文件位置合理
- 仅类名与目录语义不匹配，文件位置无需调整

### 4. 联合类型注解处理
**决定**：所有 `SkillResult | dict[str, Any]` 统一改为 `ToolResult | dict[str, Any]`

**特别注意**：`capabilities/executors/difference_analysis.py` 中有 13 处复杂类型注解，需仔细更新。

**理由**：
- 类型注解是函数契约的一部分，必须同步更新
- IDE 全局替换可以处理大部分，但联合类型需要人工确认括号优先级

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 大量文件需要修改（50+ 文件，400+ 处引用） | 使用 IDE 全局重构，分阶段提交；每阶段验证 |
| 遗漏引用导致运行时错误 | 全仓搜索 `Skill`（排除 `skills/`、`MarkdownSkill` 等），CI 测试覆盖 |
| 联合类型注解复杂 | `difference_analysis.py` 有 13 处 `SkillResult \| dict`，需人工检查 |
| 合并冲突 | 快速完成（1-2 天内），冻结 tools/ 目录其他变更 |

## Migration Plan

1. **准备阶段**
   - 创建功能分支 `refactor/rename-skill-to-tool`
   - 冻结 tools/ 目录的其他变更

2. **实施阶段**
   - 修改 `base.py`：重命名 `Skill`→`Tool`，`SkillResult`→`ToolResult`
   - 批量修改 `tools/` 下所有工具的继承关系和导入
   - 修改 `registry_core.py` 和 `tool_adapter.py` 中的类型引用
   - 修改 `capabilities/executors/` 中的类型注解
   - 修改所有测试文件中的引用

3. **验证阶段**
   - 运行全部测试：`pytest -q`
   - 运行类型检查：`mypy src/nini`
   - 验证启动：`nini doctor && nini start`

4. **回滚策略**
   - 若发现问题，revert 整个 PR
   - 无数据变更，回滚安全
