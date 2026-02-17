## ADDED Requirements

### Requirement: 图片识别技能使用用途路由模型
系统 SHALL 让 `image_analysis` 技能通过统一模型路由器调用视觉模型，并使用 `image_analysis` 用途对应的首选模型配置。

#### Scenario: 图片识别使用用途配置
- **WHEN** 用户在用途路由中为 `image_analysis` 设置了首选提供商
- **THEN** 图片识别技能调用模型时优先使用该提供商
- **AND** 不再硬编码固定提供商/模型

#### Scenario: 图片识别在无用途配置时可回退
- **WHEN** 用户未设置 `image_analysis` 用途首选提供商
- **THEN** 图片识别技能按全局首选与默认优先级回退
- **AND** 在无可用模型时返回清晰错误信息
