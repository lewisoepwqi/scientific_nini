# 过度设计清理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 系统性清理项目中的过度设计——删除死代码、合并重复实现、拆分 God Object——在不损失任何功能的前提下削减约 7,000-9,000 行代码。

**Architecture:** 分三个 Phase 执行：Phase 1 删除已确认的死代码（风险极低），Phase 2 合并重复实现（中等风险），Phase 3 拆分 God Object（高风险需充分测试）。每个 Phase 产出可独立验证、可独立合并的增量。

**Tech Stack:** Python 3.12, pytest, mypy, Black; TypeScript/Vitest (前端)

---

## Phase 1: 死代码删除（风险极低）

本阶段所有删除项均经过验证：外部无导入、无调用、无运行时依赖。每项删除后运行全量测试确认无回归。

---

### Task 1: 删除 `capabilities/implementations/` 空壳目录

**Files:**
- Delete: `src/nini/capabilities/implementations/` 整个目录（7 个文件，142 行）
- Verify: `src/nini/capabilities/defaults.py`（确认直接从 executors/ 导入）
- Verify: `src/nini/capabilities/__init__.py`

**验证事实：** `implementations/` 中 6 个 capability 文件全部只做 `from nini.capabilities.executors.xxx import Xxx` 的 re-export。`defaults.py` 直接从 `executors/` 导入，完全绕过 implementations/。全仓库无任何 `from nini.capabilities.implementations import` 的外部导入。

- [ ] **Step 1: 全局搜索确认无外部引用**

```bash
grep -r "from nini.capabilities.implementations" src/ --include="*.py" \
  | grep -v "implementations/__init__.py" \
  | grep -v "implementations/correlation" \
  | grep -v "implementations/data_cleaning" \
  | grep -v "implementations/data_exploration" \
  | grep -v "implementations/difference" \
  | grep -v "implementations/regression" \
  | grep -v "implementations/visualization"
```

Expected: 无输出（无外部导入）

- [ ] **Step 2: 删除 implementations/ 目录**

```bash
rm -rf src/nini/capabilities/implementations/
```

- [ ] **Step 3: 检查 capabilities/__init__.py 是否引用了 implementations**

读取 `src/nini/capabilities/__init__.py`，如果包含 `from nini.capabilities.implementations import ...` 的行，删除这些行。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add src/nini/capabilities/implementations/ src/nini/capabilities/__init__.py
git commit -m "chore(capabilities): 删除 implementations/ 空壳目录，executors/ 已是唯一实现"
```

---

### Task 2: 删除 `intent/multi_intent.py` 死代码

**Files:**
- Delete: `src/nini/intent/multi_intent.py`（80 行）
- Modify: `src/nini/intent/__init__.py`（移除 multi_intent 导出）

**验证事实：** `detect_multi_intent` 和 `MultiIntentResult` 仅在 `intent/__init__.py` 中被导出，全仓库无任何外部导入。

- [ ] **Step 1: 确认无外部导入**

```bash
grep -r "multi_intent\|detect_multi_intent\|MultiIntentResult" src/ --include="*.py" \
  | grep -v "intent/multi_intent.py" \
  | grep -v "intent/__init__.py"
```

Expected: 无输出

- [ ] **Step 2: 修改 `src/nini/intent/__init__.py`**

删除以下行：
```python
from nini.intent.multi_intent import MultiIntentResult, detect_multi_intent
```
和 `__all__` 列表中的 `"detect_multi_intent"` 和 `"MultiIntentResult"`。

- [ ] **Step 3: 删除文件**

```bash
rm src/nini/intent/multi_intent.py
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add src/nini/intent/multi_intent.py src/nini/intent/__init__.py
git commit -m "chore(intent): 删除从未接入的 multi_intent 模块"
```

---

### Task 3: 删除前端 `store/event-types.ts` 死代码

**Files:**
- Delete: `web/src/store/event-types.ts`（428 行）

**验证事实：** 全 `web/src/` 目录中零导入。所有事件处理器直接操作 `unknown`/`Record<string, unknown>`。

- [ ] **Step 1: 确认无导入**

```bash
grep -r "event-types" web/src/ --include="*.ts" --include="*.tsx"
```

Expected: 无输出

- [ ] **Step 2: 删除文件**

```bash
rm web/src/store/event-types.ts
```

- [ ] **Step 3: 运行前端测试 + 构建检查**

```bash
cd web && npm test -- --run && npm run build
```

Expected: 测试通过，构建成功

- [ ] **Step 4: 提交**

```bash
git add web/src/store/event-types.ts
git commit -m "chore(web): 删除未使用的 event-types.ts 类型定义"
```

---

### Task 4: 删除 `knowledge/hierarchical/retriever.py` 中的死类 `HierarchicalKnowledgeRetriever`

**Files:**
- Modify: `src/nini/knowledge/hierarchical/retriever.py`（删除 `HierarchicalKnowledgeRetriever` 类及其专属辅助类）
- Verify: 无外部导入该类

**验证事实：** `HierarchicalKnowledgeRetriever` 与 `UnifiedRetriever` 几乎逐字重复了约 180 行检索逻辑。全仓库无任何 `from ... import HierarchicalKnowledgeRetriever` 的外部导入，`__init__.py` 也未导出此类。

- [ ] **Step 1: 确认无外部导入**

```bash
grep -r "HierarchicalKnowledgeRetriever" src/ --include="*.py"
```

Expected: 仅在 `retriever.py` 自身中出现

- [ ] **Step 2: 识别类的起止行**

```bash
grep -n "class HierarchicalKnowledgeRetriever\|class RRFFusion\|class ContextAssembler" \
  src/nini/knowledge/hierarchical/retriever.py
```

- [ ] **Step 3: 确认 RRFFusion 和 ContextAssembler 的归属**

```bash
grep -r "RRFFusion\|ContextAssembler" src/ --include="*.py" | grep -v "retriever.py"
```

如果 `unified_retriever.py` 中有这些类的独立副本，则 `retriever.py` 中的对应类也可以删除。如果 `unified_retriever.py` 从 `retriever.py` 导入它们，只能删除 `HierarchicalKnowledgeRetriever`，保留其他类。

- [ ] **Step 4: 删除 HierarchicalKnowledgeRetriever 类**

仅删除 `HierarchicalKnowledgeRetriever` 类定义（约 180 行）。是否删除 `RRFFusion`/`ContextAssembler` 取决于 Step 3 结果。

- [ ] **Step 5: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/nini/knowledge/hierarchical/retriever.py
git commit -m "chore(knowledge): 删除与 UnifiedRetriever 重复的 HierarchicalKnowledgeRetriever 死类"
```

