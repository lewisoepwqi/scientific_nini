# Scientific Nini 意图分类与路由体系优化规划

> **版本**：v2.0 | **更新时间**：2026-03-15
> **基于实际代码核查修订**，修正了 v1.x 中的路径错误、Agent 数量错误及遗漏的关键 Bug。

---

## 一、当前体系现状（基于代码实测）

### 1.1 架构总览

```
用户输入
    ↓
OptimizedIntentAnalyzer（src/nini/intent/optimized.py）
    ├── Trie 树前缀匹配（~3ms）
    ├── 同义词倒排索引（_SYNONYM_MAP，硬编码）
    ├── 关键词评分（capability name / display_name / description）
    ├── _CASUAL_RE：闲聊识别（短确认、问候、感谢）
    ├── _OUT_OF_SCOPE_RE：基础 OOS 检测（已存在）
    └── _COMMAND_RE：工具指令检测
    ↓
QueryType 分类 → CASUAL_CHAT / DOMAIN_TASK / KNOWLEDGE_QA / COMMAND
    ↓
CapabilityRegistry（src/nini/capabilities/）→ capability_candidates（Top 5）
    ↓
TaskRouter（src/nini/agent/router.py）— 双轨制路由
    ├── 规则路由（_BUILTIN_RULES 关键词集合，< 5ms）
    └── LLM 兜底路由（置信度 < 0.7 时触发，~500ms）
    ↓
Specialist Agent（src/nini/agent/prompts/agents/builtin/）
    或 ToolRegistry 直接调用
    ↓
HarnessRunner（src/nini/harness/runner.py）— 完成校验与护栏
```

### 1.2 当前 Capability 清单（8 个，intent/optimized.py）

| Name | Display Name | Executable | 主要同义词（_SYNONYM_MAP） |
|------|-------------|------------|---------------------------|
| `difference_analysis` | 差异分析 | Yes | 差异、t检验、anova、方差分析、对比 |
| `correlation_analysis` | 相关性分析 | Yes | 相关、pearson、spearman、关联 |
| `regression_analysis` | 回归分析 | Yes | 回归、预测、建模、拟合 |
| `data_exploration` | 数据探索 | No | 探索、描述性统计、分布、EDA |
| `data_cleaning` | 数据清洗 | Yes | 清洗、预处理、填充、去重 |
| `visualization` | 可视化 | Yes | 可视化、画图、箱线图、散点图 |
| `report_generation` | 报告生成 | N/A | 报告、汇总、总结、PDF |
| `article_draft` | 科研文章初稿 | No | 论文、初稿、学术论文 |

### 1.3 Specialist Agent 清单（9 个，实际代码）

> **路径**：`src/nini/agent/prompts/agents/builtin/`（v1.x 文档路径 `.nini/agents/` 有误）

| Agent ID | YAML 文件 | TaskRouter 规则覆盖 | LLM Prompt 覆盖 |
|----------|-----------|-------------------|-----------------|
| `literature_search` | ✅ | ✅ | ✅ |
| `literature_reading` | ✅ | ✅ | ✅ |
| `data_cleaner` | ✅ | ✅ | ✅ |
| `statistician` | ✅ | ✅ | ✅ |
| `viz_designer` | ✅ | ✅ | ✅ |
| `writing_assistant` | ✅ | ✅ | ✅ |
| `citation_manager` | ✅ | ❌ **未接入** | ❌ **未接入** |
| `research_planner` | ✅ | ❌ **未接入** | ❌ **未接入** |
| `review_assistant` | ✅ | ❌ **未接入** | ❌ **未接入** |

**结论**：3 个 Agent 已有 YAML 定义，但 TaskRouter 的规则路由和 LLM Prompt 均未包含它们，实际上无法被路由触发。

### 1.4 OOS 检测现状（已存在，部分覆盖）

`optimized.py` 中 `_OUT_OF_SCOPE_RE` 已覆盖：

