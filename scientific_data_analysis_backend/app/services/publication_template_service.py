"""
出版级模板校验服务。
"""
from typing import Dict, Any

from app.core.publication_templates import TEMPLATES


class PublicationTemplateService:
    """模板校验服务。"""

    def validate_template(self, template_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """校验模板是否存在并返回校验结果。"""
        template = TEMPLATES.get(template_id)
        if not template:
            return {"valid": False, "reason": "模板不存在"}

        _ = config
        return {"valid": True, "template": template}


publication_template_service = PublicationTemplateService()