---

### Task 5: 删除 `workflow/` 核心引擎死代码

**Files:**
- Modify: `src/nini/workflow/executor.py`（删除 `execute_workflow()` 函数和相关执行逻辑）
- Modify: `src/nini/workflow/validator.py`（删除仅服务于 executor 的校验函数）
- Modify: `src/nini/workflow/template.py`（仅删除 executor 专属字段，不动数据模型字段）
- Modify: `src/nini/workflow/__init__.py`（移除 execute_workflow 导出）

**验证事实：** `execute_workflow()` 是 workflow 系统的核心 DAG 引擎，但全仓库零外部调用。`workflow_tool.py` 仅使用 `extractor.py`（提取模板）和 `store.py`（持久化模板），不调用 executor。`ApplyWorkflowTool` 的注释承认执行从未接通。

**数据安全注意：** `template.py` 中的 Pydantic 模型字段用于序列化/反序列化 `data/sessions/*/workspace/` 下的 workflow 文件。删除字段前必须确认这些字段不存在于持久化数据中，否则已有会话读取时会丢失数据。

保留 `extractor.py`、`store.py` 和 `template.py` 中的基础数据模型（`WorkflowStep`、`WorkflowTemplate`），因为 `workflow_tool.py` 依赖它们。

- [ ] **Step 1: 确认 execute_workflow 无外部调用**

```bash
grep -r "execute_workflow\|load_yaml_workflow" src/ --include="*.py" \
  | grep -v "workflow/executor.py" \
  | grep -v "workflow/__init__.py"
```

Expected: 无输出

- [ ] **Step 2: 数据安全检查——确认 template.py 中计划删除的字段未持久化**

```bash
grep -r "skill\|tool_name\|parameters" data/sessions/ 2>/dev/null | grep "\.json" | head -5
```

如果有输出，先确认这些字段是否就是 template.py 中"兼容旧模板"的 `skill`/`tool_name`/`parameters` 字段。如果有持久化数据依赖这些字段，**暂停 template.py 的字段清理**，仅删除 executor.py 中的代码。

- [ ] **Step 3: 精简 executor.py**

读取 `src/nini/workflow/executor.py`。删除 `execute_workflow()` 函数（约 200 行）和 `load_yaml_workflow()` / `load_yaml_workflow_file()` 函数。保留文件中被 `workflow_tool.py` 间接使用的 import（如果有）。如果删除后文件为空，直接删除整个文件。

- [ ] **Step 4: 精简 validator.py**

读取 `src/nini/workflow/validator.py`。保留 `detect_cycle()` 函数（如被其他地方引用）。确认 `safe_resolve_reference` 是否被 executor 以外的代码使用：

```bash
grep -r "safe_resolve_reference" src/ --include="*.py" \
  | grep -v "workflow/validator.py" \
  | grep -v "workflow/executor.py"
```

如果仅被 executor.py 使用，删除 `safe_resolve_reference` 及危险模式扫描等仅服务于 executor 的逻辑。

- [ ] **Step 5: 仅在 Step 2 确认安全的情况下——精简 template.py**

读取 `src/nini/workflow/template.py`。仅删除 executor 专属字段（如 `skill` / `tool_name` 双字段、`parameters` / `arguments` 双字段中的兼容字段）。保留所有 `workflow_tool.py` 依赖的字段。

- [ ] **Step 6: 更新 `__init__.py`**

移除已删除函数的导出：
```python
# 删除这行
from nini.workflow.executor import execute_workflow, load_yaml_workflow, load_yaml_workflow_file
```
并从 `__all__` 中移除对应名称。

- [ ] **Step 7: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add src/nini/workflow/executor.py src/nini/workflow/validator.py \
        src/nini/workflow/template.py src/nini/workflow/__init__.py
git commit -m "chore(workflow): 删除从未调用的 execute_workflow 核心引擎和冗余校验逻辑"
```

---

### Task 6: 删除 `knowledge/hierarchical/` 实验性子系统

**Files:**
- Delete: `src/nini/knowledge/hierarchical/` 整个目录（约 1,900 行）
- Modify: `src/nini/knowledge/__init__.py`（移除 hierarchical 导出）
- Modify: `src/nini/knowledge/context_injector.py`（清理相关 import）
- Modify: `src/nini/config.py`（移除 `enable_hierarchical_index` 字段或标记为废弃）

**决策依据（已确认，无需执行时再判断）：**
- `config.py:309` 中 `enable_hierarchical_index: bool = False`，默认关闭
- 全仓库中仅 `src/nini/config.py` 和 `hierarchical/` 内部引用此配置
- 无任何生产代码在 `if enable_hierarchical_index` 分支中激活该系统
- `QueryRouter` 的 strategy 路由是空壳，`RRFFusion` 被实例化但从未参与融合计算

**结论：直接删除整个目录。**

- [ ] **Step 1: 确认 hierarchical/ 的外部依赖**

```bash
grep -r "hierarchical\|HierarchicalKnowledge\|UnifiedRetriever\|enable_hierarchical_index" \
  src/ --include="*.py" | grep -v "hierarchical/" | grep -v "test"
```

检查所有依赖路径，确认要清理的文件列表。

- [ ] **Step 2: 删除整个目录**

```bash
rm -rf src/nini/knowledge/hierarchical/
```

- [ ] **Step 3: 清理外部引用**

对 Step 1 中发现的每个引用文件，删除对应的 import 行和 `if enable_hierarchical_index` 分支。

读取 `src/nini/knowledge/__init__.py` 和 `src/nini/knowledge/context_injector.py`，清理所有 `from nini.knowledge.hierarchical import ...` 和相关条件分支。

- [ ] **Step 4: 处理 config.py 中的 enable_hierarchical_index**

读取 `src/nini/config.py`，找到 `enable_hierarchical_index` 字段。由于子系统已删除，删除该字段定义。如果 `.env` 模板文件中有此字段，也一并删除。

- [ ] **Step 5: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/nini/knowledge/ src/nini/config.py
git commit -m "chore(knowledge): 删除默认关闭且从未激活的 hierarchical 实验性子系统"
```

