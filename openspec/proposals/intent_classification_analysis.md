# Scientific Nini 意图分类体系分析与提升报告

## 一、执行摘要

**现状评估**：Scientific Nini 当前采用基于规则的意图分析体系（Trie树+倒排索引），定义了8个核心 Capability，覆盖基础科研数据分析场景，但在意图粒度、多意图处理和科研场景覆盖上存在明显局限。

**最大差距**：意图分类体系缺乏科研领域专项适配，未覆盖文献检索、假设生成、实验设计等核心科研 workflow；同时缺少多意图检测、细粒度子意图和系统化的评估机制。

**首要建议**：分三阶段升级：Phase 1 补全科研场景意图覆盖（快速价值），Phase 2 引入混合分类架构提升精度，Phase 3 建立评估体系与上下文增强。

---

## 二、当前意图体系全景（Agent-1）

### 2.1 意图分类机制现状

```yaml
current_intent_system:
  classification_mechanism:
    method: "基于规则的意图分析（Trie树 + 倒排索引 + 同义词映射）"
    trigger_point: "用户输入后，调用LLM前进行预分析"
    classification_granularity: "粗粒度场景级（Capability级别）"

  implementation_details:
    analyzer_classes:
      - "IntentAnalyzer: 规则版意图分析器"
      - "OptimizedIntentAnalyzer: 优化版（Trie树+倒排索引，O(1)~O(n)复杂度）"
      - "EnhancedIntentAnalyzer: 增强版（语义匹配，可选依赖）"

    matching_strategies:
      - "Trie树前缀匹配: 基于Capability名称的Trie树"
      - "同义词倒排索引: _SYNONYM_MAP同义词映射表"
      - "关键词提取匹配: 基于display_name/description的关键词提取"

    scoring_weights:
      capability_name_match: 10.0
      display_name_match: 8.0
      synonym_match: 6.0（每个同义词2.0，上限6.0）
      keyword_match: 4.0（每个关键词1.5，上限4.0）
      tool_hint_match: 2.0（每个工具0.5，上限2.0）
      executable_bonus: 1.0
```

### 2.2 已定义 Capability 清单

| Name | Display Name | Executable | Description | Required Tools |
|------|-------------|------------|-------------|----------------|
| `difference_analysis` | 差异分析 | Yes | 比较两组或多组数据的差异，自动选择合适的统计检验方法 | t_test, mann_whitney, anova, kruskal_wallis |
| `correlation_analysis` | 相关性分析 | Yes | 探索变量之间的相关关系，计算相关系数矩阵 | correlation |
| `regression_analysis` | 回归分析 | Yes | 建立变量间的回归模型，进行预测和解释 | regression |
| `data_exploration` | 数据探索 | No | 全面了解数据特征：分布、缺失值、异常值等 | preview_data, data_summary, data_quality |
| `data_cleaning` | 数据清洗 | Yes | 处理缺失值、异常值，提升数据质量 | clean_data, data_quality |
| `visualization` | 可视化 | Yes | 创建各类图表展示数据特征和分析结果 | create_chart, export_chart |
| `report_generation` | 报告生成 | N/A | 生成完整的分析报告，包含统计结果和可视化 | generate_report, export_report |
| `article_draft` | 科研文章初稿 | No | 根据数据分析结果，自动编排多个分析工具逐章生成结构完整的科研论文初稿 | organize_workspace, generate_report |

**总计：8个 Capability，其中 5个可执行，3个仅引导**

### 2.2b Specialist Agent 层（6个内置Agent）

Agent-1 调研发现存在 **6个 Specialist Agent**，通过 YAML 配置定义，用于复杂任务路由：

| Agent ID | 名称 | 用途 | 触发关键词 | 对应Capability |
|----------|------|------|------------|----------------|
| `literature_search` | 文献检索Agent | 文献检索、论文搜索 | 文献、论文、引用、期刊、搜索 | KNOWLEDGE/LIT_SEARCH |
| `literature_reading` | 文献精读Agent | 文献精读、批注理解 | 精读、批注、阅读、理解 | KNOWLEDGE/LIT_READING |
| `statistician` | 统计分析专家 | 统计检验、建模解释 | 统计、检验、p值、回归、方差 | DATA/ANALYZE_* |
| `viz_designer` | 可视化设计师 | 数据可视化、图表制作 | 图表、可视化、画图、箱线图 | DATA/VIZ_* |
| `data_cleaner` | 数据清洗专家 | 数据清洗、异常处理 | 清洗、缺失值、异常值 | DATA/DATA_CLEAN |
| `writing_assistant` | 写作助手 | 科研写作、论文润色 | 写作、润色、摘要、引言 | OUTPUT/PAPER_WRITE |

**三层架构关系**：
```
用户输入
    ↓
IntentAnalyzer (意图识别) → Capability Candidates
    ↓
TaskRouter.route() (双轨制路由)
    ├── 规则路由 (confidence >= 0.7) → Specialist Agent / Capability
    └── LLM兜底路由 → 复杂意图解析
    ↓
ToolRegistry.invoke() (原子工具执行)
```

### 2.3 路由逻辑与兜底策略

```yaml
routing_logic:
  single_intent_handling:
    flow: |
      用户输入 → IntentAnalyzer.analyze() → capability_candidates(Top 5)
      → 如果最高分 >= 5.0: 标记为 DOMAIN_TASK
      → 构建 tool_hints → 注入 System Prompt → LLM 生成 Tool Calls

  clarification_policy:
    trigger_condition: "len(candidates) >= 2 且 (top1.score - top2.score) / top1.score < 0.25 且 top1.score >= 5.0"
    # 即：相对差距 < 25% 且绝对分数 >= 5.0
    action: "设置 clarification_needed=True，生成二选一追问"
    example: "你更想做 差异分析 还是 相关性分析？"
    code_reference: "src/nini/intent/optimized.py:413-456"

  query_type_classification:
    CASUAL_CHAT: "无候选 且 (匹配 _CASUAL_RE 或 长度<=10)"
    DOMAIN_TASK: "最高分 >= 5.0"
    KNOWLEDGE_QA: "有候选但最高分 < 5.0"
    COMMAND: "匹配 _COMMAND_RE（保存/导出/删除等指令）"

  fallback_strategy:
    no_capability_match: "交给LLM自由处理（query_type=CASUAL_CHAT）"
    no_clarification_options: "返回兜底选项（前3个Capability）"
    circuit_breaker: "工具调用失败链达到阈值时，返回TOOL_CALL_CIRCUIT_BREAKER"
```

