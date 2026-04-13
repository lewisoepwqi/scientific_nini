"""模型配置管理器（门面模块）。

此模块作为对外接口，将实现委托给三个内部子模块：
- _config_model_crud: 模型配置 CRUD 操作
- _config_usage: 内置用量追踪
- _config_trial: 试用模式管理
"""

from __future__ import annotations

from nini._config_model_crud import (  # noqa: F401
    API_MODE_CODING_PLAN,
    API_MODE_STANDARD,
    BUILTIN_PROVIDER_ID,
    DEFAULT_BASE_URLS_BY_PROVIDER_MODE,
    DEFAULT_MODELS_BY_PROVIDER_MODE,
    MODEL_PURPOSES,
    PROVIDER_PRIORITY_ORDER,
    SUPPORTED_API_MODES_BY_PROVIDER,
    VALID_MODEL_PURPOSES,
    VALID_PROVIDERS,
    VALID_ROUTE_PROVIDERS,
    ModelPurposeRoute,
    _ensure_app_settings_table,
    get_active_provider_id,
    get_all_effective_configs,
    get_default_base_url_for_mode,
    get_default_model_for_mode,
    get_default_provider,
    get_effective_config,
    get_model_priorities,
    get_model_purpose_routes,
    get_purpose_provider_routes,
    has_material_model_config,
    infer_api_mode_from_base_url,
    list_user_configured_provider_ids,
    load_all_model_configs,
    normalize_api_mode,
    remove_model_config,
    save_model_config,
    set_active_provider,
    set_default_provider,
    set_model_priorities,
    set_model_purpose_routes,
    set_purpose_provider_routes,
)
from nini._config_usage import (  # noqa: F401
    get_builtin_usage,
    increment_builtin_usage,
    is_builtin_exhausted,
)
from nini._config_trial import (  # noqa: F401
    activate_trial,
    get_trial_status,
)
