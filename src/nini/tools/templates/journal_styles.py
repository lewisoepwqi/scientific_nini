"""期刊样式模板定义，支持从 YAML 文件动态加载。

本模块提供6种内置期刊模板（Nature, Science, Cell, NEJM, Lancet）的动态加载功能，
支持从 YAML 配置文件读取模板设置，并允许用户上传自定义模板。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.utils.chart_fonts import CJK_FONT_FAMILY

logger = logging.getLogger(__name__)

# 默认模板配置（作为回退）
_DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "默认模板",
        "font": CJK_FONT_FAMILY,
        "font_size": 12,
        "line_width": 1.5,
        "dpi": 300,
        "figure_size": [6.4, 4.8],
        "colors": [
            "#636EFA",
            "#EF553B",
            "#00CC96",
            "#AB63FA",
            "#FFA15A",
            "#19D3F3",
            "#FF6692",
            "#B6E880",
            "#FF97FF",
            "#FECB52",
        ],
    },
    "nature": {
        "name": "Nature",
        "font": CJK_FONT_FAMILY,
        "font_size": 11,
        "line_width": 1.2,
        "dpi": 300,
        "figure_size": [3.54, 2.76],
        "colors": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"],
    },
    "science": {
        "name": "Science",
        "font": CJK_FONT_FAMILY,
        "font_size": 12,
        "line_width": 1.2,
        "dpi": 300,
        "figure_size": [3.54, 2.76],
        "colors": ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B"],
    },
    "cell": {
        "name": "Cell",
        "font": CJK_FONT_FAMILY,
        "font_size": 11,
        "line_width": 1.0,
        "dpi": 300,
        "figure_size": [3.54, 2.76],
        "colors": ["#E41A1C", "#377EB8", "#4DAF4A", "#984EA3", "#FF7F00", "#FFFF33"],
    },
    "nejm": {
        "name": "NEJM",
        "font": CJK_FONT_FAMILY,
        "font_size": 10,
        "line_width": 1.0,
        "dpi": 300,
        "figure_size": [3.54, 2.76],
        "colors": ["#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD"],
    },
    "lancet": {
        "name": "Lancet",
        "font": CJK_FONT_FAMILY,
        "font_size": 10,
        "line_width": 1.0,
        "dpi": 300,
        "figure_size": [3.54, 2.76],
        "colors": ["#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91"],
    },
}

# 项目/bundle 根目录（支持冻结模式）
from nini.config import _get_bundle_root

_ROOT = _get_bundle_root()

# 内置模板目录
_BUILTIN_TEMPLATES_DIR = _ROOT / "templates" / "journal_styles"

# 用户自定义模板目录（在 data_dir 下）
_USER_TEMPLATES_DIR = settings.data_dir / "templates" / "journal_styles"


def _get_templates_dir() -> Path:
    """获取用户自定义模板目录，确保目录存在。"""
    _USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return _USER_TEMPLATES_DIR


def _load_yaml_template(path: Path) -> dict[str, Any] | None:
    """从 YAML 文件加载单个模板配置。

    Args:
        path: YAML 文件路径

    Returns:
        模板配置字典，加载失败时返回 None
    """
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            logger.warning(f"模板文件格式错误: {path}")
            return None

        # 解析 YAML 格式
        style = data.get("style", {})
        template = {
            "name": data.get("name", path.stem),
            "font": style.get("font_family", CJK_FONT_FAMILY),
            "font_size": style.get("font_size", 12),
            "line_width": style.get("line_width", 1.5),
            "dpi": style.get("dpi", 300),
            "figure_size": style.get("figure_size", [6.4, 4.8]),
            "colors": data.get("colors", _DEFAULT_TEMPLATES["default"]["colors"]),
            "metadata": data.get("metadata", {}),
        }
        return template
    except Exception as exc:
        logger.warning(f"加载模板文件失败 {path}: {exc}")
        return None


def _load_all_yaml_templates() -> dict[str, dict[str, Any]]:
    """从所有模板目录加载 YAML 配置。

    加载顺序：
    1. 先加载内置模板（项目目录下的 templates/journal_styles/）
    2. 再加载用户自定义模板（data_dir 下的 templates/journal_styles/），允许覆盖内置模板

    Returns:
        模板名称到配置的映射字典
    """
    templates: dict[str, dict[str, Any]] = {}

    # 先加载内置模板
    if _BUILTIN_TEMPLATES_DIR.exists():
        for yaml_file in sorted(_BUILTIN_TEMPLATES_DIR.glob("*.yaml")):
            key = yaml_file.stem.lower()
            template = _load_yaml_template(yaml_file)
            if template:
                templates[key] = template

    # 再加载用户自定义模板（允许覆盖内置模板）
    user_dir = _get_templates_dir()
    if user_dir.exists():
        for yaml_file in sorted(user_dir.glob("*.yaml")):
            key = yaml_file.stem.lower()
            template = _load_yaml_template(yaml_file)
            if template:
                templates[key] = template
                logger.info(f"加载用户自定义模板: {key}")

    return templates


def _ensure_templates_loaded() -> dict[str, dict[str, Any]]:
    """确保模板已加载，返回模板字典。"""
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        yaml_templates = _load_all_yaml_templates()
        # 如果 YAML 加载失败或为空，使用默认配置
        if not yaml_templates:
            _TEMPLATES_CACHE = _DEFAULT_TEMPLATES.copy()
        else:
            # 确保 default 模板存在
            if "default" not in yaml_templates:
                yaml_templates["default"] = _DEFAULT_TEMPLATES["default"].copy()
            _TEMPLATES_CACHE = yaml_templates
    return _TEMPLATES_CACHE


# 模板缓存
_TEMPLATES_CACHE: dict[str, dict[str, Any]] | None = None


def get_templates() -> dict[str, dict[str, Any]]:
    """获取所有可用模板。

    Returns:
        模板名称到配置的映射字典
    """
    return _ensure_templates_loaded()


def get_template(style: str) -> dict[str, Any]:
    """获取模板配置，不存在时回退 default。

    Args:
        style: 模板名称（如 "nature", "science"）

    Returns:
        模板配置字典
    """
    templates = _ensure_templates_loaded()
    key = style.lower().strip()
    return templates.get(key, templates.get("default", _DEFAULT_TEMPLATES["default"]))


def get_template_names() -> list[str]:
    """获取所有可用模板名称列表。

    Returns:
        模板名称列表
    """
    return list(get_templates().keys())


def reload_templates() -> None:
    """重新加载所有模板（用于热更新）。"""
    global _TEMPLATES_CACHE
    _TEMPLATES_CACHE = None
    _ensure_templates_loaded()
    logger.info("模板已重新加载")


def save_custom_template(key: str, config: dict[str, Any]) -> bool:
    """保存用户自定义模板到 YAML 文件。

    Args:
        key: 模板标识符（如 "my_custom"）
        config: 模板配置字典

    Returns:
        是否保存成功
    """
    try:
        import yaml

        user_dir = _get_templates_dir()
        file_path = user_dir / f"{key.lower()}.yaml"

        # 构建 YAML 格式
        yaml_data = {
            "name": config.get("name", key),
            "key": key.lower(),
            "style": {
                "font_family": config.get("font", CJK_FONT_FAMILY),
                "font_size": config.get("font_size", 12),
                "line_width": config.get("line_width", 1.5),
                "dpi": config.get("dpi", 300),
                "figure_size": config.get("figure_size", [6.4, 4.8]),
            },
            "colors": config.get("colors", _DEFAULT_TEMPLATES["default"]["colors"]),
            "metadata": {
                **config.get("metadata", {}),
                "is_custom": True,
                "created_at": str(
                    __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                ),
            },
        }

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        # 刷新缓存
        reload_templates()
        logger.info(f"自定义模板已保存: {key}")
        return True
    except Exception as exc:
        logger.error(f"保存自定义模板失败 {key}: {exc}")
        return False


def delete_custom_template(key: str) -> bool:
    """删除用户自定义模板。

    Args:
        key: 模板标识符

    Returns:
        是否删除成功
    """
    try:
        user_dir = _get_templates_dir()
        file_path = user_dir / f"{key.lower()}.yaml"

        if not file_path.exists():
            logger.warning(f"模板不存在: {key}")
            return False

        file_path.unlink()
        reload_templates()
        logger.info(f"自定义模板已删除: {key}")
        return True
    except Exception as exc:
        logger.error(f"删除自定义模板失败 {key}: {exc}")
        return False


def get_template_info(key: str) -> dict[str, Any] | None:
    """获取模板的详细信息（包括元数据）。

    Args:
        key: 模板标识符

    Returns:
        模板信息字典，不存在时返回 None
    """
    templates = get_templates()
    key = key.lower().strip()
    if key not in templates:
        return None

    template = templates[key]
    return {
        "key": key,
        "name": template.get("name", key),
        "font_size": template.get("font_size", 12),
        "line_width": template.get("line_width", 1.5),
        "dpi": template.get("dpi", 300),
        "figure_size": template.get("figure_size", [6.4, 4.8]),
        "colors": template.get("colors", []),
        "metadata": template.get("metadata", {}),
        "is_builtin": key in _DEFAULT_TEMPLATES
        and not template.get("metadata", {}).get("is_custom", False),
    }


# 向后兼容：保持 TEMPLATES 字典可直接访问
TEMPLATES: dict[str, dict[str, Any]] = _DEFAULT_TEMPLATES


def _init_templates() -> None:
    """初始化模板系统，加载 YAML 配置。"""
    global TEMPLATES
    TEMPLATES = get_templates()


# 模块加载时初始化
_init_templates()