### 2.4 当前体系局限性

```yaml
current_weaknesses:
  observed_gaps:
    - "意图粒度粗：仅8个顶层Capability，缺少细粒度子意图"
    - "多意图盲区：未实现多意图检测，复合查询只能识别单一意图"
    - "科研场景缺失：未覆盖假设生成、实验设计等核心科研workflow"
    - "硬编码风险：同义词映射_SYNONYM_MAP和评分权重硬编码"
    - "无OOS检测：缺少超出范围(Out-of-Scope)意图识别机制"
    - "意图与Agent映射不清：Capability、Agent、Tool三层关系未显式定义（现有6个Specialist Agent未整合到意图taxonomy）"

  note_on_existing_agents: |
    现有6个Specialist Agent（literature_search, literature_reading, statistician,
    viz_designer, data_cleaner, writing_assistant）已通过YAML配置存在，
    但 Intent → Agent 的映射关系未显式定义，需要整合到新taxonomy中。

  missing_scenarios:
    - "文献检索：搜索论文、筛选文献、追踪引用"
    - "文献精读：摘要提取、方法论解析、结论质疑"
    - "假设生成：基于文献提出研究假设"
    - "实验设计：样本量计算、对照组设计、随机化方案"
    - "跨文献综合：多篇文献对比、元分析准备"
    - "论文撰写：章节生成、引用格式化、语法检查"
    - "同行评审：评审意见整理、回复信生成"

  context_utilization_limits:
    conversation_history: "仅用于RAG/LTM检索，未直接融入意图判断"
    user_profile: "有user_profile模型，但未在intent分析中使用"
    task_state: "未根据当前任务状态调整意图识别"

  evaluation_gaps:
    - "无意图分类准确率监控"
    - "无 clarifcation 有效性评估"
    - "无用户满意度反馈闭环"
```

---

## 三、行业最佳实践参考（Agent-2）

### 3.1 意图分类技术演进（2024-2025）

```
传统NLU管道                    现代混合架构                    LLM统一理解
─────────────                 ─────────────                  ─────────────
Tokenizer →                   Encoder NLU                    Single LLM Call
Featurizer →        →         (检索Top-K候选)        →       (Intent + Entity
DIETClassifier                +                              + Context)
(Entity Extraction)           LLM最终分类
                              (候选间选择)
```

**关键技术趋势：**
1. **混合架构成为主流**：Encoder NLU 检索候选 + LLM 最终分类（降低错误率）
2. **Function Calling 作为意图映射**：通过强制 tool_choice 实现意图分类
3. **少样本学习**：提供2-3个示例显著提升细粒度意图区分
4. **对比学习**：拉近同类意图嵌入，区分重叠意图（如"取消预订"vs"改期"）

### 3.2 层次化意图分类设计

**三层标准结构（Cognigy/Boost.ai推荐）：**
```
Level 1 (Domain):       Benefits | Loans | Hotel | Research
                              ↓
Level 2 (Topic):     Health Insurance | Mortgage | Lit Review
                              ↓
Level 3 (Intent):  Enroll dental | Check status | Search papers
```

**科研场景参考分类（Ai2 ASTA数据集）：**
- **Information Retrieval**: 找论文、查作者、追踪引用
- **Synthesis/Explanation**: 概念解释、方法论理解
- **Comparison**: 方法对比、结果对比
- **Methodology Inquiry**: 实验设计、统计方法选择
- **Data Extraction**: 提取数据、表格解析
- **Citation Verification**: 验证引用、检查来源

### 3.3 多意图处理最佳实践

**检测方法：**
| 方法 | 适用场景 | 实现方式 |
|------|----------|----------|
| 分隔符标记 | 显式多意图 | 使用"+"连接意图标签（Rasa） |
| 标点分割 | 隐式多意图 | 检测句子分隔符（.?!;）|
| 时序标记 | 顺序执行 | 识别"先...然后..."等时间词 |
| LLM隐式理解 | 复杂复合 | 单轮推理识别多个意图 |

**处理策略：**
- **并行执行**：独立意图同时执行（Multi-Intent）
- **顺序执行**：意图间有依赖（Sub-Intent）
- **用户确认**：歧义时主动询问（Clarification）

### 3.4 评估框架与指标

**核心指标：**
| 指标 | 说明 | 生产阈值 |
|------|------|----------|
| **Macro F1** | 各类别F1平均 | > 0.85 |
| **OOS Recall** | 超出范围识别率 | > 0.90（优先于Precision）|
| **AUROC** | IS vs OOS可分性 | > 0.95 |
| **Clarification Rate** | 需要澄清的比例 | < 15% |

**标准数据集：**
- **CLINC**：150意图类别，含OOS样本（业界标准）
- **MIntRec2.0**：多模态意图识别基准
- **Banking77**：77个银行领域细粒度意图

### 3.5 头部产品设计参考

**Rasa NLU：**
- DIETClassifier 联合意图分类+实体抽取
- 支持层次化意图（feedback+positive）
- 多热编码支持组合意图泛化

**OpenAI Function Calling：**
- 通过 tool_choice="any" 强制意图选择
- JSON Schema 定义可用意图
- 统一处理意图识别+参数提取

---

## 四、差距分析（Agent-3）

### 4.1 维度对比总表

| 维度 | 当前状态 | 行业最佳实践 | 差距等级 | 影响 |
|------|----------|--------------|----------|------|
| **分类方法** | 规则匹配（Trie+倒排） | 混合架构（Encoder+LLM） | 中等 | 精度受限 |
| **意图粒度** | 粗粒度8个Capability | 3层层次结构 | 严重 | 场景覆盖不足 |
| **多意图处理** | 未支持 | 支持Multi/Sub/Hybrid | 严重 | 复合查询失效 |
| **意图覆盖** | 仅数据分析 | 完整科研workflow | 严重 | 核心价值受限 |
| **模糊处理** | 简单分数差阈值 | 置信度+上下文+用户画像 | 中等 | 误识别率高 |
| **OOS检测** | 无 | AUROC>0.95 | 严重 | 误执行风险 |
| **上下文利用** | 仅RAG检索 | 对话历史+用户画像 | 中等 | 个性化不足 |
| **评估机制** | 无 | F1/OOS Recall/CLAR Rate | 严重 | 无法度量改进 |
| **可扩展性** | 硬编码映射 | 动态学习+Embedding | 中等 | 维护成本高 |

