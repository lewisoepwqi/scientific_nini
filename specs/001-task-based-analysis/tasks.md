---

description: "Task list template for feature implementation"
---

# Tasks: 任务化分析与多图表管理

**Input**: Design documents from `/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/`
**Prerequisites**: plan.md（required）, spec.md（required）, research.md, data-model.md, contracts/

**Tests**: 默认必须包含测试任务。后端/AI（人工智能）变更需包含 pytest（测试框架），前端需包含 lint/type-check（静态检查/类型检查）；仅当规范明确豁免并写明理由时可省略。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Update max-charts(50)/retention(30d) defaults in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/core/config.py
- [x] T002 [P] Add task stage and suggestion status enums in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/enums.py
- [x] T003 [P] Add task/share/suggestion types in /home/lewis/coding/scientific_nini/frontend/src/types/task.ts
- [x] T004 [P] Add task API client scaffold in /home/lewis/coding/scientific_nini/frontend/src/services/taskApi.ts
- [x] T005 [P] Add visualization API client scaffold in /home/lewis/coding/scientific_nini/frontend/src/services/visualizationApi.ts
- [x] T006 [P] Add suggestion API client scaffold in /home/lewis/coding/scientific_nini/frontend/src/services/suggestionApi.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T007 Create analysis task model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/analysis_task.py
- [x] T008 Create dataset version model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/dataset_version.py
- [x] T009 Create visualization model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/visualization.py
- [x] T010 Create chart config model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/chart_config.py
- [x] T011 Create AI suggestion model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/suggestion.py
- [x] T012 Create export package model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/export_package.py
- [x] T013 Create task share model in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/models/task_share.py
- [x] T014 Create task schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/task.py
- [x] T015 Create visualization schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/visualization.py
- [x] T016 Create dataset version schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/dataset_version.py
- [x] T017 Create suggestion schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/suggestion.py
- [x] T018 Create export schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/export.py
- [x] T019 Create share schemas in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/share.py
- [x] T020 Add migration for task/visualization/suggestion/export/share tables in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/alembic/versions/xxxx_task_models.py
- [x] T021 Implement task state machine helpers in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/task_state_machine.py
- [x] T022 Implement task access control helper (creator-only + explicit share) in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/access_control.py
- [x] T023 Implement retention cleanup service (30d) in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/retention_service.py
- [x] T024 Implement export storage helper in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/storage_service.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - 任务化分析与多图表管理 (Priority: P1) 🎯 MVP

**Goal**: 上传后自动创建任务，支持同任务多图表持久化与列表回溯。

**Independent Test**: 完成任务创建、状态查询与多图表列表，可独立验证。

### Tests for User Story 1（默认必做，除非规范明确豁免） ⚠️

- [x] T025 [P] [US1] Contract tests for /tasks and /tasks/{id} in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_tasks_contract.py
- [x] T026 [P] [US1] Contract tests for /tasks/{id}/status and /tasks/{id}/visualizations in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_task_visualizations_contract.py
- [x] T027 [P] [US1] Contract tests for chart config reuse endpoint in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_chart_config_contract.py
- [x] T028 [P] [US1] Integration test for task + multi-chart flow in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/integration/test_task_flow.py
- [x] T029 [P] [US1] Integration test for config reuse + history view in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/integration/test_chart_history.py
- [x] T030 [P] [US1] End-to-end API test for task stage changes in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/e2e/test_task_stage_e2e.py

### Implementation for User Story 1

- [x] T031 [US1] Implement task create/list/get/status service in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/task_service.py
- [x] T032 [US1] Implement dataset version service in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/dataset_version_service.py
- [x] T033 [US1] Implement visualization service (create/list + config persistence) in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/visualization_service.py
- [x] T034 [US1] Implement chart config service (reuse/clone) in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/chart_config_service.py
- [x] T035 [US1] Add task endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/tasks.py
- [x] T036 [US1] Update visualization endpoints for task scope + config reuse in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/visualizations.py
- [x] T037 [US1] Add chart config endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/chart_configs.py
- [x] T038 [US1] Wire task/visualization/chart-config routes in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/router.py
- [x] T039 [US1] Add structured logging for task + visualization operations in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/task_service.py
- [x] T040 [US1] Update OpenAPI contract for task/visualization/config endpoints in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/contracts/openapi.yaml
- [x] T041 [P] [US1] Create task store in /home/lewis/coding/scientific_nini/frontend/src/store/taskStore.ts
- [x] T042 [P] [US1] Add task list UI in /home/lewis/coding/scientific_nini/frontend/src/pages/AnalysisPage.tsx
- [x] T043 [P] [US1] Add task detail + chart list/history component in /home/lewis/coding/scientific_nini/frontend/src/components/TaskChartList.tsx
- [x] T044 [P] [US1] Add chart config reuse action UI in /home/lewis/coding/scientific_nini/frontend/src/components/ChartConfigActions.tsx
- [x] T045 [US1] Update upload flow to create task in /home/lewis/coding/scientific_nini/frontend/src/pages/UploadPage.tsx
- [x] T046 [US1] Persist chart config + refresh list in /home/lewis/coding/scientific_nini/frontend/src/pages/ChartPage.tsx

**Checkpoint**: User Story 1 should be fully functional and independently testable

---

## Phase 4: User Story 2 - AI 建议的可控闭环 (Priority: P2)

**Goal**: 提供建议生成、展示与采纳/不采纳路径。

**Independent Test**: 解析后触发建议并完成采纳/拒绝流转。

### Tests for User Story 2（默认必做，除非规范明确豁免） ⚠️