---

### Task 7: 合并 knowledge/ 顶层重复哈希工具函数

**Files:**
- Create: `src/nini/knowledge/_utils.py`（提取共享的 `compute_knowledge_file_hashes`）
- Modify: `src/nini/knowledge/vector_store.py`（替换为共享函数）
- Modify: `src/nini/knowledge/local_bm25.py`（替换为共享函数）

**验证事实：** `_compute_file_hashes()` 在 `vector_store.py`、`local_bm25.py`（Task 6 保留后 `hierarchical/index.py` 已删除）各实现了一份几乎一模一样的 SHA-256 哈希计算。

- [ ] **Step 1: 逐一比对三处实现的差异**

```bash
grep -A 15 "_compute_file_hashes\|def _compute_file_hash" \
  src/nini/knowledge/vector_store.py src/nini/knowledge/local_bm25.py
```

逐行比对输出，确认：文件扩展名过滤（`.md`？）、README 排除逻辑、路径计算方式（`relative_to` 基准）是否完全一致。如有差异，记录后在 Step 2 的共享函数中统一处理。

- [ ] **Step 2: 创建 `src/nini/knowledge/_utils.py`**

```python
"""知识库内部共享工具函数。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def compute_knowledge_file_hashes(knowledge_dir: Path) -> dict[str, str]:
    """遍历知识目录，计算所有 .md 文件的 SHA-256 哈希。

    排除 README.md。

    Returns:
        字典 {relative_path_str: sha256_hex}
    """
    hashes: dict[str, str] = {}
    for fp in sorted(knowledge_dir.rglob("*.md")):
        if fp.name == "README.md":
            continue
        rel = str(fp.relative_to(knowledge_dir))
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    return hashes
```

如果 Step 1 发现两处实现有差异，在函数中统一为更严格的版本，并在注释中说明。

- [ ] **Step 3: 替换 vector_store.py 中的实现**

读取 `src/nini/knowledge/vector_store.py`，找到 `_compute_file_hashes` 方法。

在文件顶部 import 区域添加：
```python
from nini.knowledge._utils import compute_knowledge_file_hashes
```

删除 `_compute_file_hashes` 方法定义，将调用点 `self._compute_file_hashes(self.knowledge_dir)` 改为 `compute_knowledge_file_hashes(self.knowledge_dir)`。

- [ ] **Step 4: 替换 local_bm25.py 中的实现**

同 Step 3，对 `src/nini/knowledge/local_bm25.py` 做相同替换。

- [ ] **Step 5: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/nini/knowledge/_utils.py \
        src/nini/knowledge/vector_store.py \
        src/nini/knowledge/local_bm25.py
git commit -m "refactor(knowledge): 提取 compute_knowledge_file_hashes 为共享工具函数，消除两处重复"
```

---

## Phase 1 小结

| Task | 操作 | 预计删减行数 |
|------|------|------------|
| Task 1 | 删除 capabilities/implementations/ | ~142 行 |
| Task 2 | 删除 intent/multi_intent.py | ~80 行 |
| Task 3 | 删除前端 event-types.ts | ~428 行 |
| Task 4 | 删除 HierarchicalKnowledgeRetriever 死类 | ~180 行 |
| Task 5 | 删除 workflow 核心引擎 | ~400 行 |
| Task 6 | 删除 hierarchical 实验性子系统 | ~1,900 行 |
| Task 7 | 合并重复哈希函数 | 净减 ~40 行 |
| **Phase 1 合计** | | **~3,170 行** |

每个 Task 独立提交，可独立 PR、独立 review、独立合并。

---

## Phase 2: 合并重复实现（中等风险）

本阶段合并功能重叠的并行实现。每个 Task 需要更仔细的测试覆盖。

---

### Task 8: 合并 Intent 双规则分析器

**Files:**
- Modify: `src/nini/intent/service.py`（融入 Trie 优化 + profile_booster）
- Delete: `src/nini/intent/optimized.py`（758 行）
- Delete: `src/nini/intent/profile_booster.py`（合并进 service.py）
- Delete: `src/nini/intent/subtypes.py`（合并进 service.py）
- Modify: `src/nini/intent/__init__.py`（移除 optimized 导出）
- Modify: `src/nini/agent/runner.py`（移除 optimized_intent_analyzer 引用）
- Modify: `src/nini/agent/components/context_builder.py`（移除 optimized_intent_analyzer 引用）
- Modify: `src/nini/config.py`（`intent_strategy` 字段添加废弃注释，保留字段定义）

**核心问题：** `IntentAnalyzer`（service.py）和 `OptimizedIntentAnalyzer`（optimized.py）包含约 600 行重复代码（同义词表、正则、停用词、分析方法）。`OptimizedIntentAnalyzer` 多了 Trie 索引和 profile_boost，但缺少 skill 处理方法，导致 runner.py 绕过策略选择器直接用 `default_intent_analyzer`。

**策略：** 将 Trie 优化和 profile_boost 能力融入 `IntentAnalyzer`（service.py），使其成为唯一的规则分析器。删除 `OptimizedIntentAnalyzer`。

**向后兼容处理：** `intent_strategy` 字段（`config.py:296`）在用户的 `.env` 中可能存在配置。删除策略选择分支时，需在代码中处理非默认值的情况（打印 warning，而不是静默忽略）。

- [ ] **Step 1: 在 service.py 中引入 TrieNode 和构建倒排索引**

读取 `src/nini/intent/optimized.py`，找到 `TrieNode` 类（约 20 行）和 `_build_inverted_index()` 方法（约 30 行）。将它们复制到 `src/nini/intent/service.py` 中。同时将 `optimized.py` 中多出的同义词条目合并到 service.py 的 `_SYNONYM_MAP` 中。

- [ ] **Step 2: 在 IntentAnalyzer 中添加 Trie 搜索能力**

在 `IntentAnalyzer.__init__` 中构建倒排索引，在 `_match_capabilities()` 中先尝试 Trie 搜索，降级到线性扫描。

- [ ] **Step 3: 在 IntentAnalyzer 中整合 profile_boost**

读取 `src/nini/intent/profile_booster.py`，将 `apply_boost()` 函数移入 service.py，在匹配结果后应用。

- [ ] **Step 4: 在 IntentAnalyzer 中整合 subtypes**

读取 `src/nini/intent/subtypes.py`，将 `get_difference_subtype()` 移入 service.py。

- [ ] **Step 5: 更新 runner.py——添加废弃警告并统一使用 default_intent_analyzer**

读取 `src/nini/agent/runner.py`，找到 `_get_intent_analyzer` 函数（约 145-155 行），修改为：

```python
def _get_intent_analyzer(settings: Any) -> IntentAnalyzer:
    """返回意图分析器实例。

    intent_strategy 配置已废弃，IntentAnalyzer 现已内置 Trie 优化。
    """
    strategy = getattr(settings, "intent_strategy", "optimized_rules")
    if strategy not in ("optimized_rules", "rules"):
        import logging
        logging.getLogger(__name__).warning(
            "intent_strategy=%r 已废弃，当前统一使用 IntentAnalyzer（含 Trie 优化）。"
            "请从 .env 中移除此配置。",
            strategy,
        )
    return default_intent_analyzer
