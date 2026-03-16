## 1. 用户画像 Boosting 模块

- [x] 1.1 新建 `src/nini/intent/profile_booster.py`，导入 `IntentCandidate`、`UserProfile`，定义 capability 与 method 的映射表 `_CAPABILITY_METHOD_MAP: dict[str, list[str]]`，覆盖当前全部 11 个 capability：
  - `difference_analysis`: `["t_test", "anova", "mann_whitney", "kruskal_wallis", "paired_t_test", "independent_t_test", "one_way_anova"]`
  - `correlation_analysis`: `["pearson", "spearman", "kendall", "correlation"]`
  - `regression_analysis`: `["linear_regression", "logistic_regression", "multiple_regression"]`
  - `data_exploration`: `["data_summary", "preview_data", "data_quality"]`
  - `data_cleaning`: `["clean_data", "dataset_transform"]`
  - `visualization`: `["create_chart", "export_chart"]`
  - `report_generation`: `["generate_report", "export_report"]`
  - `article_draft`: `[]`（无直接方法映射，不参与 Boosting）
  - `citation_management`: `[]`（Phase 1 新增，无统计方法映射）
  - `peer_review`: `[]`（Phase 1 新增，无统计方法映射）
  - `research_planning`: `[]`（Phase 1 新增，无统计方法映射）
- [x] 1.2 实现 `_compute_delta(capability_name: str, user_profile: UserProfile) -> float`：查找 capability 对应的 method 列表，将 `user_profile.preferred_methods` 中这些 method 的权重求和，乘以系数 3.0，上限 clamp 到 3.0
- [x] 1.3 实现 `apply_boost(candidates: list[IntentCandidate], user_profile: UserProfile) -> list[IntentCandidate]`：对每个候选调用 `_compute_delta`，用 `dataclasses.replace` 创建新候选对象（不修改原对象），按新 score 降序排列后返回
- [x] 1.4 在 `src/nini/intent/__init__.py` 中导出 `apply_boost`

## 2. analyze() 集成 Boosting 与低置信度日志

- [x] 2.1 在 `src/nini/intent/optimized.py` 顶部添加：`from nini.intent.profile_booster import apply_boost` 和 `_lowconf_logger = logging.getLogger("nini.intent.lowconf")`
- [x] 2.2 `analyze()` 方法签名新增 `user_profile: UserProfile | None = None` 参数（向后兼容，默认 `None`）；需同步导入 `from nini.models.user_profile import UserProfile`
- [x] 2.3 在 `analyze()` 的 `_apply_clarification_policy()` 调用之前，如果 `user_profile` 非 `None`，调用 `analysis.capability_candidates = apply_boost(analysis.capability_candidates, user_profile)` 重排候选
- [x] 2.4 在 `analyze()` 末尾（return 之前），检查 `analysis.capability_candidates` 为空或 `analysis.capability_candidates[0].score < 3.0` 时，通过 `_lowconf_logger.info(...)` 写入 JSON 格式日志，格式为 `{"query": ..., "top_score": ..., "timestamp": ...}`（`query` 截断到 200 字符，`top_score` 为空列表时设为 0.0，`timestamp` 用 `datetime.now(timezone.utc).isoformat()`）

## 3. 构建评估数据集

- [x] 3.1 创建目录 `tests/fixtures/`
- [x] 3.2 创建 `tests/fixtures/intent_eval_dataset.yaml`，编写 50 条域内查询，覆盖全部 8 个 capability（每个至少 4 条），格式：`{query, expected_top1, query_type: "domain_task", note}`
- [x] 3.3 追加 20 条模糊/多意图查询（`query_type: "ambiguous"`，`expected_top1` 为最可能的 capability 或 `null`），覆盖典型澄清场景
- [x] 3.4 追加 20 条 OOS 查询（`query_type: "out_of_scope"`，`expected_top1: null`），覆盖联网检索类和非科研通用类两种 OOS

## 4. 编写评估测试套件

- [x] 4.1 新建 `tests/test_intent_eval.py`，在 `conftest.py` 或 module 级 fixture 中加载 `tests/fixtures/intent_eval_dataset.yaml` 并初始化 `OptimizedIntentAnalyzer`
- [x] 4.2 用 `@pytest.mark.parametrize` 对 `domain_task` 类型用例参数化，断言 `analyze(query).capability_candidates[0].name == expected_top1`；测试名包含 query 前 30 字符以便定位失败
- [x] 4.3 用 `@pytest.mark.parametrize` 对 `out_of_scope` 类型用例参数化，断言 `analyze(query).query_type == QueryType.OUT_OF_SCOPE`
- [x] 4.4 添加 session 级 fixture：在 module 顶部定义两个列表 `_domain_results: list[bool] = []`、`_oos_results: list[bool] = []`；参数化测试执行时将命中结果 `append` 到对应列表；session 级 fixture 在 `yield` 之后直接 `print()` 输出域内 Top-1 准确率（`sum(_domain_results)/len(_domain_results)`）和 OOS 召回率，不使用 `capsys`/`capfd`（session 级 fixture 不支持 function-scope 的 `capsys`）
- [x] 4.5 运行 `pytest tests/test_intent_eval.py -v` 验证测试可运行，记录初始基线准确率（允许低于目标值，目的是建立基线）

## 5. 编写单元测试

- [x] 5.1 编写测试：`_compute_delta("difference_analysis", profile_with_t_test_weight_0.8)` 返回 > 0 的值
- [x] 5.2 编写测试：`apply_boost(candidates, empty_profile)` 返回与输入相同顺序的候选列表（score 不变）
- [x] 5.3 编写测试：`apply_boost` 不修改原候选对象（immutability）
- [x] 5.4 编写测试：低分查询（Top-1 < 3.0）触发 `nini.intent.lowconf` 日志记录（使用 `caplog`）
- [x] 5.5 编写测试：高分查询（Top-1 >= 3.0）不触发低置信度日志
- [ ] 5.6 运行 `pytest tests/ -q` 验证全部测试通过（本次会话已两次尝试，测试在约 4% 处长时间无输出，未完成）

## 6. 收尾

- [x] 6.1 运行 `black --check src tests` 格式检查，必要时格式化（仓库级检查存在既有失败，本次改动相关文件已通过 `black --check`）
- [x] 6.2 运行 `mypy src/nini` 验证无新增类型错误（仓库级检查存在既有错误，本次改动相关文件已通过 `mypy`）
- [x] 6.3 按 git workflow 规范提交并创建 PR，base 分支为 `main`