### 4.2 科研场景覆盖矩阵

| 科研场景 | 所需子意图 | 当前覆盖 | 缺失 | 优先级 |
|----------|------------|----------|------|--------|
| **文献检索** | 关键词搜索、作者筛选、时间筛选、相关推荐 | ⚠️ 部分 | 有Agent但无意图层映射 | P0 |
| **文献精读** | 摘要提取、方法论解析、结论质疑、文献对比 | ⚠️ 部分 | 有Agent但无意图层映射 | P0 |
| **假设生成** | 基于文献假设、数据驱动假设、假设验证设计 | ❌ 无 | 全部 | P1 |
| **实验设计** | 样本量计算、对照组设计、随机化方案、伦理审查 | ❌ 无 | 全部 | P1 |
| **数据清洗分析** | 缺失值处理、异常检测、格式转换、变量衍生 | ⚠️ 部分 | 有Agent但无意图层映射 | P1 |
| **统计检验** | 检验选择、假设检验、效应量计算、多重比较 | ⚠️ 部分 | 有Agent但无意图层映射 | P2 |
| **图表生成** | 图表推荐、样式调整、多图排版、期刊格式 | ⚠️ 部分 | 有Agent但无意图层映射 | P2 |
| **论文撰写** | 大纲生成、章节撰写、引用管理、语法检查 | ❌ 无 | 全部 | P1 |
| **引用管理** | 引用导入、格式转换、重复检测、库同步 | ❌ 无 | 全部 | P2 |
| **同行评审** | 意见整理、回复生成、修改追踪 | ❌ 无 | 全部 | P2 |
| **研究思路整理** | 概念图生成、逻辑链梳理、Gap识别 | ❌ 无 | 全部 | P1 |
| **跨文献综合** | 元分析准备、证据合成、矛盾识别 | ❌ 无 | 全部 | P2 |

**覆盖率：4/12 场景（33%），主要是数据分析相关场景**

### 4.3 关键差距根因归类

```yaml
critical_gaps:
  GAP-001:
    title: "科研场景意图覆盖严重不足"
    root_cause: "TAXONOMY_INCOMPLETE"
    current_pain: "用户无法进行文献检索、假设生成、实验设计等核心科研活动"
    severity_score: 9
    improvement_effort: "M"
    value_score: 10
    priority_rank: 1

  GAP-002:
    title: "缺少多意图检测能力"
    root_cause: "METHOD_OUTDATED"
    current_pain: "'先帮我分析相关性然后生成图表'类复合查询只能执行单一意图"
    severity_score: 8
    improvement_effort: "M"
    value_score: 8
    priority_rank: 2

  GAP-003:
    title: "无OOS检测机制"
    root_cause: "NO_EVALUATION"
    current_pain: "超出能力范围的查询可能触发错误工具调用"
    severity_score: 8
    improvement_effort: "L"
    value_score: 9
    priority_rank: 3

  GAP-004:
    title: "意图粒度过于粗放的"
    root_cause: "TAXONOMY_INCOMPLETE"
    current_pain: "'差异分析'无法区分配对t检验/独立t检验/ANOVA等具体场景"
    severity_score: 7
    improvement_effort: "M"
    value_score: 7
    priority_rank: 4

  GAP-005:
    title: "上下文利用不充分"
    root_cause: "CONTEXT_BLIND"
    current_pain: "未利用用户研究方向、历史偏好进行意图预测"
    severity_score: 6
    improvement_effort: "H"
    value_score: 6
    priority_rank: 5

  GAP-006:
    title: "评估体系缺失"
    root_cause: "NO_EVALUATION"
    current_pain: "无法度量意图分类准确率，无法持续优化"
    severity_score: 7
    improvement_effort: "M"
    value_score: 8
    priority_rank: 6

  GAP-007:
    title: "硬编码同义词表"
    root_cause: "HARDCODED_FRAGILE"
    current_pain: "新增意图需修改代码，无法动态扩展"
    severity_score: 5
    improvement_effort: "L"
    value_score: 6
    priority_rank: 7
```

---

## 五、提升方案（Agent-4）

### 5.1 新版意图分类体系设计

#### 设计原则
1. **科研场景优先**：以研究者实际 workflow 为核心组织意图
2. **三层层次结构**：Domain → Scenario → Intent，兼顾覆盖与精准
3. **动态可扩展**：支持运行时动态添加意图，无需代码修改
4. **多意图兼容**：支持单一场景内的多意图组合

#### 新版意图分类体系（三级层次 + 与现有Agent映射）

**设计原则更新**：
1. **与现有Agent整合优先**：新意图体系需兼容现有6个Specialist Agent
2. **Capability-Agent解耦**：Intent 映射到 Capability，Capability 再决定调用 Agent 或 Tool
3. **渐进式迁移**：Phase 1 保持现有Agent功能不变，通过映射表接入新体系