```python
# 现有覆盖：联网检索、文献数据库直连、新闻资讯类查询
_OUT_OF_SCOPE_RE = re.compile(
    r"检索|搜索|搜一下|查一下|查找|查询最新|最新进展|最新消息|最新动态|"
    r"最新研究|发展近况|联网|上网|爬虫|爬取|爬网|browse|google|pubmed|"
    r"scholar|知网|web\s*search|internet|新闻|资讯|热点|头条",
    re.IGNORECASE,
)
```

**现有 OOS 未覆盖**：非科研类任意请求（订机票、播放音乐、天气查询等）——当前这类请求会 fallback 到 `CASUAL_CHAT`，由 LLM 自由处理，存在无意义执行风险。

---

## 二、已知 Bug 与优先修复项

> 这是对 v1.x 规划文档的重要补充，以下问题比意图分类优化更紧迫。

### BUG-001：Harness 完成校验 `promised_artifact` 误判（P0）

**位置**：`src/nini/harness/runner.py:385`

**现象**：AI 介绍自身能力（如"我可以制作**图表**与**报告**"）时，会被 Harness 误判为"承诺了产物但未生成"，触发第二轮 AgentRunner，导致**同一条用户消息收到两次完整回答**。

**根因**：
```python
# 当前：过于宽泛，单独出现"图表"/"报告"即判定为承诺产物
promised_artifact = bool(re.search(r"(图表|报告|产物|已生成|已导出|附件)", final_text))
```

**修复方向**：改为匹配"完成语义 + 产物词"的组合模式：
```python
# 修复后：仅匹配真实承诺/已交付的表达
promised_artifact = bool(re.search(
    r"(已生成|已导出|已完成|以下是|如下|这里是|请查看).{0,15}(图表|报告|产物|附件)"
    r"|(图表|报告|产物|附件).{0,8}(已生成|已导出|已完成|已保存)",
    final_text,
))
```

**影响**：修复后，任何含"图表"/"报告"的介绍性/能力描述类回答不再触发二次执行。

**附加优化**：当 `query_type == CASUAL_CHAT`（闲聊/问候类）时，`artifact_generated` 校验项应直接跳过：
```python
# 闲聊场景无需产物校验
is_casual = getattr(session, "_last_query_type", None) == "CASUAL_CHAT"
promised_artifact = (not is_casual) and bool(re.search(..., final_text))
```

### BUG-002：3 个 Agent 无法被路由触发（P1）

**位置**：`src/nini/agent/router.py`

**现象**：`citation_manager`、`research_planner`、`review_assistant` 已有 YAML 定义，但路由层完全不知道它们的存在，用户的相关请求无法路由到这些 Agent。

**修复**：在 `_BUILTIN_RULES` 和 `_LLM_ROUTING_PROMPT` 中补充这 3 个 Agent 的关键词和描述。

---

## 三、差距分析

### 3.1 维度评估

| 维度 | 当前状态 | 理想状态 | 差距等级 | 优先级 |
|------|---------|---------|---------|--------|
| **Harness 完成校验误判** | `promised_artifact` 过于宽泛 | 精确匹配完成语义 | 🔴 严重 | **P0** |
| **Agent 路由覆盖** | 9 个中只有 6 个被路由 | 全部 9 个可路由 | 🔴 严重 | **P1** |
| **同义词表扩展性** | Python 代码硬编码 | YAML 配置化，无需改代码 | 🟡 中等 | P1 |
| **意图粒度** | 8 个顶层 Capability | 细粒度子意图（检验类型、图表类型等） | 🟡 中等 | P2 |
| **多意图检测** | 未支持（复合查询只识别单一意图） | 支持顺序/并行多意图 | 🟡 中等 | P2 |
| **OOS 检测** | 部分覆盖（联网/检索类） | 完整拒绝非科研请求 | 🟡 中等 | P2 |
| **上下文感知** | 仅 RAG 检索，未影响意图判断 | 对话历史 + 用户画像增强 | 🟢 低 | P3 |
| **评估体系** | 无意图分类准确率监控 | F1/OOS Recall/澄清率监控 | 🟢 低 | P3 |

### 3.2 科研场景覆盖矩阵

