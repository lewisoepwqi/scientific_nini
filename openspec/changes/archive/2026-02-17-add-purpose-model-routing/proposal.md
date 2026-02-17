# Change: 支持按用途配置模型路由（含图片识别）

## Why

当前系统仅支持“全局首选提供商”，无法针对不同用途（如对话、标题生成、图片识别）分别配置模型。  
这会导致以下问题：

1. 图片识别能力被硬编码为 OpenAI，无法在页面切换到其他已配置模型。
2. 标题生成与主对话共用同一模型，难以平衡成本、速度与稳定性。
3. 用户无法在 UI 中直观管理“用途 -> 模型”的路由策略。

## What Changes

- 新增用途级模型路由配置：`chat`、`title_generation`、`image_analysis`。
- 后端模型路由器支持用途优先级：`用途首选 > 全局首选 > 默认可用顺序`。
- 图片识别技能改为走统一模型路由，不再硬编码 OpenAI。
- 新增用途路由 API（查询/保存），并在模型配置页面提供可视化配置。
- 保持现有全局首选 API 兼容，不破坏已有调用方式。

## Impact

- Affected specs:
  - `conversation`（模型路由与标题生成）
  - `skills`（图片识别模型选择）
- Affected code:
  - `src/nini/config_manager.py`
  - `src/nini/agent/model_resolver.py`
  - `src/nini/api/routes.py`
  - `src/nini/models/schemas.py`
  - `src/nini/skills/image_analysis.py`
  - `src/nini/agent/title_generator.py`
  - `src/nini/agent/runner.py`
  - `web/src/components/ModelConfigPanel.tsx`
  - `tests/test_phase5_model_resolver.py`
  - `tests/test_model_config_manager.py`
  - `tests/test_image_analysis.py`
