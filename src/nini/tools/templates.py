"""出版级模板定义，支持从 YAML 文件动态加载。

向后兼容模块：请使用 nini.tools.templates.journal_styles 或从 nini.tools.templates 导入。
"""

# 从新的位置重新导出所有功能，保持向后兼容
from nini.tools.templates.journal_styles import (  # noqa: F401
    TEMPLATES,
    delete_custom_template,
    get_template,
    get_template_info,
    get_template_names,
    get_templates,
    reload_templates,
    save_custom_template,
)