| 科研场景 | 所需能力 | 当前覆盖 | 缺口说明 |
|---------|---------|---------|---------|
| **文献检索** | 关键词搜索、作者筛选、引用追踪 | ⚠️ 部分 | Agent 已存在，但路由后实际工具依赖外部 API |
| **文献精读** | 摘要提取、方法论解析、文献对比 | ⚠️ 部分 | Agent 已存在，缺 PDF 解析工具 |
| **数据清洗分析** | 缺失值、异常检测、变量衍生 | ✅ 基本覆盖 | Tool + Agent 双路径均可 |
| **统计检验** | 假设检验、效应量、多重比较 | ✅ 基本覆盖 | 子检验类型意图粒度不足 |
| **图表生成** | 图表推荐、期刊格式、多图排版 | ✅ 基本覆盖 | 样式定制能力有限 |
| **引用管理** | 格式转换、重复检测 | ⚠️ Agent 存在但未路由 | citation_manager 未接入路由 |
| **论文撰写** | 章节生成、语法检查、引用 | ⚠️ 部分 | writing_assistant 已接入，但能力边界不清 |
| **同行评审** | 意见整理、回复生成 | ⚠️ Agent 存在但未路由 | review_assistant 未接入路由 |
| **研究规划** | 研究设计、任务拆解 | ⚠️ Agent 存在但未路由 | research_planner 未接入路由 |
| **假设生成** | 基于文献/数据提出研究假设 | ❌ 无 | 全部缺失 |
| **实验设计** | 样本量计算、随机化方案 | ❌ 无 | 全部缺失 |

---

## 四、分阶段优化计划

### Phase 0 — 修复阻断性 Bug（≤ 3 天，立即执行）

**目标**：消除影响当前用户体验的关键缺陷。

#### 任务列表

**[P0-1] 修复 `promised_artifact` 完成校验误判**
- 文件：`src/nini/harness/runner.py:385`
- 改动：收紧正则，要求"完成语义词 + 产物词"组合匹配
- 测试：发送"你是谁"/"你能做什么"，确认不触发二次回答

**[P0-2] 补全 3 个遗漏 Agent 的路由规则**
- 文件：`src/nini/agent/router.py`
- 改动：在 `_BUILTIN_RULES` 中添加 `citation_manager`、`research_planner`、`review_assistant` 的关键词规则；更新 `_LLM_ROUTING_PROMPT` 和 `_LLM_BATCH_ROUTING_PROMPT` 中的 Agent 列表
- 参考规则：
  ```python
  (frozenset({"引用", "参考文献", "引用格式", "文献管理", "bibliography"}), "citation_manager"),
  (frozenset({"研究规划", "研究设计", "实验设计", "研究方案", "研究思路"}), "research_planner"),
  (frozenset({"审稿", "同行评审", "评审意见", "回复审稿", "修改意见"}), "review_assistant"),
  ```

**验证标准**：
- `pytest tests/ -q` 全部通过
- 手动测试：发送"你是谁"不触发双回答
- 手动测试：发送"帮我整理审稿意见"能路由到 `review_assistant`

---

### Phase 1 — 路由基础建设（1～2 周）

**目标**：让现有 9 个 Agent 的能力真正可达，同义词表可维护。

#### [P1-1] 同义词表 YAML 化

将 `optimized.py` 中 `_SYNONYM_MAP` 硬编码迁移到配置文件，支持无代码扩展。

```yaml
# config/intent_synonyms.yaml（新增文件）
difference_analysis:
  - "差异"
  - "显著性"
  - "t检验"
  - "anova"
  - "方差分析"
  - "对比分析"
  - "均值比较"

correlation_analysis:
  - "相关"
  - "相关性"
  - "pearson"
  - "spearman"
  - "变量关系"

# ... 其他 capability
```

- 加载逻辑：`OptimizedIntentAnalyzer.__init__` 中读取 YAML，fallback 到内置 dict
- 优先级：运行时 YAML > 代码内置（支持用户覆盖）

#### [P1-2] 补充文献/写作/评审类同义词

现有 `_SYNONYM_MAP` 对文献、写作、引用类词汇覆盖很少，补充到 `article_draft` 和新增条目：