```yaml
new_intent_taxonomy:
  version: "2.0"
  design_date: "2025-03-15"
  migration_strategy: "与现有6个Specialist Agent兼容，通过mapping表路由"

  level_1_domains:
    # ========== 领域1：知识获取 ==========
    - domain_id: "KNOWLEDGE"
      domain_name: "知识获取"
      description: "科研文献检索、阅读与知识提取"
      mapped_specialist_agents: ["literature_search", "literature_reading"]

      level_2_scenarios:
        - scenario_id: "LIT_SEARCH"
          scenario_name: "文献检索"
          specialist_agent: "literature_search"  # 映射到现有Agent
          level_3_intents:
            - intent_id: "LIT_SEARCH_KEYWORD"
              description: "按关键词搜索文献"
              examples: ["帮我找关于机器学习的论文", "搜索CRISPR最新研究"]
              confidence_threshold: 0.75

            - intent_id: "LIT_SEARCH_AUTHOR"
              description: "按作者搜索文献"
              examples: ["查找 Geoffrey Hinton 的论文", "某作者的所有文章"]
              confidence_threshold: 0.80

            - intent_id: "LIT_SEARCH_CITATION"
              description: "引用追踪"
              examples: ["这篇文章被谁引用了", "查找引用该论文的文献"]
              confidence_threshold: 0.75

            - intent_id: "LIT_SEARCH_RELATED"
              description: "相关文献推荐"
              examples: ["找类似的研究", "推荐相关论文"]
              confidence_threshold: 0.70

        - scenario_id: "LIT_READING"
          scenario_name: "文献精读"
          level_3_intents:
            - intent_id: "LIT_EXTRACT_ABSTRACT"
              description: "摘要提取与总结"
              examples: ["总结这篇论文的主要发现", "提取核心观点"]
              confidence_threshold: 0.75

            - intent_id: "LIT_PARSE_METHOD"
              description: "方法论解析"
              examples: ["解释实验设计", "这个方法是怎么实现的"]
              confidence_threshold: 0.75

            - intent_id: "LIT_CRITIQUE_CONCLUSION"
              description: "结论质疑与评估"
              examples: ["这个结论可靠吗", "有什么局限性"]
              confidence_threshold: 0.80

            - intent_id: "LIT_COMPARE_PAPERS"
              description: "多文献对比"
              examples: ["比较这两篇论文的方法", "有什么不同"]
              confidence_threshold: 0.75

        - scenario_id: "LIT_SYNTHESIS"
          scenario_name: "知识综合"
          level_3_intents:
            - intent_id: "LIT_IDENTIFY_GAP"
              description: "研究Gap识别"
              examples: ["这个领域还有什么问题没解决", "研究空白有哪些"]
              confidence_threshold: 0.80

            - intent_id: "LIT_GENERATE_HYPOTHESIS"
              description: "假设生成"
              examples: ["基于这些文献提出假设", "我想研究...是否可行"]
              confidence_threshold: 0.85

    # ========== 领域2：研究设计 ==========
    - domain_id: "DESIGN"
      domain_name: "研究设计"
      description: "实验设计、样本规划与方法选择"

      level_2_scenarios:
        - scenario_id: "EXP_DESIGN"
          scenario_name: "实验设计"
          level_3_intents:
            - intent_id: "EXP_CALC_SAMPLE_SIZE"
              description: "样本量计算"
              examples: ["需要多少样本", "计算样本量"]
              confidence_threshold: 0.80

            - intent_id: "EXP_DESIGN_CONTROL"
              description: "对照组设计"
              examples: ["如何设置对照组", "安慰剂设计"]
              confidence_threshold: 0.80

            - intent_id: "EXP_RANDOMIZATION"
              description: "随机化方案"
              examples: ["怎么随机分组", "随机化策略"]
              confidence_threshold: 0.75

        - scenario_id: "METHOD_SELECT"
          scenario_name: "方法选择"
          level_3_intents:
            - intent_id: "METHOD_STATS_ADVICE"
              description: "统计方法建议"
              examples: ["用什么统计方法", "t检验还是ANOVA"]
              confidence_threshold: 0.75

            - intent_id: "METHOD_VALIDITY_CHECK"
              description: "效度检查"
              examples: ["这个设计有什么偏倚风险", "内部效度如何"]
              confidence_threshold: 0.80

    # ========== 领域3：数据处理 ==========
    - domain_id: "DATA"
      domain_name: "数据处理"
      description: "数据清洗、分析与可视化（现有Capability细化）"
      mapped_specialist_agents: ["statistician", "viz_designer", "data_cleaner"]

      level_2_scenarios:
        - scenario_id: "DATA_CLEAN"
          scenario_name: "数据清洗"
          level_3_intents:
            - intent_id: "DATA_HANDLE_MISSING"
              description: "缺失值处理"
              examples: ["处理缺失数据", "缺失值填充"]
              confidence_threshold: 0.70

            - intent_id: "DATA_DETECT_OUTLIER"
              description: "异常值检测"
              examples: ["找出异常值", "检测离群点"]
              confidence_threshold: 0.70

            - intent_id: "DATA_TRANSFORM"
              description: "数据转换"
              examples: ["数据标准化", "对数转换", "变量衍生"]
              confidence_threshold: 0.70

        - scenario_id: "DATA_ANALYZE"
          scenario_name: "数据分析"
          level_3_intents:
            - intent_id: "ANALYZE_DIFFERENCE"
              description: "差异分析"
              sub_types: ["paired_t_test", "independent_t_test", "one_way_anova", "two_way_anova", "mann_whitney", "kruskal_wallis"]
              examples: ["比较两组差异", "t检验", "ANOVA分析"]
              confidence_threshold: 0.75

            - intent_id: "ANALYZE_CORRELATION"
              description: "相关性分析"
              sub_types: ["pearson", "spearman", "kendall", "partial_correlation"]
              examples: ["计算相关系数", "相关性矩阵"]
              confidence_threshold: 0.75

            - intent_id: "ANALYZE_REGRESSION"
              description: "回归分析"
              sub_types: ["linear", "logistic", "multinomial", "polynomial", "stepwise"]
              examples: ["建立回归模型", "预测分析", "逻辑回归"]
              confidence_threshold: 0.75

        - scenario_id: "DATA_VIZ"
          scenario_name: "数据可视化"
          level_3_intents:
            - intent_id: "VIZ_RECOMMEND"
              description: "图表智能推荐"
              examples: ["用什么图表展示", "推荐合适的可视化"]
              confidence_threshold: 0.75

            - intent_id: "VIZ_CREATE"
              description: "创建图表"
              sub_types: ["scatter", "line", "bar", "histogram", "box", "heatmap", "forest"]
              examples: ["画散点图", "生成箱线图", "森林图"]
              confidence_threshold: 0.70

    # ========== 领域4：成果产出 ==========
    - domain_id: "OUTPUT"
      domain_name: "成果产出"
      description: "论文撰写、报告生成与成果分享"
      mapped_specialist_agents: ["writing_assistant"]

      level_2_scenarios:
        - scenario_id: "PAPER_WRITE"
          scenario_name: "论文撰写"
          level_3_intents:
            - intent_id: "PAPER_GENERATE_OUTLINE"
              description: "生成论文大纲"
              examples: ["帮我写论文大纲", "论文结构建议"]
              confidence_threshold: 0.80

            - intent_id: "PAPER_WRITE_SECTION"
              description: "撰写章节"
              sub_sections: ["abstract", "introduction", "methods", "results", "discussion", "conclusion"]
              examples: ["写方法部分", "生成讨论章节"]
              confidence_threshold: 0.75

            - intent_id: "PAPER_CITE_MANAGE"
              description: "引用管理"
              examples: ["插入引用", "格式化参考文献", "检查引用格式"]
              confidence_threshold: 0.70

        - scenario_id: "REPORT_GENERATE"
          scenario_name: "报告生成"
          level_3_intents:
            - intent_id: "REPORT_FULL_ANALYSIS"
              description: "完整分析报告"
              examples: ["生成分析报告", "完整的数据分析总结"]
              confidence_threshold: 0.75

        - scenario_id: "REVIEW_RESPONSE"
          scenario_name: "同行评审"
          level_3_intents:
            - intent_id: "REVIEW_ORGANIZE_COMMENTS"
              description: "评审意见整理"
              examples: ["整理审稿意见", "分类评审建议"]
              confidence_threshold: 0.75

            - intent_id: "REVIEW_GENERATE_RESPONSE"
              description: "回复信生成"
              examples: ["写回复信", "回复审稿人意见"]
              confidence_threshold: 0.80

    # ========== 领域5：通用交互 ==========
    - domain_id: "GENERAL"
      domain_name: "通用交互"
      description: "系统控制、帮助与闲聊"

      level_2_scenarios:
        - scenario_id: "SYSTEM"
          scenario_name: "系统控制"
          level_3_intents:
            - intent_id: "SYS_SAVE"
              description: "保存"
              examples: ["保存结果", "保存会话"]
              confidence_threshold: 0.90

            - intent_id: "SYS_EXPORT"
              description: "导出"
              examples: ["导出数据", "下载报告"]
              confidence_threshold: 0.90

            - intent_id: "SYS_HELP"
              description: "帮助"
              examples: ["怎么用", "帮助"]
              confidence_threshold: 0.85

        - scenario_id: "CHAT"
          scenario_name: "闲聊"
          level_3_intents:
            - intent_id: "CHAT_GREETING"
              description: "问候"
              examples: ["你好", "早上好"]
              confidence_threshold: 0.95

            - intent_id: "CHAT_THANKS"
              description: "感谢"
              examples: ["谢谢", "感谢帮助"]
              confidence_threshold: 0.95

  # OOS Intent
  oos_intent:
    intent_id: "OOS"
    description: "超出能力范围"
    examples: ["帮我订机票", "播放音乐", "讲个笑话"]
    handling: "礼貌拒绝并提供替代建议"
```

