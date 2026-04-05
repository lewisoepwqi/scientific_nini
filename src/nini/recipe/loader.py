"""Recipe 配置加载器与规则分类。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from nini.config import settings


class RecipeInputField(BaseModel):
    """Recipe 输入字段定义。"""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    required: bool = True
    placeholder: str = ""
    example: str = ""


class RecipeStep(BaseModel):
    """Recipe 步骤定义。"""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""


class RecipeOutput(BaseModel):
    """Recipe 默认输出定义。"""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: str = Field(min_length=1)


class RecipeRecoveryRule(BaseModel):
    """Recipe 最小恢复策略。"""

    max_retries: int = Field(default=1, ge=0, le=3)
    user_hint: str = ""
    fallback_action: str = ""


class RecipeDefinition(BaseModel):
    """Recipe 元数据定义。"""

    recipe_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    scenario: str = ""
    example_input: str = ""
    recommended_triggers: list[str] = Field(default_factory=list)
    deep_task_keywords: list[str] = Field(default_factory=list)
    input_fields: list[RecipeInputField] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(min_length=3)
    default_outputs: list[RecipeOutput] = Field(default_factory=list)
    recovery: RecipeRecoveryRule = Field(default_factory=RecipeRecoveryRule)
    starter_prompt_template: str = Field(min_length=1)

    def to_public_dict(self) -> dict[str, Any]:
        """输出前端可直接消费的公开字段。"""
        return {
            "recipe_id": self.recipe_id,
            "name": self.name,
            "summary": self.summary,
            "scenario": self.scenario,
            "example_input": self.example_input,
            "recommended_triggers": self.recommended_triggers,
            "input_fields": [field.model_dump() for field in self.input_fields],
            "steps": [step.model_dump() for step in self.steps],
            "default_outputs": [output.model_dump() for output in self.default_outputs],
            "recovery": self.recovery.model_dump(),
        }

    def render_prompt(
        self,
        user_request: str,
        recipe_inputs: dict[str, Any] | None = None,
    ) -> str:
        """将用户输入渲染为带 Recipe 上下文的提示。"""
        normalized_inputs = recipe_inputs or {}
        input_lines: list[str] = []
        for field in self.input_fields:
            raw_value = normalized_inputs.get(field.key)
            value = str(raw_value or "").strip()
            if value:
                input_lines.append(f"- {field.label}: {value}")
        if not input_lines:
            input_lines.append("- 未提供结构化补充输入，请结合原始请求自行补足必要上下文。")

        step_lines = [
            f"{index}. {step.title}：{step.description}"
            for index, step in enumerate(self.steps, start=1)
        ]
        output_lines = [
            f"- {output.label}（{output.type}）" for output in self.default_outputs
        ] or ["- 输出结构化结果并说明下一步建议"]

        return self.starter_prompt_template.format(
            recipe_name=self.name,
            user_request=user_request.strip(),
            input_bullets="\n".join(input_lines),
            step_bullets="\n".join(step_lines),
            output_bullets="\n".join(output_lines),
            fallback_hint=self.recovery.user_hint or "请在失败时说明阻塞点并给出用户下一步建议。",
        ).strip()


class RecipeRegistry:
    """Recipe 配置注册表。"""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self._recipes: dict[str, RecipeDefinition] = {}
        self.reload()

    def reload(self) -> None:
        """重新加载全部 Recipe 配置。"""
        if not self.config_dir.exists():
            raise FileNotFoundError(f"Recipe 配置目录不存在: {self.config_dir}")

        recipes: dict[str, RecipeDefinition] = {}
        for path in sorted(self.config_dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(payload, dict):
                raise ValueError(f"Recipe 配置必须是对象: {path}")
            try:
                recipe = RecipeDefinition.model_validate(payload)
            except ValidationError as exc:
                raise ValueError(f"Recipe 配置校验失败: {path}") from exc
            if recipe.recipe_id in recipes:
                raise ValueError(f"重复的 recipe_id: {recipe.recipe_id}")
            recipes[recipe.recipe_id] = recipe

        if len(recipes) < 3:
            raise ValueError("Recipe Center MVP 至少需要 3 个 Recipe")
        self._recipes = recipes

    def list_public(self) -> list[dict[str, Any]]:
        """返回公开 Recipe 列表。"""
        return [recipe.to_public_dict() for recipe in self._recipes.values()]

    def get(self, recipe_id: str | None) -> RecipeDefinition | None:
        """获取单个 Recipe。"""
        if not recipe_id:
            return None
        return self._recipes.get(recipe_id)

    def match_recommendation(self, content: str) -> RecipeDefinition | None:
        """按规则推荐最匹配的 Recipe。"""
        normalized = str(content or "").strip().lower()
        if not normalized:
            return None

        best_recipe: RecipeDefinition | None = None
        best_score = 0
        for recipe in self._recipes.values():
            score = 0
            for trigger in recipe.recommended_triggers:
                token = trigger.strip().lower()
                if token and token in normalized:
                    score += 3
            for keyword in recipe.deep_task_keywords:
                token = keyword.strip().lower()
                if token and token in normalized:
                    score += 1
            if score > best_score:
                best_recipe = recipe
                best_score = score
        return best_recipe if best_score > 0 else None


def classify_task_request(
    content: str,
    *,
    explicit_recipe: RecipeDefinition | None,
    registry: RecipeRegistry,
) -> dict[str, Any]:
    """规则优先的 quick/deep task 分类。"""
    normalized = str(content or "").strip()
    if explicit_recipe is not None:
        return {
            "task_kind": "deep_task",
            "recipe_id": explicit_recipe.recipe_id,
            "recommended_recipe_id": explicit_recipe.recipe_id,
            "classification_reason": "explicit_recipe",
        }

    recommended = registry.match_recommendation(normalized)
    if recommended is not None:
        return {
            "task_kind": "quick_task",
            "recipe_id": None,
            "recommended_recipe_id": recommended.recipe_id,
            "classification_reason": "rule_match",
        }

    return {
        "task_kind": "quick_task",
        "recipe_id": None,
        "recommended_recipe_id": None,
        "classification_reason": "rule_default",
    }


@lru_cache(maxsize=1)
def get_recipe_registry() -> RecipeRegistry:
    """返回全局 Recipe 注册表。"""
    return RecipeRegistry(settings.recipes_dir)