```

删除 `from nini.intent import default_intent_analyzer, optimized_intent_analyzer` 中的 `optimized_intent_analyzer`。

- [ ] **Step 6: 更新 context_builder.py**

读取 `src/nini/agent/components/context_builder.py`，找到约 67-69 行的策略选择代码，同样替换为直接返回 `default_intent_analyzer`，删除 `optimized_intent_analyzer` 导入。

- [ ] **Step 7: 更新 intent/__init__.py**

移除 `OptimizedIntentAnalyzer`、`optimized_intent_analyzer`、`profile_booster`、`subtypes` 的导出。

- [ ] **Step 8: 删除合并完成的文件**

```bash
rm src/nini/intent/optimized.py
rm src/nini/intent/profile_booster.py
rm src/nini/intent/subtypes.py
```

- [ ] **Step 9: 运行测试 + 类型检查**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/intent/ src/nini/agent/runner.py src/nini/agent/components/context_builder.py
```

Expected: 全部通过

- [ ] **Step 10: 提交**

```bash
git add src/nini/intent/ src/nini/agent/runner.py src/nini/agent/components/context_builder.py
git commit -m "refactor(intent): 合并双规则分析器为单一 IntentAnalyzer，融入 Trie 优化和 profile_boost"
```

**预计削减：~600 行**

---

### Task 9: 合并 Memory 双重长期存储

**Files:**
- Create: `scripts/migrate_long_term_memory.py`（一次性迁移脚本）
- Modify: `src/nini/memory/memory_store.py`（融入 LongTermMemoryStore 的必要能力）
- Delete: `src/nini/memory/long_term_memory.py`（763 行）
- Modify: `src/nini/memory/scientific_provider.py`（统一写入路径）
- Modify: `src/nini/agent/runner.py`（移除 `consolidate_session_memories` 调用）

**核心问题：** `MemoryStore`（SQLite facts 表）和 `LongTermMemoryStore`（JSONL entries.jsonl）功能高度重叠。同一条数据在 `on_session_end` 中被双写。去重算法完全相同。

**策略：** 以 `MemoryStore`（SQLite）为唯一长期存储。但 `entries.jsonl` 是用户数据，删除前必须提供迁移路径，将已有 JSONL 数据写入 SQLite。

**数据迁移必须在代码删除前完成。**

- [ ] **Step 1: 确认 LongTermMemoryStore 向量搜索是否实际启用**

```bash
grep -r "VectorKnowledgeStore\|sentence.transformer\|vector_store" \
  src/nini/memory/long_term_memory.py
```

如果向量搜索依赖外部库（sentence-transformers）且默认关闭，则此能力可以直接丢弃，无需迁移到 SQLite。

- [ ] **Step 2: 确认 LongTermMemoryStore 外部调用者完整列表**

```bash
grep -r "long_term_memory\|LongTermMemoryStore\|get_long_term_memory_store\|consolidate_session_memories" \
  src/ --include="*.py" | grep -v "long_term_memory.py" | grep -v "test"
```

记录所有调用位置，逐一处理。

- [ ] **Step 3: 编写迁移脚本 `scripts/migrate_long_term_memory.py`**

```python
#!/usr/bin/env python3
"""将 entries.jsonl 中的历史长期记忆迁移到 SQLite MemoryStore。

用法:
    python scripts/migrate_long_term_memory.py [--data-dir data/sessions]

迁移逻辑：
- 扫描 data/sessions/*/entries.jsonl
- 每条 LongTermMemoryEntry 转为 MemoryStore 的 fact 记录
- 按 memory_id 去重（已迁移的条目跳过）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nini.memory.memory_store import MemoryStore


async def migrate(data_dir: Path) -> int:
    """返回迁移条目数。"""
    store = MemoryStore()
    await store.initialize()
    migrated = 0

    for entries_file in data_dir.glob("*/entries.jsonl"):
        session_id = entries_file.parent.name
        for line in entries_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            # 按 memory_id 去重
            if store.get_fact(entry.get("memory_id", "")):
                continue
            store.add_fact(
                session_id=session_id,
                fact_id=entry.get("memory_id", ""),
                content=entry.get("content", ""),
                source=entry.get("source", "long_term_memory"),
                tags=entry.get("tags", []),
                metadata={
                    "score": entry.get("score", 0.0),
                    "memory_type": entry.get("memory_type", "unknown"),
                    "migrated_from": "entries.jsonl",
                },
            )
            migrated += 1

    print(f"迁移完成：{migrated} 条记录写入 SQLite。")
    return migrated


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/sessions", type=Path)
    args = parser.parse_args()
    asyncio.run(migrate(args.data_dir))
```

**注意：** `store.add_fact` 和 `store.get_fact` 的实际 API 需要在读取 `memory_store.py` 后确认，并相应调整脚本中的调用方式。

- [ ] **Step 4: 验证迁移脚本可正常运行**

```bash
python scripts/migrate_long_term_memory.py --data-dir data/sessions
```

Expected: 打印迁移条目数，无报错。若 `data/sessions/` 为空则打印 "迁移完成：0 条记录"。

- [ ] **Step 5: 将 on_session_end 中的双写改为单写**

读取 `src/nini/memory/scientific_provider.py`，找到 `on_session_end` 中向 `LongTermMemoryStore` 写入的代码，删除该写入路径，保留 `MemoryStore` 的写入路径。

- [ ] **Step 6: 清理 runner.py 中的 consolidate_session_memories 调用**