```yaml
article_draft:
  - "论文"
  - "初稿"
  - "学术论文"
  - "方法部分"
  - "引言"
  - "讨论章节"
  - "写摘要"

citation_management:   # 新增 capability（映射到 citation_manager Agent）
  - "引用格式"
  - "参考文献"
  - "文献引用"
  - "bibliography"
  - "APA格式"
  - "引用管理"

peer_review:           # 新增 capability（映射到 review_assistant Agent）
  - "审稿意见"
  - "同行评审"
  - "回复审稿人"
  - "修改建议"
  - "评审回复"

research_planning:     # 新增 capability（映射到 research_planner Agent）
  - "研究方案"
  - "研究设计"
  - "实验设计"
  - "研究规划"
  - "研究思路"
```

#### [P1-3] 完善 OOS 非科研关键词黑名单

现有 `_OUT_OF_SCOPE_RE` 覆盖联网检索类，补充通用非科研场景的快速拒绝：

```python
# 在 _OUT_OF_SCOPE_RE 中补充（或新增独立黑名单）
_GENERAL_OOS_KEYWORDS = [
    "订机票", "订酒店", "订餐", "外卖", "天气", "股票", "彩票",
    "播放音乐", "讲笑话", "翻译", "导航", "地图", "购物",
]
```

- **实现**：`is_quick_oos(query)` 函数，在 `IntentAnalyzer.analyze()` 中优先检查
- **行为**：命中时设置 `QueryType.OUT_OF_SCOPE`，LLM 给出引导性回复而不执行工具

**Phase 1 完成标准**：
- [ ] 同义词表从 YAML 加载，新增同义词无需改代码
- [ ] 9 个 Agent 全部可通过意图触发
- [ ] OOS 非科研请求返回引导性回复，不触发工具调用

---

### Phase 2 — 意图精度提升（3～4 周）

**目标**：支持多意图检测，提升细粒度场景识别精度。前提是 Phase 0/1 已完成。

#### [P2-1] 多意图检测（轻量规则优先）

不引入 Embedding，先用规则实现 80% 场景：

```python
# src/nini/intent/multi_intent.py（新增）
_SEQUENTIAL_MARKERS = re.compile(r"先.{0,10}(然后|再|接着|之后)|首先.{0,10}(其次|然后)")
_PARALLEL_MARKERS = re.compile(r"同时|顺便|另外|还有|以及")
_SENTENCE_SPLIT = re.compile(r"[，。；！？,.;!?]+")

def detect_multi_intent(query: str) -> list[str] | None:
    """返回子意图列表（顺序执行），无多意图时返回 None。"""
    # 检测顺序标记
    if _SEQUENTIAL_MARKERS.search(query):
        parts = _SENTENCE_SPLIT.split(query)
        return [p.strip() for p in parts if len(p.strip()) > 3]
    return None
```

- 集成点：`TaskRouter.route()` 调用前检测多意图，多意图时转发到 `route_batch()`
- 测试用例："先分析相关性然后画散点图"→ 两个子任务顺序执行

#### [P2-2] 细粒度子检验类型意图

`difference_analysis` 当前无法区分具体检验类型，增加子意图识别：

```python
# 在 _SYNONYM_MAP 的 difference_analysis 中区分子类型（打标签）
_SUBTYPE_MAP = {
    "difference_analysis": {
        "paired_t_test": ["配对t检验", "重复测量", "前后对比"],
        "independent_t_test": ["独立样本", "两组比较", "独立t检验"],
        "one_way_anova": ["单因素方差", "one-way anova", "多组比较"],
        "mann_whitney": ["mann-whitney", "非参数两样本", "秩和检验"],
        "kruskal_wallis": ["kruskal", "非参数多组"],
    }
}
```

- 子类型信息注入 `tool_hints`，引导 LLM 调用正确的统计工具

#### [P2-3] 澄清策略优化

当前澄清触发条件（相对差距 < 25%）会在"帮我分析数据"类模糊输入时频繁追问，影响体验。

优化策略：
1. 澄清前先检查是否已有加载的数据集——有数据时倾向于 `data_exploration` 而非追问
2. 澄清选项限制在 3 个以内，并附带简短示例
3. 记录用户历史选择，相同模糊输入优先复用上次选择

