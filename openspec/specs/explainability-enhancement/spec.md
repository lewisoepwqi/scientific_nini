# Capability: Explainability Enhancement

## Purpose

Provide users with visibility into the Agent's reasoning process, enabling better understanding and trust in AI-driven analysis decisions.
## Requirements
### Requirement: Reasoning event visualization

The system SHALL provide enhanced visualization for REASONING events in the chat interface and SHALL preserve one stable reasoning identity across streaming, completion, history restoration, and prompt/runtime context reconstruction.

#### Scenario: Collapsible reasoning steps

- **WHEN** a REASONING event is received from the Agent
- **THEN** the system SHALL render it as a collapsible panel in the message stream
- **AND** the panel SHALL show a summary title (e.g., "分析思路", "决策过程")
- **AND** the user SHALL be able to expand/collapse the panel to view full reasoning

#### Scenario: Highlighted decision points

- **WHEN** the reasoning content contains decision keywords (e.g., "选择", "决定", "因此", "因为")
- **THEN** those keywords SHALL be visually highlighted (bold or colored text)
- **AND** the system SHALL parse and display decision chains in a structured format

#### Scenario: Streaming reasoning updates merge into one panel

- **WHEN** multiple REASONING events with the same stable reasoning identity are emitted for a single reasoning chain
- **THEN** the client SHALL merge them into one logical reasoning panel
- **AND** the completed reasoning event SHALL finalize that same panel instead of creating another reasoning bubble

#### Scenario: Refreshed transcript restores completed reasoning without duplication

- **WHEN** the user refreshes the page after a reasoning stream has completed
- **THEN** the restored transcript SHALL contain one completed reasoning panel for that reasoning identity
- **AND** the transcript SHALL NOT replay duplicated reasoning fragments as separate panels

#### Scenario: Reasoning-related runtime context respects the untrusted-context contract

- **WHEN** reasoning-adjacent runtime materials such as analysis memories or research profile preferences are injected into an LLM call
- **THEN** those materials SHALL be marked and ordered according to the canonical untrusted runtime context contract
- **AND** they SHALL NOT be elevated into trusted system prompt directives

### Requirement: Analysis reasoning timeline

The system SHALL display the Agent's reasoning process as a timeline view.

#### Scenario: Timeline view for analysis steps

- **WHEN** the user initiates a multi-step analysis
- **THEN** a timeline component SHALL appear showing each reasoning step
- **AND** each step SHALL display: step number, title, status (pending/active/completed), timestamp

#### Scenario: Step detail expansion

- **WHEN** the user clicks on a timeline step
- **THEN** the step SHALL expand to show detailed reasoning content
- **AND** any associated tool calls or data references SHALL be shown as sub-items

#### Scenario: Timeline progression

- **WHEN** the Agent completes a reasoning step
- **THEN** the timeline SHALL automatically scroll to show the next active step
- **AND** completed steps SHALL be marked with a success indicator

### Requirement: Decision rationale display

The system SHALL display the rationale behind key analysis decisions.

#### Scenario: Tool selection explanation

- **WHEN** the Agent decides to use a specific statistical test (e.g., t_test vs mann_whitney)
- **THEN** the reasoning SHALL include why that test was chosen
- **AND** the UI SHALL display this rationale adjacent to the tool call result

#### Scenario: Assumption checking explanation

- **WHEN** the Agent checks statistical assumptions (normality, homogeneity)
- **THEN** the reasoning SHALL explain the assumption check results
- **AND** if assumptions are violated, the reasoning SHALL explain the fallback strategy

### Requirement: Reasoning event structure enhancement

The system SHALL support structured REASONING event metadata for enhanced visualization.

#### Scenario: Structured reasoning metadata

- **WHEN** the Agent generates a REASONING event
- **THEN** the event MAY include structured fields:
  - reasoning_type: "analysis" | "decision" | "planning" | "reflection"
  - confidence_score: 0.0 to 1.0
  - key_decisions: list of key decision points
  - references: citations to data or prior steps

#### Scenario: Reasoning chain linking

- **WHEN** multiple REASONING events are generated in sequence
- **THEN** each event SHALL include a reference to the parent reasoning (if applicable)
- **AND** the UI SHALL be able to display them as a connected chain

### Requirement: Export reasoning for documentation

The system SHALL allow users to export reasoning for documentation purposes.

#### Scenario: Copy reasoning to clipboard

- **WHEN** the user clicks the "复制分析思路" button on a reasoning panel
- **THEN** the full reasoning content SHALL be formatted and copied to clipboard
- **AND** the format SHALL be suitable for pasting into research documentation

#### Scenario: Include reasoning in report export

- **WHEN** the user generates a research report
- **THEN** there SHALL be an option to include the reasoning timeline in the export
- **AND** the reasoning SHALL be formatted as a methodological appendix

### Requirement: Completion verification visibility

系统 SHALL 在用户界面中展示完成前校验的状态，而不是仅在后台静默执行。

#### Scenario: 用户可见 completion check 结果

- **WHEN** 前端收到 `completion_check` 事件
- **THEN** 系统 SHALL 在现有分析过程界面中展示校验结果
- **AND** 用户 SHALL 能看到哪些检查项已经满足、哪些仍待补齐

#### Scenario: 未通过校验时显示继续执行原因

- **WHEN** completion check 未通过且系统继续执行当前轮
- **THEN** 界面 SHALL 明确说明“为何尚未结束”
- **AND** 不得仅表现为模型继续输出而没有解释

### Requirement: Recovery and blocked state visibility

系统 SHALL 让 loop recovery 与 blocked 状态成为可理解的运行诊断信息。

#### Scenario: 坏循环恢复过程可见

- **WHEN** 系统识别到坏循环并触发恢复
- **THEN** 界面 SHALL 显示当前处于恢复、重规划或重新验证状态
- **AND** 用户 SHALL 能理解这是系统主动纠偏而非普通推理文本

#### Scenario: blocked 原因对用户可见

- **WHEN** 系统进入 `blocked` 状态
- **THEN** 界面 SHALL 显示阻塞原因和建议动作
- **AND** 用户 SHALL 能区分“任务失败终止”与“需要补充信息或调整策略”

### Requirement: Harness diagnostics integrate with existing analysis views

系统 SHALL 将 harness 诊断状态整合到现有分析计划、推理或任务视图中，而不是要求用户跳转到完全独立的新界面才能理解运行状态。

#### Scenario: 诊断信息与现有任务状态并列展示

- **WHEN** completion check、loop recovery 或 blocked 事件发生
- **THEN** 这些状态 SHALL 能与现有计划步骤、任务尝试或推理面板一起呈现
- **AND** 用户 SHALL 能从同一轮分析视图追踪运行进度与诊断结果
