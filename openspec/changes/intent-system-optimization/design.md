## Context

当前系统在三个位置存在可独立修复的缺陷：

1. **`harness/runner.py:385`** — `promised_artifact` 正则 `(图表|报告|产物|已生成|已导出|附件)` 单独匹配产物词即触发，AI 介绍自身能力时（"我可以制作图表与报告"）被误判为承诺产物，导致 HarnessRunner 触发第二轮 AgentRunner，同一消息收到两次完整回答。

2. **`agent/router.py`** — `_BUILTIN_RULES` 和 `_LLM_ROUTING_PROMPT` 只列出 6 个 Specialist Agent，实际已有 9 个 YAML 定义（`citation_manager`、`research_planner`、`review_assistant` 未接入），用户相关请求永远无法路由到这三个 Agent。

3. **`intent/optimized.py`** — `_SYNONYM_MAP` 完全硬编码在 Python 源文件中，任何同义词扩展都需要修改代码、重启服务，维护成本高。

三处改动相互独立，均无外部依赖变更，可按顺序单独发布。

## Goals / Non-Goals

**Goals:**
- 消除 Harness 完成校验对能力描述类回答的误判，单消息不再触发双回答
- 将 TaskRouter 内置规则和 LLM Prompt 覆盖率从 6/9 提升到 9/9
- 同义词表 YAML 外置，重启后生效，无需修改代码即可扩展

**Non-Goals:**
- 不引入 Embedding 检索或外部 NLU 服务
- 不修改现有 9 个 Agent 的 YAML 配置内容
- 不改变 `RoutingDecision` 数据结构或公开接口签名
- 不实现多意图检测（留待后续 Phase 2）

## Decisions

### 决策 1：`promised_artifact` 改为"完成语义词 + 产物词"正则组合

**选择**：使用两段正则 OR 匹配，要求完成语义词（`已生成|已导出|已完成|以下是|请查看|如下`）和产物词（`图表|报告|产物|附件`）在 15 字符范围内共现：

```python
_PROMISED_ARTIFACT_RE = re.compile(
    r"(已生成|已导出|已完成|以下是|请查看|如下)[\s\S]{0,15}(图表|报告|产物|附件)"
    r"|(图表|报告|产物|附件)[\s\S]{0,8}(已生成|已导出|已完成|已保存)",
)
promised_artifact = bool(_PROMISED_ARTIFACT_RE.search(final_text))
```

**备选方案**：
- *方案 A*：增加 `query_type == CASUAL_CHAT` 时跳过产物校验 — 被否决，因 session 上没有可靠的 query_type 持久化字段，实现需额外改动
- *方案 B*：完全移除产物校验项 — 被否决，该校验在真实分析场景（模型承诺生成图表却漏掉工具调用）仍有价值
- *方案 C*（选择）：收紧正则语义，保留校验逻辑，改动最小、风险最低

**理由**：最小改动，不影响 harness 其他校验项；正则模式可在不重启服务的情况下通过配置调整。

### 决策 2：TaskRouter 新增 3 条规则，保持关键词集合设计不变

**选择**：直接在 `_BUILTIN_RULES` 列表末尾追加 3 条 `frozenset` 规则，同步在 `_LLM_ROUTING_PROMPT` 和 `_LLM_BATCH_ROUTING_PROMPT` 中补充 3 个 Agent 描述。

关键词设计：
- `citation_manager`：`{"引用格式", "参考文献", "文献管理", "bibliography", "citation"}`
- `research_planner`：`{"研究规划", "研究设计", "实验设计", "研究方案", "研究思路"}`
- `review_assistant`：`{"审稿", "同行评审", "评审意见", "回复审稿", "修改意见"}`

**备选方案**：
- *动态从 YAML 加载路由规则* — 被否决，过度设计，路由规则变化频率极低，YAML 化收益不抵额外复杂度
- *修改置信度阈值* — 不适用，问题是规则缺失而非阈值不合理

**理由**：与现有 6 条规则格式完全一致，零学习成本，可直接通过现有测试框架验证。

### 决策 3：同义词 YAML 加载在 `__init__` 时一次性完成，失败回退内置

**选择**：`OptimizedIntentAnalyzer.__init__` 中尝试加载 `config/intent_synonyms.yaml`，成功则替换 `_SYNONYM_MAP`，失败（文件不存在或格式错误）则保留内置 dict 并记录日志。配置文件路径相对于项目根目录（通过 `settings.base_dir` 获取）。

```python
def _load_synonym_map() -> dict[str, list[str]]:
    """加载外部同义词配置，失败时回退内置。"""
    config_path = settings.base_dir / "config" / "intent_synonyms.yaml"
    if not config_path.exists():
        logger.debug("未找到外部同义词配置，使用内置 _SYNONYM_MAP")
        return dict(_SYNONYM_MAP)
    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("顶层结构须为 dict")
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as exc:
        logger.warning("加载同义词配置失败，回退内置: path=%s err=%s", config_path, exc)
        return dict(_SYNONYM_MAP)
```

**备选方案**：
- *文件变更时热重载* — 被否决，需要文件监听线程，复杂度过高；当前场景启动时加载一次足够
- *通过 API 端点更新* — 被否决，超出本次改动范围

**理由**：启动时一次加载，无运行时开销；`PyYAML` 需在实现前确认是否已在传递依赖中（通过 `python -c "import yaml"` 验证），若缺失需在 `pyproject.toml` 显式声明。

## Risks / Trade-offs

**[风险 1] `promised_artifact` 正则漏判真实承诺** → 如果模型用非标准表达承诺产物（如"给你一份分析"而非"以下是报告"），新正则可能漏判，导致真实承诺漏检。缓解：保留 `not_transitional` 校验项作为补充，过渡性结尾仍会被拦截；同时通过 harness trace 监控实际触发频率，按需补充语义词列表。

**[风险 2] 新增路由关键词与现有关键词产生歧义** → `citation_manager` 的规则中"引用格式"包含"引用"子串，而"引用"已在 `literature_search` 规则中，导致"参考文献引用格式"同时命中两个 Agent；`research_planner` 的"研究设计"也可能与其他规则产生交叉。缓解：当前多命中返回多 Agent 并行执行，对这类边界查询影响有限；`citation_manager` 规则已使用长语（"引用格式"而非单字"引用"），可减少误命中频率。若噪音明显，后续可将 `citation_manager` 规则中的"引用格式"拆分为更精确的短语。

**[风险 3] YAML 配置文件格式错误导致回退** → 用户修改配置文件格式有误时，系统静默使用内置配置，用户可能不知道自己的修改未生效。缓解：启动日志中 WARNING 级别明确提示路径和错误原因；`nini doctor` 命令可扩展校验此配置文件（后续改动）。

## Migration Plan

1. 三处改动均无破坏性变更，可直接部署，无需数据迁移
2. `config/intent_synonyms.yaml` 随代码库一同提交（初始内容与现有 `_SYNONYM_MAP` 完全一致），确保存量部署立即可用
3. 回滚策略：删除 `config/intent_synonyms.yaml` 即回退同义词到内置；其余两处修改通过 `git revert` 回滚

## Open Questions

- `_PROMISED_ARTIFACT_RE` 中"完成语义词"列表是否需要覆盖英文表达（如 `here is`、`generated`）？当前模型回复以中文为主，暂不纳入，待观察后决定。
- `nini doctor` 是否应在启动检查中验证 `config/intent_synonyms.yaml` 格式？留待后续 Phase 1 完善 OOS 扩展时一并处理。