读取 `src/nini/agent/runner.py`，删除 `consolidate_session_memories` 的调用代码（约 285-298 行范围）。

- [ ] **Step 7: 删除 long_term_memory.py**

```bash
rm src/nini/memory/long_term_memory.py
```

- [ ] **Step 8: 清理全局单例和 __init__.py 导出**

移除 `get_long_term_memory_store()`、`initialize_long_term_memory()`、`LongTermMemoryStore` 等所有相关导入和导出。

- [ ] **Step 9: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

Expected: 全部通过

- [ ] **Step 10: 提交**

```bash
git add scripts/migrate_long_term_memory.py \
        src/nini/memory/ \
        src/nini/agent/runner.py
git commit -m "refactor(memory): 统一长期存储到 SQLite MemoryStore，移除重复的 LongTermMemoryStore"
```

**预计削减：~800 行**

---

### Task 10: 提取 runner.py 中两处内联的 ask_user_question 审批流

**Files:**
- Modify: `src/nini/agent/runner.py`（提取 2 处内联流为独立方法）

**核心问题澄清：**
`runner.py` 中共有 4 处 ask_user_question 审批流，但其中 2 处已经是独立方法：
- `_request_tool_approval()`（3752 行）—— 已提取，无需改动
- `_request_sandbox_import_approval()`（3944 行）—— 已提取，无需改动

仍需提取的 2 处内联流：
1. **普通 ask_user_question 处理**（约 1876-1963 行）：LLM 主动调用的问答流，含图表偏好检测
2. **确认型兜底**（约 1201-1278 行）：无意图时的确认回退流

这 2 处内联在 `run()` 的 `AsyncGenerator` 中，无法用返回 `list[AgentEvent]` 的同步方法替代——必须提取为 `async def` 方法，在 runner.py 内通过 `async for` 委托。

**方法签名设计：**

```python
async def _handle_ask_user_question_tool(
    self,
    session: Session,
    *,
    tc_id: str,
    func_args: str,
    turn_id: str,
) -> AsyncGenerator[AgentEvent, None]:
    """处理 LLM 主动调用的 ask_user_question 工具。含图表偏好检测。"""
    ...

async def _handle_confirmation_fallback(
    self,
    session: Session,
    *,
    turn_id: str,
    confirmation_payload: dict[str, Any],
) -> AsyncGenerator[AgentEvent, None]:
    """处理无意图时的确认型兜底 ask_user_question。"""
    ...
```

- [ ] **Step 1: 读取普通审批流的完整代码**

读取 `src/nini/agent/runner.py` 1876-1963 行，理解完整逻辑（含 `_detect_chart_preference_from_answers` 调用和 `session.chart_output_preference` 更新）。

- [ ] **Step 2: 提取 `_handle_ask_user_question_tool` 方法**

将 1876-1963 行的逻辑提取到新方法中。注意：原代码直接 `yield` 事件，提取后需要用 `async def _handle_ask_user_question_tool(...): yield event` 的形式，并在 `run()` 的调用点改为：

```python
if func_name == "ask_user_question":
    async for event in self._handle_ask_user_question_tool(
        session, tc_id=tc_id, func_args=func_args, turn_id=turn_id
    ):
        yield event
    continue
```

- [ ] **Step 3: 读取确认型兜底的完整代码**

读取 `src/nini/agent/runner.py` 1201-1278 行，理解完整逻辑。

- [ ] **Step 4: 提取 `_handle_confirmation_fallback` 方法**

将 1201-1278 行的逻辑提取到新方法中。调用点改为：

```python
if confirmation_payload and self._ask_user_question_handler is not None:
    async for event in self._handle_confirmation_fallback(
        session, turn_id=turn_id, confirmation_payload=confirmation_payload
    ):
        yield event
```

- [ ] **Step 5: 运行测试 + 类型检查**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/agent/runner.py
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/nini/agent/runner.py
git commit -m "refactor(agent): 提取 ask_user_question 两处内联处理为独立方法，削减 run() 体积"
```

**预计削减：不减少行数，但 run() 减少约 170 行内联代码**

---

### Task 11: 前端事件处理器去重

**Files:**
- Create: `web/src/store/event-handler-utils.ts`（提取共享函数）
- Modify: `web/src/store/event-handler.ts`（使用共享函数）
- Modify: `web/src/store/event-handler-extended.ts`（使用共享函数）
- Modify: `web/src/store/message-normalizer.ts`（移除重复的 `cloneMessages`）

**核心问题（仅保留已确认的重复）：**
1. `isActiveSessionEvent` 在 `event-handler.ts` 和 `event-handler-extended.ts` 各定义一次
2. `cloneMessages` 在 `message-normalizer.ts` 和 `session-ui-cache.ts` 各定义一次

**明确不做的修改：**
- `hypothesis-slice.ts` 和 `hypothesis-event-handler.ts` **不内联、不删除**。经确认，Hypothesis 系统在 `HypothesisTracker.tsx`、`App.tsx`、`store.ts`、`types.ts` 中均有使用，是活跃模块。

- [ ] **Step 1: 确认 isActiveSessionEvent 的两处定义**

```bash
grep -n "isActiveSessionEvent" web/src/store/event-handler.ts \
  web/src/store/event-handler-extended.ts
```

确认两处定义完全一致（或有微小差异需要合并）。

- [ ] **Step 2: 确认 cloneMessages 的两处定义**

```bash
grep -n "cloneMessages" web/src/store/message-normalizer.ts \
  web/src/store/session-ui-cache.ts
```

确认哪个版本更完整，以该版本为准。

- [ ] **Step 3: 创建 `web/src/store/event-handler-utils.ts`**

```typescript
/**
 * 事件处理器共享工具函数。
 */
import { useStore } from "../store";

/** 判断事件是否属于当前活跃会话。 */
export function isActiveSessionEvent(sessionId: string): boolean {
  return useStore.getState().currentSessionId === sessionId;
}
```

（根据实际代码调整实现内容。）

- [ ] **Step 4: 更新 event-handler.ts 和 event-handler-extended.ts**

在两个文件中：
- 删除本地 `isActiveSessionEvent` 定义
- 添加 `import { isActiveSessionEvent } from "./event-handler-utils"`

- [ ] **Step 5: 统一 cloneMessages**

确认 `session-ui-cache.ts` 中的 `cloneMessages` 已被导出。在 `message-normalizer.ts` 中删除本地定义，改为从 `session-ui-cache.ts` 导入。

- [ ] **Step 6: 运行前端测试 + 构建检查**

```bash
cd web && npm test -- --run && npm run build
```

Expected: 测试通过，构建成功

- [ ] **Step 7: 提交**

```bash
git add web/src/store/event-handler-utils.ts \
        web/src/store/event-handler.ts \
        web/src/store/event-handler-extended.ts \
        web/src/store/message-normalizer.ts
