## Why

代码审查发现多个 P2/P3 级效率和可观测性问题：长期记忆 JSONL 全量加载（活跃用户 10K+ 条记忆时导致内存压力）、Agent 循环使用硬编码 128K 作为所有模型的上下文窗口（Claude 实际 200K、本地模型可能仅 8K）、压缩归档文件名秒级碰撞风险、图表 DPI 无上限校验（极端值导致内存爆炸）、知识库空状态返回空结果无法区分"无匹配"和"系统未就绪"。

这些问题单独不构成严重影响，但在活跃用户场景下累积效应明显。

## What Changes

- **长期记忆 JSONL 流式加载**：替代全量 `read_text().split("\n")` 为逐行流式读取
- **动态上下文窗口**：从 ModelResolver 获取当前模型的实际 context window 大小，替代硬编码 128000
- **压缩归档文件名防碰撞**：追加 UUID 短码到文件名
- **图表 DPI 上限校验**：添加 `300 <= dpi <= 600` 范围检查
- **知识库空状态元数据**：向量库查询返回 `availability` 字段区分"无匹配"和"未就绪"

## Capabilities

### New Capabilities
（无新能力——全部为现有功能的内部优化）

### Modified Capabilities

- `knowledge-retrieval`: 查询结果返回可用性元数据
- `chart-rendering`: DPI 范围校验

## Impact

- **受影响文件**：`memory/long_term_memory.py`、`agent/runner.py`、`memory/compression.py`、`charts/style_contract.py`、`knowledge/vector_store.py`
- **API 兼容性**：无 breaking change；知识检索结果新增可选 `availability` 字段
- **依赖**：无新依赖