- [x] T047 [P] [US2] Contract tests for suggestion endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_suggestions_contract.py
- [x] T048 [P] [US2] Integration test for suggestion flow in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/integration/test_suggestion_flow.py
- [x] T049 [P] [US2] End-to-end API test for suggestion state transitions in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/e2e/test_suggestion_e2e.py

### Implementation for User Story 2

- [x] T050 [US2] Add suggestion structure validation rules in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/schemas/suggestion.py
- [x] T051 [US2] Implement AI suggestion client in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/ai_suggestion_service.py
- [x] T052 [US2] Implement suggestion persistence service in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/suggestion_service.py
- [x] T053 [US2] Add suggestion endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/suggestions.py
- [x] T054 [US2] Wire suggestion routes in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/router.py
- [x] T055 [US2] Implement AI suggestion endpoint in /home/lewis/coding/scientific_nini/ai_service/api/suggestions.py
- [x] T056 [US2] Wire AI suggestion router in /home/lewis/coding/scientific_nini/ai_service/api/router.py
- [x] T057 [US2] Update OpenAPI contract for suggestion endpoints in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/contracts/openapi.yaml
- [x] T058 [P] [US2] Add suggestion panel component in /home/lewis/coding/scientific_nini/frontend/src/components/SuggestionPanel.tsx
- [x] T059 [US2] Integrate suggestion prompt/accept/reject in /home/lewis/coding/scientific_nini/frontend/src/pages/AnalysisPage.tsx
- [x] T060 [US2] Update task store with suggestion status in /home/lewis/coding/scientific_nini/frontend/src/store/taskStore.ts

**Checkpoint**: User Story 2 should be independently testable with suggestion flow

---

## Phase 5: User Story 3 - 可复现与可分享的导出 (Priority: P3)

**Goal**: 导出分享包并支持复现。

**Independent Test**: 生成分享包并在相同数据版本下复现图表。

### Tests for User Story 3（默认必做，除非规范明确豁免） ⚠️

- [x] T061 [P] [US3] Contract tests for export endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_exports_contract.py
- [x] T062 [P] [US3] Contract tests for share endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_shares_contract.py
- [x] T063 [P] [US3] Integration test for export + reproduce flow in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/integration/test_export_flow.py
- [x] T064 [P] [US3] Integration test to ensure export excludes raw data in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/integration/test_export_content.py
- [x] T065 [P] [US3] End-to-end API test for export retention/access control in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/e2e/test_export_e2e.py

### Implementation for User Story 3

- [x] T066 [US3] Implement export package service in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/export_service.py
- [x] T067 [US3] Implement publication template validation service in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/publication_template_service.py
- [x] T068 [US3] Add publication templates definitions in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/core/publication_templates.py
- [x] T069 [US3] Add export endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/exports.py
- [x] T070 [US3] Add share endpoints in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/endpoints/shares.py
- [x] T071 [US3] Wire export/share routes in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/api/v1/router.py
- [x] T072 [US3] Update OpenAPI contract for export/share/template endpoints in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/contracts/openapi.yaml
- [x] T073 [P] [US3] Add export API client in /home/lewis/coding/scientific_nini/frontend/src/services/exportApi.ts
- [x] T074 [P] [US3] Add share API client in /home/lewis/coding/scientific_nini/frontend/src/services/shareApi.ts
- [x] T075 [P] [US3] Add export action component in /home/lewis/coding/scientific_nini/frontend/src/components/ExportButton.tsx
- [x] T076 [P] [US3] Add share dialog component in /home/lewis/coding/scientific_nini/frontend/src/components/ShareDialog.tsx
- [x] T077 [US3] Add export reproduce flow in /home/lewis/coding/scientific_nini/frontend/src/pages/PreviewPage.tsx
- [x] T078 [US3] Add template selection + validation UI in /home/lewis/coding/scientific_nini/frontend/src/components/ExportTemplateSelect.tsx

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T079 [P] Update API documentation in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/docs/api.md
- [x] T080 Add observability helpers for task/suggestion/export in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/app/services/observability.py
- [x] T081 [P] Add chart list performance benchmark in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/perf/test_chart_list_perf.py
- [x] T082 [P] Record quickstart verification in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/quickstart.md
- [x] T083 [P] Record frontend lint/type-check results in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/quickstart.md
- [x] T084 [P] Record backend pytest results in /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel or sequentially (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational (Phase 2) - no dependencies
- **US2 (P2)**: Starts after Foundational (Phase 2) - integrates with task context
- **US3 (P3)**: Starts after Foundational (Phase 2) - integrates with visualization outputs

### Parallel Opportunities

- All tasks marked [P] within a phase can be done in parallel
- After Phase 2, US1/US2/US3 can proceed in parallel if staffed

---

## Parallel Example: User Story 1

```bash
Task: "Contract tests for /tasks and /tasks/{id} in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_tasks_contract.py"
Task: "Contract tests for /tasks/{id}/status and /tasks/{id}/visualizations in /home/lewis/coding/scientific_nini/scientific_data_analysis_backend/tests/contract/test_task_visualizations_contract.py"
Task: "Create task store in /home/lewis/coding/scientific_nini/frontend/src/store/taskStore.ts"
Task: "Add task detail + chart list/history component in /home/lewis/coding/scientific_nini/frontend/src/components/TaskChartList.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Run US1 tests and verify independent flow

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test independently → Demo
3. Add US2 → Test independently → Demo
4. Add US3 → Test independently → Demo

### Parallel Team Strategy

- After Phase 2, assign separate owners to US1/US2/US3 to parallelize delivery