git commit -m "refactor(web): 提取事件处理器共享函数，消除 isActiveSessionEvent 和 cloneMessages 重复定义"
```

**预计削减：~80 行**

---

## Phase 3: 拆分 God Object（高风险，需充分测试）

本阶段拆分过度膨胀的类和文件。每个 Task 需要仔细设计接口边界，确保行为不变。

---

### Task 12: 拆分 `AgentRunner.run()` 巨型方法

**Files:**
- Modify: `src/nini/agent/runner.py`（4,404 行，run() 约 2,355 行 → 拆为 10 个阶段方法）

**核心问题：** `run()` 方法约 2,355 行，承担 25+ 个独立职责：7 个嵌套闭包、94 个 yield、28 个 continue。

**拆分策略：** 将 `run()` 按执行阶段拆分为 10 个独立的 `AsyncGenerator` 方法。主 `run()` 成为约 80 行的调度器，依次委托每个阶段。

**阶段方法签名设计（根据 runner.py 结构推导）：**

```python
# 主调度器（目标约 80 行）
async def run(self, user_message: str, *, session: Session, turn_id: str, ...) -> AsyncGenerator[AgentEvent, None]:
    async for event in self._run_phase_init(session, turn_id=turn_id, user_message=user_message, ...):
        yield event
    async for event in self._run_phase_context_build(session, turn_id=turn_id, ...):
        yield event
    async for event in self._run_react_loop(session, turn_id=turn_id, ...):
        yield event
    async for event in self._run_phase_finalize(session, turn_id=turn_id, ...):
        yield event

# 阶段方法（各约 200-400 行）
async def _run_phase_init(...) -> AsyncGenerator[AgentEvent, None]: ...
async def _run_phase_context_build(...) -> AsyncGenerator[AgentEvent, None]: ...
async def _run_react_loop(...) -> AsyncGenerator[AgentEvent, None]: ...        # 主循环
async def _run_phase_tool_dispatch(...) -> AsyncGenerator[AgentEvent, None]: ...   # 从 react_loop 中提取
async def _run_phase_finalize(...) -> AsyncGenerator[AgentEvent, None]: ...
```

**实施注意：** 由于 `run()` 是 `AsyncGenerator` 且含大量闭包和共享状态，拆分时需要仔细处理：
- 闭包中引用的外部变量必须作为参数传入阶段方法，或提升为实例变量
- 每个 `continue` 语句的控制流必须在拆分后保持等价语义

**详细实施步骤（执行前必须先读取 runner.py 全部方法边界）：**

- [ ] **Step 1: 阅读并记录 run() 的完整结构**

读取 `src/nini/agent/runner.py` 中 `run()` 方法的起止行，以及其中每个主要代码块的行号范围：

```bash
grep -n "# ──\|async for\|^        if \|^        while\|^        try:" \
  src/nini/agent/runner.py | head -80
```

绘制每个逻辑块（初始化、上下文构建、ReAct 主循环、工具分发、收尾）的行号边界。

- [ ] **Step 2: 识别共享状态变量**

列出 `run()` 中所有被多个阶段共用的局部变量（如 `iteration`、`pending_followup_prompt`、`tool_call_results` 等）。这些变量在拆分后需要作为参数传入或封装为数据类。

建议：创建一个 `RunState` dataclass 持有跨阶段状态：

```python
from dataclasses import dataclass, field

@dataclass
class RunState:
    """run() 跨阶段共享状态。"""
    iteration: int = 0
    pending_followup_prompt: str | None = None
    # 根据实际变量补充
```

- [ ] **Step 3: 提取初始化阶段 `_run_phase_init`**

将 `run()` 开头的初始化代码（session 准备、context 注入、第一个 yield）移入 `_run_phase_init`，返回 `RunState` 初始值。

- [ ] **Step 4: 提取 ReAct 主循环 `_run_react_loop`**

将 `while True:` 主循环移入 `_run_react_loop`，接收 `RunState` 作为参数（可变引用）。

- [ ] **Step 5: 从主循环中提取工具分发 `_run_phase_tool_dispatch`**

将工具分发（`if func_name == "ask_user_question": ...`、`if func_name in ("task_write", ...):`、正常工具执行）移入独立方法，主循环变为简洁的调度器。

- [ ] **Step 6: 提取收尾阶段 `_run_phase_finalize`**

将收尾代码（memory 写入、session 状态更新等）移入 `_run_phase_finalize`。

- [ ] **Step 7: 重写 `run()` 为调度器**

确认 `run()` 变为约 80 行纯调度代码，无业务逻辑。

- [ ] **Step 8: 运行全量测试 + 类型检查**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/agent/runner.py
```

Expected: 全部通过

- [ ] **Step 9: 提交**

```bash
git add src/nini/agent/runner.py
git commit -m "refactor(agent): 拆分 AgentRunner.run() 2355 行为 5 个阶段方法，主方法缩至约 80 行"
```

**预计削减：不减少总行数，但 run() 从约 2,355 行降至约 80 行调度器。**

---

### Task 13: 简化 `event_builders.py`（提取辅助函数，保留显式接口）

**Files:**
- Modify: `src/nini/agent/event_builders.py`（1,216 行 → 约 900 行）
- Create: `src/nini/agent/_event_builder_helpers.py`（内部辅助函数，约 100 行）

**核心问题：** 41 个 `build_xxx_event` 函数中，大多数函数体有相似的结构（Pydantic 构造 → dump → 加 metadata → 返回），但部分函数含有特殊逻辑（如 `build_analysis_plan_event` 中的 `AnalysisPlanStep` 对象构建）。

**策略：保留 41 个显式函数，提取公共辅助函数削减函数体内的重复代码。**

**不采用注册表/元编程方案**，原因：注册表会破坏 IDE 的跳转、补全和类型推断，对一个频繁被阅读和调用的模块来说，这是不可接受的工程成本。

