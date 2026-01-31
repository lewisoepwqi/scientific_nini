# 数据模型：任务化分析与多图表管理

> 说明：字段为业务语义层描述，不绑定具体实现细节。

## 实体与字段

### 1) 分析任务

- **含义**: 贯穿上传、解析、建议与可视化的任务上下文。
- **关键字段**:
  - `id`：唯一标识
  - `dataset_id`：关联数据集标识
  - `owner_id`：创建者标识
  - `stage`：任务阶段（uploading / parsed / profiling / suggestion_pending / processing / analysis_ready / visualization_ready）
  - `suggestion_status`：建议状态（pending / accepted / rejected / skipped）
  - `active_version_id`：当前使用的数据版本标识
  - `created_at` / `updated_at`
- **约束**:
  - 一个任务必须且仅能绑定一个当前数据版本。
  - 默认仅创建者可访问，显式分享后团队可访问。

### 2) 数据集

- **含义**: 用户上传的数据集合。
- **关键字段**:
  - `id`：唯一标识
  - `owner_id`：创建者标识
  - `name`：名称
  - `schema_summary`：字段与类型概要
  - `row_count` / `column_count`
  - `created_at`
- **约束**:
  - 同一用户下数据集名称可重复，但 `id` 全局唯一。

### 3) 数据版本

- **含义**: 数据集的处理版本（原始/默认/建议/自定义）。
- **关键字段**:
  - `id`：唯一标识
  - `dataset_id`：所属数据集
  - `source_type`：raw / default / ai / custom
  - `transformations`：处理步骤摘要
  - `row_count` / `column_count`
  - `created_at`
  - `expires_at`：保留截止时间（默认 30 天）
- **约束**:
  - `dataset_id + source_type + created_at` 组合需可区分版本。

### 4) 图表

- **含义**: 任务下的可视化产物。
- **关键字段**:
  - `id`：唯一标识
  - `task_id`：所属任务
  - `dataset_version_id`：绑定数据版本
  - `chart_type`：图表类型
  - `config_id`：图表配置标识
  - `render_log`：渲染记录摘要
  - `created_at` / `updated_at`
- **约束**:
  - 单任务图表数量受上限约束（可配置）。

### 5) 图表配置

- **含义**: 语义、样式与导出规则的统一配置。
- **关键字段**:
  - `id`：唯一标识
  - `semantic_config`：语义配置
  - `style_config`：风格配置
  - `export_config`：导出配置
  - `version`：配置版本
  - `created_at` / `updated_at`

### 6) AI 建议

- **含义**: 对任务的结构化分析建议。
- **关键字段**:
  - `id`：唯一标识
  - `task_id`：所属任务
  - `payload`：清洗/统计/图表/注意事项
  - `status`：pending / accepted / rejected
  - `created_at`

### 7) 任务分享

- **含义**: 任务与分享包的显式授权记录。
- **关键字段**:
  - `id`：唯一标识
  - `task_id`：所属任务
  - `member_id`：被分享成员标识
  - `permission`：访问权限（view / edit）
  - `created_at`
  - `expires_at`：可选到期时间
- **约束**:
  - 默认仅创建者可访问，必须存在显式分享记录才可被他人访问。

### 8) 分享包

- **含义**: 用于复现与分享的打包对象。
- **关键字段**:
  - `id`：唯一标识
  - `visualization_id`：关联图表
  - `dataset_version_ref`：数据版本引用（不含原始数据）
  - `config_snapshot`：配置快照
  - `render_log_snapshot`：渲染记录快照
  - `created_at`
  - `expires_at`：保留截止时间（默认 30 天）

## 关系

- 数据集 1 —— * 数据版本
- 分析任务 1 —— * 图表
- 图表 1 —— 1 图表配置（可复用配置生成新图表）
- 分析任务 1 —— 0..1 AI 建议
- 分析任务 1 —— * 任务分享
- 图表 1 —— 0..* 分享包

## 状态与生命周期

- **任务阶段**: uploading → parsed → profiling → suggestion_pending → processing → analysis_ready → visualization_ready。
- **数据版本**: 新建 → 使用中 → 过期/归档（默认 30 天）。
- **分享包**: 生成 → 使用中 → 过期/撤销。