**新版统计：5个 Domain，12个 Scenario，约35个 Intent**

#### Intent → Capability → Agent/Tool 映射机制

```yaml
routing_mapping:
  # 三层映射表定义

  intent_to_capability:
    # 意图映射到Capability（用户理解的能力层）
    LIT_SEARCH_KEYWORD:
      primary_capability: "literature_search"
      fallback_capabilities: ["knowledge_qa"]

    ANALYZE_DIFFERENCE:
      primary_capability: "difference_analysis"
      fallback_capabilities: ["data_exploration"]

    DATA_HANDLE_MISSING:
      primary_capability: "data_cleaning"
      requires_dataset: true

  capability_to_handler:
    # Capability映射到处理者（Agent或Tool）
    literature_search:
      handler_type: "specialist_agent"
      handler_id: "literature_search"
      execution_mode: "delegate"  # 委托给Agent执行

    difference_analysis:
      handler_type: "tool_chain"
      tools: ["data_summary", "t_test", "chart_session"]
      execution_mode: "direct"  # 直接调用Tools

    data_cleaning:
      handler_type: "conditional"
      condition: "complexity_check"
      simple_case:
        handler_type: "tool_chain"
        tools: ["clean_data"]
      complex_case:
        handler_type: "specialist_agent"
        handler_id: "data_cleaner"

  specialist_agent_definitions:
    # 现有6个Specialist Agent定义
    literature_search:
      description: "文献检索专家"
      yaml_config: ".nini/agents/literature_search.yaml"
      tools: ["fetch_url", "search_semantic_scholar", "extract_citations"]
      triggers: ["LIT_SEARCH_*"]

    literature_reading:
      description: "文献精读专家"
      yaml_config: ".nini/agents/literature_reading.yaml"
      tools: ["pdf_extract", "highlight_notes", "summarize_section"]
      triggers: ["LIT_READING_*", "LIT_EXTRACT_*"]

    statistician:
      description: "统计分析专家"
      yaml_config: ".nini/agents/statistician.yaml"
      tools: ["t_test", "anova", "regression", "correlation"]
      triggers: ["ANALYZE_*", "METHOD_STATS_*"]

    viz_designer:
      description: "可视化设计师"
      yaml_config: ".nini/agents/viz_designer.yaml"
      tools: ["create_chart", "export_chart", "style_journal"]
      triggers: ["VIZ_*", "DATA_VIZ"]

    data_cleaner:
      description: "数据清洗专家"
      yaml_config: ".nini/agents/data_cleaner.yaml"
      tools: ["clean_data", "detect_outlier", "handle_missing"]
      triggers: ["DATA_CLEAN", "DATA_HANDLE_*", "DATA_DETECT_*"]

    writing_assistant:
      description: "写作助手"
      yaml_config: ".nini/agents/writing_assistant.yaml"
      tools: ["generate_section", "check_grammar", "format_citation"]
      triggers: ["PAPER_WRITE_*", "REVIEW_*"]
```

**路由决策流程**：
```
用户输入
    ↓
IntentAnalyzer → IntentCandidate(s)
    ↓
CapabilityResolver → Capability
    ↓
HandlerRouter
    ├── simple_tool_chain → ToolRegistry.invoke()
    ├── specialist_agent → AgentSpawner.dispatch()
    └── hybrid → Agent + Tool 混合
```

### 5.2 技术方案升级路径

