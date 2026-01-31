# Implementation Plan: 任务化分析与多图表管理

**Branch**: `001-task-based-analysis` | **Date**: 2026-01-31 | **Spec**: /home/lewis/coding/scientific_nini/specs/001-task-based-analysis/spec.md
**Input**: Feature specification from `/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/spec.md`

## Summary

本计划聚焦“任务化主线 + 单数据集多图表 + AI（人工智能）建议闭环 + 可复现分享”。技术方案以既有前后端分层为基础，通过任务状态机、数据版本与图表持久化实现可追溯分析流程，并以 REST（表述性状态转移）风格的 `/api/v1` 接口输出能力。研究结论明确了默认访问控制、分享包不含原始数据、7 阶段任务状态机、单任务图表上限可配置与 30 天数据保留策略。

## Technical Context

**Language/Version**: Python 3.x（后端/AI 服务），TypeScript（前端）  
**Primary Dependencies**: FastAPI（后端 Web 框架），React（前端框架） + Vite（构建工具） + Zustand（状态管理），Plotly（图表渲染）  
**Storage**: PostgreSQL（关系型数据库），Redis（缓存/任务状态），文件存储（数据集与导出包）  
**Testing**: pytest（测试框架），`npm run lint` + `npm run type-check`  
**Target Platform**: Linux 服务器 + 现代浏览器（Web 端）  
**Project Type**: Web（网页）应用  
**Performance Goals**: 图表列表在 ≤50 图表场景下 95% 加载 ≤5 秒；AI 建议流程 60% 用户在 2 分钟内完成闭环  
**Constraints**: 分享包不包含原始数据；默认仅创建者访问并需显式分享；单任务图表数量设上限（可配置）；任务状态机 7 阶段  
**Scale/Scope**: 单任务图表默认上限 50（可配置）；数据与分享包默认保留 30 天

## Constitution Check

*门禁：必须在第 0 阶段研究前通过，第 1 阶段设计后重新检查。*

- 语言一致性：所有新增/修改文档与用户交互必须为中文，术语首次出现需标注中文解释。
- 分层与契约：前端仅通过后端 `/api/v1`；AI（人工智能）能力必须经由后端；接口变更同步更新契约/文档/测试。
- 数据安全：密钥仅通过环境变量；日志不得包含敏感数据；数据最小化原则需在计划中体现。
- 质量门禁：后端/AI 变更需包含 pytest（测试框架）；前端需通过 `npm run lint` 与 `npm run type-check`；如豁免需说明理由。
- 可复现与可观测：计划必须列出参数记录、随机种子（如适用）与结构化日志要求。
- 若存在违反或复杂度超标，必须在 “Complexity Tracking（复杂度跟踪）” 中记录并给出替代方案说明。

结论：无违反，允许进入第 0 阶段研究。

## Project Structure

### Documentation (this feature)

```text
/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出
├── data-model.md        # Phase 1 输出
├── quickstart.md        # Phase 1 输出
├── contracts/           # Phase 1 输出
└── tasks.md             # Phase 2 输出（/speckit.tasks 生成）
```

### Source Code (repository root)

```text
/home/lewis/coding/scientific_nini/
├── scientific_data_analysis_backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── services/
│       ├── store/
│       └── types/
└── ai_service/
    ├── api/
    ├── core/
    ├── services/
    └── tests/
```

**Structure Decision**: 采用 Web 应用结构，后端位于 `scientific_data_analysis_backend/`，前端位于 `frontend/`，AI 服务位于 `ai_service/`，与现有工程结构一致。

## Complexity Tracking

无。

## Phase 0: 研究与约束收敛

- 输出：`/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/research.md`
- 目标：消除技术上下文不确定性，固化访问控制、分享包内容、状态机与保留策略等关键决策。

## Phase 1: 设计与契约

- 数据模型：`/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/data-model.md`
- 接口契约：`/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/contracts/openapi.yaml`
- 快速开始：`/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/quickstart.md`
- 可复现与可观测：记录数据版本、关键参数与随机种子（如适用），输出结构化日志与关键指标（耗时、失败原因）。

## Phase 1: Agent Context 更新

- 已运行：`.specify/scripts/bash/update-agent-context.sh codex`

## Constitution Check (Post-Design)

- 语言一致性：通过（全部为中文，术语含英文解释）。
- 分层与契约：通过（接口统一 `/api/v1`，AI 由后端转发）。
- 数据安全：通过（分享包不含原始数据，访问控制默认仅创建者）。
- 质量门禁：通过（计划中明确 pytest 与前端 lint/type-check）。
- 可复现与可观测：通过（数据版本、参数、结构化日志写入计划）。

结论：无违反，可进入 Phase 2 任务拆解。

## Phase 2: 任务拆解（由 /speckit.tasks 生成）

- 输出：`/home/lewis/coding/scientific_nini/specs/001-task-based-analysis/tasks.md`
- 说明：本阶段不在 /speckit.plan 内生成。