**辅助函数设计：**

```python
# src/nini/agent/_event_builder_helpers.py
"""event_builders 内部辅助函数，不对外暴露。"""
from __future__ import annotations
from typing import Any
from nini.agent.events import AgentEvent, EventType
from pydantic import BaseModel


def _make_event(
    event_type: EventType,
    data_model: BaseModel,
    turn_id: str | None,
    seq: int | None,
    extra: dict[str, Any] | None = None,
) -> AgentEvent:
    """通用事件构建辅助：Pydantic 模型 → AgentEvent。"""
    data = data_model.model_dump()
    if extra:
        data.update(extra)
    metadata: dict[str, Any] = {}
    if seq is not None:
        metadata["seq"] = seq
    return AgentEvent(
        type=event_type,
        data=data,
        turn_id=turn_id,
        metadata=metadata if metadata else None,
    )
```

通过 `_make_event` 辅助函数，典型的函数体从 10-15 行压缩为 5-8 行，但函数签名、文档字符串、类型检查完全保留。

- [ ] **Step 1: 分析 41 个函数的分类**

读取 `src/nini/agent/event_builders.py`，将 41 个函数分为两类：
- **标准型**：函数体 = Pydantic 构造 → dump → metadata → 返回（可使用 `_make_event`）
- **特殊型**：含有额外预处理逻辑（如 `build_analysis_plan_event`），需保留现有结构

```bash
grep -n "^def build_" src/nini/agent/event_builders.py
```

对每个函数读取函数体，标记类型。

- [ ] **Step 2: 创建 `src/nini/agent/_event_builder_helpers.py`**

按上述设计创建文件，实现 `_make_event` 辅助函数。

- [ ] **Step 3: 逐一替换标准型函数体**

对每个"标准型"函数，将函数体替换为调用 `_make_event`。例如：

原始（约 12 行）：
```python
def build_text_event(text: str, *, turn_id: str | None = None, seq: int | None = None, **extra) -> AgentEvent:
    data_obj = TextEventData(text=text)
    data = data_obj.model_dump()
    if extra:
        data.update(extra)
    metadata = {}
    if seq is not None:
        metadata["seq"] = seq
    return AgentEvent(
        type=EventType.TEXT,
        data=data,
        turn_id=turn_id,
        metadata=metadata if metadata else None,
    )
```

替换后（约 6 行）：
```python
def build_text_event(text: str, *, turn_id: str | None = None, seq: int | None = None, **extra) -> AgentEvent:
    """构造 TEXT 事件。"""
    return _make_event(EventType.TEXT, TextEventData(text=text), turn_id, seq, extra or None)
```

- [ ] **Step 4: 保留特殊型函数不变**

对含有预处理逻辑的函数（如 `build_analysis_plan_event`），不做修改或仅做最小调整。

- [ ] **Step 5: 运行测试**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/agent/event_builders.py
```

Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/nini/agent/_event_builder_helpers.py src/nini/agent/event_builders.py
git commit -m "refactor(agent): 提取 event_builders 共享辅助函数，削减函数体重复代码约 300 行"
```

**预计削减：~300 行（保留显式接口，不牺牲 IDE 支持）**

---

### Task 14: 拆分 `config_manager.py`

**Files:**
- Modify: `src/nini/config_manager.py`（1,081 行 → 拆为 4 个模块）
- Create: `src/nini/config_parts/model_pricing.py`
- Create: `src/nini/config_parts/trial_manager.py`
- Create: `src/nini/config_parts/purpose_routes.py`

**策略：** 按职责拆分：
- `config_manager.py` → 仅保留配置加载/合并核心逻辑（约 300 行）
- `config_parts/model_pricing.py` → 定价与用量追踪（约 250 行）
- `config_parts/trial_manager.py` → 试用模式逻辑（约 250 行）
- `config_parts/purpose_routes.py` → 用途路由逻辑（约 150 行）

**注意：** 此 Task 不减少行数，目标是让每个文件职责单一。

- [ ] **Step 1: 读取 config_manager.py 完整结构**

```bash
grep -n "^class \|^def \|^async def " src/nini/config_manager.py
```

识别每个类和函数的归属职责。

- [ ] **Step 2: 创建 config_parts/ 目录**

```bash
mkdir -p src/nini/config_parts
touch src/nini/config_parts/__init__.py
```

- [ ] **Step 3: 迁移 model_pricing 相关代码**

读取 config_manager.py，将定价计算和用量追踪相关的类/函数移入 `src/nini/config_parts/model_pricing.py`。在 config_manager.py 中添加 re-export，保持对外接口不变。

- [ ] **Step 4: 迁移 trial_manager 相关代码**

同样方式迁移试用模式逻辑。

- [ ] **Step 5: 迁移 purpose_routes 相关代码**

同样方式迁移用途路由逻辑。

- [ ] **Step 6: 运行测试 + 类型检查**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/config_manager.py src/nini/config_parts/
```

- [ ] **Step 7: 提交**

```bash
git add src/nini/config_manager.py src/nini/config_parts/
git commit -m "refactor(config): 拆分 config_manager.py 为 4 个单职责模块"
```

---

### Task 15: 拆分 `compression.py`

**Files:**
- Modify: `src/nini/memory/compression.py`（1,338 行 → 拆为 3 个模块）
- Create: `src/nini/memory/analysis_memory.py`
- Create: `src/nini/memory/memory_extraction.py`

**策略：**
- `compression.py` → 仅保留会话压缩逻辑（约 300 行）
- `analysis_memory.py` → AnalysisMemory 数据模型 + CRUD（约 600 行）
- `memory_extraction.py` → 工具提取、统计提取等辅助函数（约 300 行）

- [ ] **Step 1: 读取 compression.py 完整结构**

```bash
grep -n "^class \|^def \|^async def " src/nini/memory/compression.py
```

识别每个类和函数的归属职责。

- [ ] **Step 2: 迁移 AnalysisMemory 相关代码到 analysis_memory.py**

读取 compression.py，将 `AnalysisMemory` 类及其 CRUD 方法移入新文件。在 compression.py 中添加 re-export。

- [ ] **Step 3: 迁移提取辅助函数到 memory_extraction.py**

将工具提取、统计提取等辅助函数移入新文件。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/ -q --timeout=60
```

- [ ] **Step 5: 提交**