#### 分类架构升级（从规则到混合）

```python
# 当前实现（规则版）
def classify_intent(query) -> IntentAnalysis:
    return optimized_intent_analyzer.analyze(query)

# 目标实现（混合架构）
async def classify_intent_hybrid(query, context) -> IntentAnalysis:
    # Step 1: Embedding 检索 Top-K 候选（快速）
    candidates = await embedding_retriever.search(query, top_k=10)

    # Step 2: 规则引擎快速过滤（保底）
    rule_matches = rule_analyzer.quick_match(query)

    # Step 3: LLM 最终分类（精准）
    if len(candidates) > 1 and needs_llm_resolution(candidates):
        final_intent = await llm_intent_classifier.classify(
            query=query,
            candidates=candidates[:5],
            context=context,
            few_shot_examples=get_few_shot_examples(candidates)
        )
    else:
        final_intent = candidates[0]

    # Step 4: OOS 检测
    if final_intent.confidence < OOS_THRESHOLD:
        final_intent = OOS_INTENT

    return final_intent
```

#### 多意图检测方案

```yaml
multi_intent_solution:
  detection_approach:
    - "标点分割: 检测句子分隔符(.?!;)分割的多个独立查询"
    - "时序标记: 识别'先...然后...'、'首先...接着...'等顺序词"
    - "连接词检测: '同时'、'顺便'、'另外'等并列标记"
    - "LLM隐式: 当上述方法置信度低时，使用LLM判断"

  resolution_strategy:
    parallel: "独立意图并行执行（如：检索文献A和文献B）"
    sequential: "有依赖意图顺序执行（如：先分析再可视化）"
    clarification: "歧义时主动询问用户意图关系"

  prompt_template: |
    # 多意图识别

    用户输入：{user_query}

    请分析该输入包含几个独立意图：
    - 如果是单一意图，直接返回意图类型
    - 如果是多个意图，列出每个子意图及它们之间的关系（并行/顺序/依赖）

    示例：
    输入："帮我分析相关性，然后生成散点图"
    输出：[
      {"intent": "correlation_analysis", "type": "primary"},
      {"intent": "visualization_scatter", "type": "follow_up", "relation": "sequential", "depends_on": 0}
    ]
```

#### OOS 检测方案

```python
# OOS 检测策略
class OOSDetector:
    def __init__(self):
        self.threshold = 0.3  # 置信度阈值
        self.ood_detector = None  # 可选：专用OOD检测模型

    def is_oos(self, query: str, top_candidate: IntentCandidate) -> bool:
        # 策略1: 置信度阈值
        if top_candidate.score < self.threshold:
            return True

        # 策略2: 与第二候选差距过小（歧义）
        if second_candidate and abs(top_candidate.score - second_candidate.score) < 0.05:
            return True

        # 策略3: 关键词黑名单（快速匹配）
        if self._matches_oos_keywords(query):
            return True

        return False

    def get_oos_response(self, query: str) -> str:
        return f"我目前无法处理'{query}'这类请求。我可以帮您：文献检索、数据分析、统计检验、论文撰写等科研相关任务。"
```

#### 上下文增强方案

```yaml
context_enhancement:
  dialogue_history_integration:
    method: "滑动窗口 + 关键信息提取"
    window_size: 5
    extraction_fields:
      - "mentioned_datasets: 用户提到的数据集"
      - "previous_intents: 历史意图序列"
      - "pending_tasks: 未完成/待跟进任务"
      - "user_preferences: 用户表达的偏好"

  user_research_profile:
    fields:
      - "research_field: 研究领域（机器学习/生物医学/社会科学等）"
      - "expertise_level: 专业水平（学生/初级/高级研究者）"
      - "preferred_methods: 偏好方法（频繁使用t检验vs非参数检验）"
      - "common_datasets: 常用数据集"
      - "recent_topics: 近期研究话题"

  intent_boosting:
    description: "根据用户画像调整意图候选分数"
    example: "如果用户research_field='生物医学'，遇到'生存分析'意图时+2分"
```

#### 与现有代码集成点

**关键集成位置**：

```python
# 1. OptimizedIntentAnalyzer.analyze() 增强点
# 文件: src/nini/intent/optimized.py
# 在现有 Trie树+倒排索引基础上，增加 Embedding 检索

class OptimizedIntentAnalyzer:
    def __init__(self):
        self._trie = Trie()  # 现有
        self._inverted_index = InvertedIndex()  # 现有
        self._embedding_retriever = None  # 新增: 延迟加载

    async def analyze(self, user_message, ...):
        # 现有: 规则匹配
        trie_matches = self._trie_match(user_message)

        # 新增: Embedding 检索（异步）
        if self._should_use_embedding(user_message):
            embedding_matches = await self._embedding_retriever.search(
                user_message, top_k=5
            )
            # 融合排序
            candidates = self._merge_candidates(trie_matches, embedding_matches)
        else:
            candidates = trie_matches

        # 新增: OOS 检测
        if self._is_oos(candidates):
            return IntentAnalysis(is_oos=True)

        return IntentAnalysis(candidates=candidates)

# 2. TaskRouter.route() 多意图支持
# 文件: src/nini/agent/router.py

class TaskRouter:
    async def route(self, intent: str, context: dict) -> RoutingDecision:
        # 新增: 多意图检测
        if self._is_multi_intent(intent):
            sub_intents = self._parse_multi_intent(intent)
            return await self._route_batch(sub_intents, context)

        # 现有: 双轨制路由
        rule_result = self._rule_route(intent)
        if rule_result.confidence >= 0.7:
            return rule_result
        return await self._llm_route(intent, context)

# 3. 与 knowledge/ 模块复用
# 复用现有的向量存储和检索基础设施

class IntentEmbeddingRetriever:
    def __init__(self):
        # 复用 knowledge/ 的向量存储
        self._vector_store = get_knowledge_vector_store()
        # 使用轻量级本地模型（无需额外部署）
        self._encoder = SentenceTransformer('all-MiniLM-L6-v2')

    async def search(self, query: str, top_k: int = 5):
        query_embedding = self._encoder.encode(query)
        # 复用 knowledge/ 的检索接口
        return await self._vector_store.similarity_search(
            embedding=query_embedding,
            filter={"type": "intent"},
            top_k=top_k
        )
```

