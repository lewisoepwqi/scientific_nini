## Context

C4 提供 Skill 契约运行时，C5 提供插件系统和 NetworkPlugin 骨架。现有 `fetch_url` 工具可发起 HTTP 请求，但没有学术搜索特化的工具。现有 `citation_management` Capability 处理引用格式化，但不涉及检索。

## Goals / Non-Goals

**Goals:**
- 创建 literature-review Skill（带 contract）
- 实现 search_literature 工具（Semantic Scholar + CrossRef）
- 实现离线降级路径
- 验证 NetworkPlugin 集成

**Non-Goals:**
- 不实现全文下载
- 不实现引文网络分析

## Decisions

### D1: Skill 契约设计

**选择**：四步线性 DAG，trust_ceiling=t1，evidence_required=true：

```
search_papers → filter_papers → synthesize → generate_output
```

- `search_papers`：调用 search_literature 工具检索文献（或引导用户手动提供）
- `filter_papers`：LLM 引导用户按相关性、时效性、影响因子筛选
- `synthesize`：LLM 综合筛选后的文献，提取关键发现和争议点
- `generate_output`：生成文献综述大纲或摘要，标注 O2 草稿级，每个结论附来源

**理由**：与 C1 strategy 中文献调研策略的四步流程一致。evidence_required=true 要求每个关键结论标注来源。

### D2: search_literature 工具设计

**选择**：继承 Tool 基类，参数：query（检索词）、max_results（默认 20）、year_from（起始年份，可选）、sort_by（relevance/date）。

实现：
1. 优先使用 Semantic Scholar API（免费，无需 API key）
2. 降级到 CrossRef API（免费，覆盖更广）
3. 都不可用时返回 ToolResult 提示用户手动提供

返回：文献列表（title、authors、year、abstract、doi、citation_count）。

**理由**：两个 API 都免费且无需注册，适合本地优先定位。通过 NetworkPlugin 检测可用性。

### D3: 离线降级策略

**选择**：
1. search_papers 步骤检测 NetworkPlugin 是否可用
2. 不可用时，步骤自动切换为「手动模式」：提示用户上传 PDF 或提供文献引用列表
3. 用户提供的文献通过现有 knowledge 模块解析和存储
4. 后续步骤（筛选、综合、输出）正常运行，基于用户提供的文献

**理由**：与 C5 的降级机制一致——明确告知用户，提供替代路径，不静默降级。

### D4: 与 NetworkPlugin 的集成

**选择**：search_literature 工具在执行前查询 `PluginRegistry.get("network")`。若 NetworkPlugin 不可用，直接返回降级 ToolResult。NetworkPlugin 的 is_available() 扩展为检测 Semantic Scholar API 端点可达性。

**理由**：工具级别的降级检测，简单直接。不需要在 ContractRunner 层面做额外处理。

## Risks / Trade-offs

- **[风险] Semantic Scholar API 限流** → 实现 rate limiting（每秒 1 请求），超限时降级到 CrossRef。
- **[风险] 检索结果质量有限** → trust_ceiling=t1 限制输出为 O2 草稿级，提示用户验证。
- **[回滚]** 删除新建文件 + revert registry.py 和 network.py 即可恢复。
