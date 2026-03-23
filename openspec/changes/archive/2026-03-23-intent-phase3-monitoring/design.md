## Context

Phase 3 是意图体系优化的收尾阶段，前置条件是 Phase 2 的多意图和澄清策略改进已上线，并积累了足够真实查询样本。此阶段关注两件事：让系统"认识"用户（画像 Boosting），以及让团队"看到"系统表现（评估 + 监控）。

`UserProfile` 已有 `preferred_methods: dict[str, float]`（如 `{"t_test": 0.6, "anova": 0.4}`）和 `research_domains: list[str]`（如 `["biology", "medicine"]`），但意图分析器目前完全不使用这些信息。本阶段 Boosting 仅使用 `preferred_methods`（方法偏好权重可精确映射到 capability），`research_domains` 留待后续阶段实现（需要额外的 domain→capability 映射表）。

## Goals / Non-Goals

**Goals:**
- `profile_booster.apply_boost(candidates, user_profile)` 对候选列表做评分加权，不改变 `IntentAnalysis` 数据结构
- `analyze()` 向后兼容新增 `user_profile` 参数（默认 `None`，不传时行为完全不变）
- 90 条 YAML 评估数据集 + 参数化测试，CI 中可运行，首次运行建立准确率基线
- 低置信度日志：`logger.info` 写入 `nini.intent.lowconf` logger，JSON 格式含 query、top_score、timestamp

**Non-Goals:**
- 不实现跨会话的历史意图序列预测（需要持久化的意图历史字段，不在本次改动范围）
- 不实现在线学习或 Embedding fine-tuning
- 不构建监控 Dashboard（日志由运维系统消费）
- 不修改 `UserProfile` 数据模型（只读取，不新增字段）
- **不基于 `research_domains` 做 Boosting**（需额外的 domain→capability 映射表，复杂度不对等，留后续阶段）
- **评估数据集准确率目标（>= 80%）不作为 CI 断言**，首次运行仅建立基线；准确率打印到控制台供人工观察

## Decisions

### 决策 1：Boosting 采用加法而非乘法

```python
# 加法 Boosting：对特定 capability 的分数加上 boost_delta
def apply_boost(candidates, user_profile) -> list[IntentCandidate]:
    ...
    for c in candidates:
        delta = _compute_delta(c.name, user_profile)
        c = dataclasses.replace(c, score=c.score + delta)
    return sorted(candidates, key=lambda x: x.score, reverse=True)
```

boost_delta 取值范围 [0, 3]，与现有分数量级（5~20）兼容，不会让 Boosting 完全覆盖文本匹配信号。

**备选**：乘法（score * factor）→ 被否决，低分候选乘以大系数后可能异常超越高分候选，线性加法更可预测。

### 决策 2：评估数据集用 YAML 而非 CSV 或 Python fixture

YAML 结构化且可读性好，研究人员可直接编辑添加用例。数据集格式：

```yaml
- query: "帮我做配对t检验"
  expected_top1: "difference_analysis"
  query_type: "domain_task"
  note: "含具体检验类型"
- query: "帮我订机票"
  expected_top1: null
  query_type: "out_of_scope"
```

`tests/test_intent_eval.py` 用 `@pytest.mark.parametrize` 加载 YAML，参数化运行每条用例，失败时显示具体 query。

### 决策 3：低置信度阈值设为 Top-1 分数 < 3.0

该阈值低于现有澄清触发阈值（5.0），专门捕获"意图分析器几乎没有线索"的极端低信度情况。日志使用独立 logger 名 `nini.intent.lowconf`，生产环境可单独配置输出到文件/ELK，不污染主日志。

## Risks / Trade-offs

**[风险 1] Boosting 造成意图"锁定效应"** → 用户偶尔尝试新分析类型时，画像 Boosting 持续将其偏向历史偏好。缓解：boost_delta 上限 3.0，而文本强匹配分数可达 15+，文本信号仍为主导；`preferred_methods` 更新需要用户主动使用新方法，天然有一定惰性保护。

**[风险 2] 评估数据集标注偏差** → 数据集由开发者手工标注，可能偏向开发者认知而非真实用户表达。缓解：YAML 格式方便后续从生产日志中挑选真实查询补充；初始 90 条作为基线，不要求覆盖全部场景。

**[风险 3] 低置信度日志量过大** → 初期意图系统仍不完善，大量查询可能触发低置信度日志。缓解：独立 logger 可动态调整日志级别；阈值 3.0 相对保守，只记录真正低信度情况。

## Migration Plan

1. 三处新增文件（`profile_booster.py`、`intent_eval_dataset.yaml`、`test_intent_eval.py`）不破坏现有代码
2. `analyze()` 的 `user_profile` 参数有默认值 `None`，所有现有调用无需修改
3. 低置信度日志默认不输出（需要 `nini.intent.lowconf` logger 配置为 INFO 级别才可见）
4. 回滚：删除三个新文件；`optimized.py` 的修改可独立 `git revert`