**复用分析**：
| 现有模块 | 可复用部分 | 新增需求 |
|----------|------------|----------|
| `knowledge/vector_store.py` | 向量存储、相似度检索 | 意图类型过滤 |
| `agent/model_resolver.py` | LLM 调用接口 | intent 专用 purpose |
| `capabilities/registry.py` | Capability 注册机制 | 意图-Capability 映射 |
| `memory/session.py` | 对话历史存储 | 意图历史追踪字段 |

#### 评估框架

```yaml
evaluation_framework:
  test_set_construction:
    sources:
      - "真实用户查询日志"
      - "合成边界案例（相似意图对）"
      - "对抗样本（意图接近的困难案例）"
      - "OOS样本（超出范围查询）"

    categories:
      - "in_scope_perfect: 标准域内查询"
      - "in_scope_ambiguous: 模糊域内查询"
      - "multi_intent: 多意图查询"
      - "oos_clear: 明显OOS查询"
      - "oos_edge: 边界OOS查询"

  key_metrics:
    - name: "Intent Accuracy"
      description: "顶级意图准确率"
      target: ">= 0.90"

    - name: "Intent Top-3 Accuracy"
      description: "正确答案在Top3内比例"
      target: ">= 0.95"

    - name: "OOS Recall"
      description: "OOS检测召回率"
      target: ">= 0.90"
      priority: "高"

    - name: "Clarification Rate"
      description: "需要澄清的查询比例"
      target: "<= 15%"

    - name: "Clarification Success"
      description: "澄清后正确识别率"
      target: ">= 0.85"

    - name: "Multi-Intent Detection Rate"
      description: "多意图检测率"
      target: ">= 0.80"

  monitoring_design:
    real_time:
      - "低置信度查询记录（<0.5）"
      - "澄清触发率监控"
      - "OOS查询类型统计"

    daily_report:
      - "意图分布变化"
      - "新出现的未覆盖查询模式"
      - "用户满意度反馈（澄清是否被接受）"
```

### 5.3 分阶段实施计划

```yaml
implementation_roadmap:

  phase_1:
    title: "Phase 1 — 补全意图覆盖与现有Agent整合（基础建设）"
    duration: "4-5周"
    focus: "整合现有6个Specialist Agent，补全科研场景意图，建立可扩展taxonomy"
    deliverables:
      - "整合6个现有Specialist Agent到新意图体系"
      - "新增15-20个科研专项意图（文献/写作/实验设计）"
      - "每个意图的示例话术库（5-10个示例）"
      - "同义词映射表YAML配置化"
      - "Intent-Agent-Capability映射表"
    effort: "M"
    value: "高"
    tasks:
      - "整合 literature_search/literature_reading Agent到LIT_SEARCH意图"
      - "整合 statistician/viz_designer/data_cleaner Agent到DATA领域意图"
      - "整合 writing_assistant Agent到OUTPUT领域意图"
      - "新增 EXP_DESIGN 领域（实验设计场景）"
      - "将硬编码同义词表改为YAML配置"
    risks:
      - "需要与现有Agent YAML配置保持兼容"
      - "Intent与Agent的映射关系需仔细设计"

  phase_2:
    title: "Phase 2 — 混合分类架构与多意图支持（质量提升）"
    duration: "6-8周"
    focus: "引入Embedding检索，实现多意图检测和OOS拒绝"
    deliverables:
      - "混合意图分类器（复用knowledge/向量存储）"
      - "多意图检测模块（标点+时序+LLM）"
      - "OOS检测模块（置信度+关键词+Embedding距离）"
      - "评估数据集（200+标注样本）"
    effort: "H"
    value: "高"
    tasks:
      - "评估 knowledge/ 向量存储复用可行性"
      - "集成轻量级Embedding模型（all-MiniLM-L6-v2，本地运行）"
      - "实现多意图检测（TaskRouter.route_batch增强）"
      - "实现OOS检测逻辑（三策略融合）"
      - "构建评估数据集并建立benchmark"
    risks:
      - "Embedding模型增加内存占用（~100MB）"
      - "需要评估推理延迟影响（目标<100ms）"

  phase_3:
    title: "Phase 3 — 上下文感知与生产监控（体验优化）"
    duration: "3-4周"
    focus: "对话历史增强、用户画像、持续评估体系"
    deliverables:
      - "用户研究画像系统（复用ResearchProfile）"
      - "对话历史意图增强"
      - "生产环境意图监控（准确率/澄清率/OOS率）"
      - "低置信度样本自动收集机制"
    effort: "M"
    value: "中"
    tasks:
      - "扩展ResearchProfile支持意图偏好"
      - "实现历史意图序列对当前意图的boosting"
      - "构建意图分类准确率监控仪表板"
      - "实现自动化A/B测试框架"
```
```

### 5.4 关键提示词模板草稿

#### 意图分类主提示词

```yaml
prompt_main_intent_classification: |
  # 科研助手意图分类

  ## 你的任务
  分析用户输入，从候选意图中选择最匹配的一个或多个意图。

  ## 当前对话上下文
  {conversation_context}

  ## 用户画像
  {user_profile}

  ## 候选意图（按Embedding相似度排序）
  {candidate_intents}

  ## 用户输入
  "{user_query}"

  ## 输出格式
  请输出JSON格式：
  ```json
  {
    "primary_intent": "主要意图ID",
    "confidence": 0.95,
    "reasoning": "选择理由（简短）",
    "secondary_intents": ["次要意图ID"],
    "is_multi_intent": false,
    "is_oos": false,
    "missing_info": ["如需澄清，列出缺失信息"]
  }
  ```

  ## 示例

  用户："帮我找关于深度学习的论文，要最近两年的"
  输出：
  ```json
  {
    "primary_intent": "LIT_SEARCH_KEYWORD",
    "confidence": 0.92,
    "reasoning": "明确的关键词搜索+时间筛选",
    "secondary_intents": [],
    "is_multi_intent": false,
    "is_oos": false,
    "missing_info": []
  }
  ```

  用户："分析一下相关性然后画个图"
  输出：
  ```json
  {
    "primary_intent": "ANALYZE_CORRELATION",
    "confidence": 0.88,
    "reasoning": "复合意图：分析+可视化",
    "secondary_intents": ["VIZ_CREATE"],
    "is_multi_intent": true,
    "is_oos": false,
    "missing_info": []
  }
  ```