```bash
git add src/nini/memory/compression.py \
        src/nini/memory/analysis_memory.py \
        src/nini/memory/memory_extraction.py
git commit -m "refactor(memory): 拆分 compression.py 为 3 个单职责模块"
```

---

### Task 16: 简化 Memory Provider 抽象

**Files:**
- Delete: `src/nini/memory/provider.py`（60 行 ABC）
- Modify: `src/nini/memory/manager.py`（186 行编排 → 直接方法调用）
- Modify: `src/nini/memory/scientific_provider.py`（取消 ABC 继承，独立类）

**策略：** 既然只有 1 个 Provider 实现，去掉抽象层。将 `MemoryManager` 简化为直接持有 `ScientificMemoryProvider` 实例，而不是 `list[MemoryProvider]`。保留 `MemoryManager` 作为 Facade（对外 API 不变），但内部不再有 provider 注册/遍历机制。

- [ ] **Step 1: 确认只有 1 个 Provider 实现**

```bash
grep -r "class.*MemoryProvider\|MemoryProvider\)" src/ --include="*.py"
```

Expected: 仅 `provider.py` 中有 `MemoryProvider` ABC，`scientific_provider.py` 中有唯一实现。

- [ ] **Step 2: 修改 scientific_provider.py**

读取 `src/nini/memory/scientific_provider.py`，删除 `(MemoryProvider)` 继承，删除相关 import，保留所有方法实现不变。

- [ ] **Step 3: 修改 manager.py**

读取 `src/nini/memory/manager.py`，将 `list[MemoryProvider]` 改为直接持有 `ScientificMemoryProvider` 实例。删除 provider 注册/遍历机制，改为直接调用。对外接口方法签名不变。

- [ ] **Step 4: 删除 provider.py**

```bash
rm src/nini/memory/provider.py
```

- [ ] **Step 5: 清理 __init__.py**

移除 `MemoryProvider` 的导出（如有）。

- [ ] **Step 6: 运行测试 + 类型检查**

```bash
pytest tests/ -q --timeout=60
mypy src/nini/memory/
```

- [ ] **Step 7: 提交**

```bash
git add src/nini/memory/provider.py \
        src/nini/memory/manager.py \
        src/nini/memory/scientific_provider.py \
        src/nini/memory/__init__.py
git commit -m "refactor(memory): 移除单实现的 MemoryProvider ABC，Manager 直接持有 ScientificMemoryProvider"
```

**预计削减：~100 行**

---

## Phase 2-3 总预估

| Phase | 任务数 | 预计削减行数 | 风险 |
|-------|--------|------------|------|
| Phase 2 | 4 个 Task | ~1,780 行（Task 11 修正后） | 中等 |
| Phase 3 | 5 个 Task | ~400 行 + 结构改善 | 较高 |
| **合计** | 9 个 Task | ~2,180 行 + 结构改善 | — |

---

## 全局执行策略

### 执行顺序

```
Phase 1（Task 1-7）→ 全量测试通过 → 合并到 main
     ↓
Phase 2（Task 8-11）→ 每个 Task 独立分支 + 测试 → 独立 PR
     ↓
Phase 3（Task 12-16）→ 每个 Task 独立分支 + 全量测试 → 独立 PR + 详细 review
```

### 每个 Task 的验证清单

- [ ] `pytest tests/ -q --timeout=60` 全部通过
- [ ] `black --check src tests` 格式检查通过
- [ ] `mypy src/nini/` 类型检查通过（修改的模块）
- [ ] 前端：`cd web && npm test -- --run && npm run build`（涉及前端时）
- [ ] `git diff --stat` 确认变更范围合理

### 分支命名规范

```
chore/dead-code-cleanup-phase1       # Phase 1 整体
refactor/merge-intent-analyzers      # Task 8
refactor/merge-memory-stores         # Task 9
refactor/extract-approval-handlers   # Task 10
refactor/frontend-event-handler-dedup # Task 11
refactor/split-agent-runner          # Task 12
refactor/event-builders-helpers      # Task 13
```

---

## 自检清单

### 1. Spec 覆盖度

本计划覆盖了分析报告中识别的所有过度设计问题：

| 分析报告问题 | 对应 Task |
|-------------|----------|
| capabilities/implementations/ 死代码 | Task 1 |
| intent/multi_intent.py 死代码 | Task 2 |
| 前端 event-types.ts 死代码 | Task 3 |
| HierarchicalKnowledgeRetriever 死类 | Task 4 |
| workflow 核心引擎死代码 | Task 5 |
| hierarchical 子系统未启用 | Task 6 |
| _compute_file_hashes 三处重复 | Task 7 |
| Intent 双分析器重复 | Task 8 |
| Memory 双存储重复 | Task 9 |
| ask_user_question 审批流重复 | Task 10 |
| 前端事件处理器重复 | Task 11 |
| runner.py God Object | Task 12 |
| event_builders 机械重复 | Task 13 |
| config_manager.py 职责过载 | Task 14 |
| compression.py 职责膨胀 | Task 15 |
| Memory Provider 过度抽象 | Task 16 |

### 2. 修正说明

- `memory/knowledge.py`（分析报告称死代码）：实际被 `session.py:26` 导入并使用，**不是死代码**。已从计划中移除。
- `models/event_schemas.py`（分析报告称死代码）：实际被 `event_builders.py` 和 `contract_runner.py` 大量导入，**不是死代码**。已从计划中移除。
- `hypothesis-slice.ts` 和 `hypothesis-event-handler.ts`（原计划建议内联）：经确认在 `HypothesisTracker.tsx`、`App.tsx`、`store.ts`、`types.ts` 中均有使用，**是活跃模块**。Task 11 已移除内联步骤。
- `_request_tool_approval` 和 `_request_sandbox_import_approval`（原计划称"4 处内联"）：这 2 处已是独立方法，无需处理。Task 10 仅处理剩余 2 处真正内联的流。
- **Task 13 元编程方案**：原计划使用注册表替代 41 个显式函数，但注册表会破坏 IDE 跳转和类型推断。修正为提取辅助函数、保留显式接口的方案。

### 3. 未覆盖的低优先级项

以下问题优先级较低，未纳入本次计划：
- `ResearchProfileManager` 同步化包装（低优先级，功能正常）
- `intent_strategy` 字段在 config.py 中的最终删除（依赖 Task 8 的废弃警告期完成后）