**Phase 2 完成标准**：
- [ ] "先...然后..."类复合查询能拆分为多个子任务
- [ ] 差异分析能在 `tool_hints` 中体现具体检验类型
- [ ] 澄清触发率下降（目标 < 15%）

---

### Phase 3 — 上下文感知与监控（后续迭代）

**目标**：利用用户画像和对话历史提升意图预测精准度，建立可度量的评估体系。

> **前置条件**：Phase 2 完成且已有足够真实用户查询样本。

#### [P3-1] 用户研究画像集成

- 复用 `models/user_profile.py` 的 `ResearchProfile`
- 意图评分 Boosting：用户研究领域为生物医学时，"生存分析"意图 +2 分
- 历史意图序列：上一轮执行了差异分析，当前轮"画个图"优先路由到 `viz_designer`

#### [P3-2] 基础评估数据集

构建最小可用评估集：
- 50 条标准域内查询（覆盖所有 Capability）
- 20 条模糊/多意图查询
- 20 条 OOS 查询
- 目标：意图 Top-1 准确率 ≥ 0.88，OOS 召回率 ≥ 0.85

#### [P3-3] 生产监控

- 记录低置信度查询（< 0.5）到独立日志
- 统计每日：意图分布、澄清触发率、OOS 命中率
- 为后续引入 Embedding 检索提供数据支撑

---

## 五、实施路线图

```
Week 1       Week 2       Week 3-4     Week 5-8     后续
────────     ────────     ────────     ────────     ────────
Phase 0      Phase 1      Phase 1      Phase 2      Phase 3
Bug 修复     基础建设     完善阶段     精度提升     监控体系

[P0-1]       [P1-1]       [P1-3]       [P2-1]       [P3-1]
harness      同义词        OOS          多意图        用户画像
误判修复     YAML 化       扩展         检测

[P0-2]       [P1-2]       ────         [P2-2]       [P3-2]
3 Agent      补充文献/               子检验         评估数据集
路由补全     写作/评审               粒度

                                       [P2-3]       [P3-3]
                                       澄清策略      生产监控
                                       优化
```

**总预估工作量**：Phase 0（3 天）+ Phase 1（1～2 周）+ Phase 2（3～4 周）+ Phase 3（持续迭代）

---

## 六、关键文件索引

| 文件 | 作用 | 本规划涉及改动 |
|------|------|--------------|
| `src/nini/harness/runner.py` | 完成校验与护栏 | **P0-1** `promised_artifact` 修复 |
| `src/nini/agent/router.py` | Agent 路由规则 | **P0-2** 补充 3 个 Agent；P1 |
| `src/nini/intent/optimized.py` | 意图分析核心 | P1 同义词 YAML 化；P1-3 OOS 扩展 |
| `src/nini/capabilities/registry.py` | Capability 注册 | P1-2 新增 3 个 Capability |
| `src/nini/agent/prompts/agents/builtin/` | 9 个 Agent YAML | 无改动（已完备） |
| `config/intent_synonyms.yaml` | **新建** 同义词配置 | P1-1 |
| `src/nini/intent/multi_intent.py` | **新建** 多意图检测 | P2-1 |

---

## 附录：v1.x → v2.0 主要修正

| 修正项 | v1.x 内容 | v2.0 修正 | 原因 |
|--------|-----------|----------|------|
| Agent 路径 | `.nini/agents/` | `src/nini/agent/prompts/agents/builtin/` | 代码实测 |
| Agent 数量 | 6 个 | 9 个（新增 citation_manager、research_planner、review_assistant） | 代码实测 |
| OOS 检测现状 | "无" | "已存在基础 `_OUT_OF_SCOPE_RE`" | `optimized.py` 有此实现 |
| 最高优先级 | GAP-001 意图覆盖 | BUG-001 harness 误判（P0） | 影响当前用户体验 |
| Embedding 方案时机 | Phase 2 立即引入 | 推迟到 Phase 3 数据积累后评估 | 避免过早引入 ~100MB 依赖 |
| 3 个遗漏 Agent | 未提及 | 作为 P0-2 立即修复 | 路由规则未覆盖 |
