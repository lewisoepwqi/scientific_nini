# peer-review Specification

## Purpose
定义同行评审辅助能力在意图层的识别规则、同义词覆盖范围，以及审稿意见整理和回复信撰写场景的路由要求，确保审稿相关请求能稳定命中对应能力。

## Requirements

### Requirement: peer_review Capability 在意图层可被识别

系统 SHALL 在 `create_default_capabilities()` 中注册 `peer_review` Capability，使用户的审稿辅助请求能通过意图层路由到 `review_assistant` Agent。

#### Scenario: 用户请求整理审稿意见时意图层推荐 peer_review

- **WHEN** 用户输入含"审稿"、"同行评审"、"评审意见"等关键词的请求
- **THEN** `capability_candidates` 中包含 `peer_review`

### Requirement: peer_review 同义词覆盖审稿流程相关术语

`config/intent_synonyms.yaml` 中 SHALL 包含 `peer_review` 条目，覆盖审稿意见整理、回复信撰写、修改建议等词汇。

#### Scenario: 同义词匹配回复审稿人请求

- **WHEN** 用户输入"帮我写一封回复审稿人的信"
- **THEN** 意图候选中包含 `peer_review`

#### Scenario: 同义词匹配英文 reviewer 词汇

- **WHEN** 用户输入"reviewer comments 怎么回"
- **THEN** 意图候选中包含 `peer_review`