```

#### 多意图处理提示词

```yaml
prompt_multi_intent_resolution: |
  # 多意图解析

  用户输入包含多个意图，请解析它们之间的关系。

  用户输入："{user_query}"

  已识别意图：
  {identified_intents}

  请判断：
  1. 这些意图是并行执行（相互独立）还是顺序执行（有依赖）？
  2. 如果是顺序执行，依赖关系是什么？
  3. 是否需要用户确认执行顺序？

  输出JSON格式：
  ```json
  {
    "execution_mode": "parallel|sequential|needs_clarification",
    "execution_plan": [
      {"intent": "意图ID", "step": 1, "depends_on": null},
      {"intent": "意图ID", "step": 2, "depends_on": 1}
    ],
    "clarification_question": "如需确认，列出问题"
  }
  ```
```

#### 意图模糊追问提示词

```yaml
prompt_clarification: |
  # 意图澄清

  用户输入"{user_query}"存在歧义，多个意图候选分数接近。

  候选意图：
  {ambiguous_intents}

  请生成一个自然的追问，帮助用户明确意图。

  要求：
  1. 追问应简洁友好
  2. 提供2-3个具体选项
  3. 解释每个选项的区别

  输出格式：
  ```json
  {
    "clarification_question": "追问文本",
    "options": [
      {"label": "选项标签", "description": "详细说明", "intent_id": "对应意图"}
    ]
  }
  ```

  示例：
  歧义输入："帮我分析数据"
  输出：
  ```json
  {
    "clarification_question": "您想进行哪种数据分析？",
    "options": [
      {"label": "差异分析", "description": "比较两组数据的统计差异（如实验组vs对照组）", "intent_id": "ANALYZE_DIFFERENCE"},
      {"label": "相关性分析", "description": "探索变量间的相关关系", "intent_id": "ANALYZE_CORRELATION"},
      {"label": "数据探索", "description": "全面了解数据特征、分布和质量", "intent_id": "DATA_EXPLORATION"}
    ]
  }
  ```
```

#### OOS识别与引导提示词

```yaml
prompt_oos_handling: |
  # 超出范围(OOS)处理

  用户输入"{user_query}"不在系统能力范围内。

  系统支持的能力：
  {supported_capabilities}

  请：
  1. 礼貌地说明无法处理该请求
  2. 解释系统能做什么（与用户需求最接近的）
  3. 提供替代建议

  输出格式：
  ```json
  {
    "is_oos": true,
    "response": "礼貌的回复文本",
    "closest_capability": "最接近的能力ID",
    "suggestions": ["替代建议1", "替代建议2"]
  }
  ```

  示例：
  用户："帮我订一张去北京的机票"
  输出：
  ```json
  {
    "is_oos": true,
    "response": "我是一个科研数据分析助手，暂时无法帮您预订机票。",
    "closest_capability": null,
    "suggestions": [
      "我可以帮您搜索与北京相关的研究论文",
      "如果您有旅行相关的数据需要分析，我很乐意协助"
    ]
  }
  ```
```

---

## 六、快速启动建议（Top 3 立即可做）

### 1. 立即扩展同义词表（1天）
将硬编码的 `_SYNONYM_MAP` 改为 YAML 配置文件，支持动态扩展。

```yaml
# config/intent_synonyms.yaml
difference_analysis:
  - "差异分析"
  - "t检验"
  - "anova"
  - "比较两组"
  - "显著性检验"

correlation_analysis:
  - "相关性"
  - "相关系数"
  - "pearson"
  - "spearman"
  - "变量关系"
```

### 2. 快速补全文献检索意图（2-3天）
优先实现最缺失的 `LIT_SEARCH_KEYWORD`、`LIT_SEARCH_AUTHOR` 两个意图，绑定到现有 FetchURL 或新增文献检索工具。

### 3. 添加简单的 OOS 检测（1天）
基于置信度阈值和关键词黑名单，实现基础 OOS 拒绝逻辑。

```python
OOS_KEYWORDS = ["订机票", "订酒店", "播放音乐", "讲笑话", "天气", "股票"]

def is_quick_oos(query: str) -> bool:
    return any(kw in query for kw in OOS_KEYWORDS)
```

---

## 附录：修正说明（v1.1）

本次修正基于 Agent-1（项目解析）和 Agent-2（行业调研）的详细反馈：

### 主要修正内容

| 修正项 | 原报告 | 修正后 | 原因 |
|--------|--------|--------|------|
| **Specialist Agent层** | 完全遗漏 | 补充6个现有Agent及其映射 | Agent-1明确发现6个YAML配置的Agent |
| **澄清策略参数** | 绝对差距 <= 1.0 | 相对差距 < 25% | 代码实际使用相对差距策略 |
| **时间估算** | Phase 1: 2-3周 | Phase 1: 4-5周 | 需整合现有Agent，非从零构建 |
| **Embedding方案** | 建议all-MiniLM | 复用knowledge/向量存储 | 减少额外依赖，利用现有基础设施 |
| **文献检索覆盖** | ❌ 完全缺失 | ⚠️ 有Agent但无意图映射 | literature_search Agent已存在 |

### 架构关系澄清

```
原报告架构（错误）：
Intent → Capability → Tool

修正后架构（正确）：
Intent → Capability → Handler
                      ├── simple: Tool Chain
                      ├── complex: Specialist Agent
                      └── hybrid: Agent + Tool
```

### 新增内容

1. **Intent → Capability → Agent/Tool 映射机制**：明确三层路由关系
2. **与现有代码集成点**：提供具体代码插入位置和示例
3. **Specialist Agent定义表**：列出6个现有Agent的YAML配置和触发意图
4. **复用分析表**：说明knowledge/等现有模块的可复用部分

### 致谢

感谢 Agent-1（project-analyst）和 Agent-2（industry-researcher）的深入调研和反馈。

---

**报告生成时间**: 2025-03-15
**修正时间**: 2025-03-15
**分析师**: Claude Code Orchestrator Agent
**版本**: v1.1
