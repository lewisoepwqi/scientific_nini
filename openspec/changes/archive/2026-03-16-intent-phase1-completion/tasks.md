## 1. 新增三个 Capability 定义

- [x] 1.1 在 `src/nini/capabilities/defaults.py` 的 `create_default_capabilities()` 末尾追加 `citation_management` Capability：`name="citation_management"`、`display_name="引用管理"`、`description="参考文献格式化、引用规范转换（APA/MLA/GB/T）"`、`is_executable=False`、`execution_message="请在对话中描述需要整理的参考文献和目标格式，Agent 将调用 citation_manager 为你处理。"`
- [x] 1.2 在同函数末尾追加 `peer_review` Capability：`name="peer_review"`、`display_name="同行评审辅助"`、`description="整理审稿意见、生成回复信件"`、`is_executable=False`、`execution_message="请在对话中粘贴审稿意见，Agent 将调用 review_assistant 帮你整理回复思路和草拟回信。"`
- [x] 1.3 在同函数末尾追加 `research_planning` Capability：`name="research_planning"`、`display_name="研究规划"`、`description="研究设计、实验方案制定、样本量计算"`、`is_executable=False`、`execution_message="请在对话中描述你的研究目标和约束条件，Agent 将调用 research_planner 帮你制定实验方案。"`

## 2. 扩充 YAML 同义词配置

- [x] 2.1 在 `config/intent_synonyms.yaml` 末尾追加 `citation_management` 条目，同义词含：引用格式、参考文献、文献引用、引用管理、bibliography、APA格式、MLA格式、GB/T格式、citation、文献格式化、引用规范
- [x] 2.2 追加 `peer_review` 条目，同义词含：审稿意见、同行评审、评审意见、回复审稿、修改意见、reviewer、peer review、审稿人、回复审稿人、reviewer comments、意见回复
- [x] 2.3 追加 `research_planning` 条目，同义词含：研究规划、研究设计、实验设计、研究方案、研究思路、样本量、样本量计算、随机化、研究框架、research design、实验方案

## 3. 新增 QueryType.OUT_OF_SCOPE 及 OOS 扩展

- [x] 3.1 在 `src/nini/intent/base.py` 的 `QueryType` 枚举中新增 `OUT_OF_SCOPE = "out_of_scope"`
- [x] 3.2 扩展 `src/nini/intent/optimized.py` 中的 `_OUT_OF_SCOPE_RE`，在现有联网检索词后追加通用非科研词汇：订机票、订酒店、订餐、外卖、天气预报、股票行情、彩票、播放音乐、讲笑话、导航路线、网购、快递查询、打车（注意：避免使用 "搜索"、"查询" 等在科研场景中有合理用途的裸词）
- [x] 3.3 修改 `_classify_query_type` 方法：将 `_OUT_OF_SCOPE_RE` 检测**提到方法的最前面**（先于 `if not analysis.capability_candidates:` 整个分支），命中时直接返回 `QueryType.OUT_OF_SCOPE`；这是必要的，因为 OOS 类查询通常不命中任何 capability 同义词（`candidates` 为空），若不提前检测则会错误返回 `KNOWLEDGE_QA`

## 4. 编写测试

- [x] 4.1 编写测试：`create_default_capabilities()` 返回的列表包含 `citation_management`、`peer_review`、`research_planning` 三个 Capability
- [x] 4.2 编写测试：含"参考文献"的输入，意图分析器候选中包含 `citation_management`（需先初始化分析器并传入 capabilities）
- [x] 4.3 编写测试：含"审稿意见"的输入，意图候选中包含 `peer_review`
- [x] 4.4 编写测试：含"实验设计"的输入，意图候选中包含 `research_planning`
- [x] 4.5 编写测试：`QueryType` 枚举包含 `OUT_OF_SCOPE` 值且值为字符串 `"out_of_scope"`
- [x] 4.6 编写测试：输入"帮我订一张机票"，`_classify_query_type` 返回 `QueryType.OUT_OF_SCOPE`
- [x] 4.7 编写测试：输入"明天天气怎么样"，`_classify_query_type` 返回 `QueryType.OUT_OF_SCOPE`
- [x] 4.8 编写测试：`OUT_OF_SCOPE` 时 `rag_needed` 为 `False`
- [x] 4.9 运行 `pytest tests/ -q` 验证全部测试通过

## 5. 收尾

- [x] 5.1 运行 `black --check src tests` 格式检查，必要时 `black src tests` 修正
- [x] 5.2 运行 `mypy src/nini` 验证无新增类型错误
- [x] 5.3 按 git workflow 规范提交并创建 PR，base 分支为 `main`
