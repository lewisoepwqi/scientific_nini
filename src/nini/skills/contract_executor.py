"""Markdown Contract Skill 的真实执行器。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import uuid
from typing import Any, Mapping

from nini.models.risk import OutputLevel, TRUST_CEILING_MAP, TrustLevel
from nini.models.skill_contract import ContractResult, SkillContract, SkillStep
from nini.skills.contract_runner import ContractRunner, EventCallback

logger = logging.getLogger(__name__)

_STEP_HEADING_RE = re.compile(r"(?m)^##+\s+.*?[（(]([A-Za-z][A-Za-z0-9_-]*)[）)]\s*$")
_PROMPT_TEMPLATE_RE = re.compile(r"(?ms)^###\s+LLM 提示模板\s*\n+```(?:\w+)?\n(.*?)\n```")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
_JSON_BLOCK_RE = re.compile(r"(?s)\{.*\}")
_NON_EXECUTABLE_TOOL_HINTS = frozenset({"task_write", "task_state"})
_MAX_STEP_PROMPT_CHARS = 8000


@dataclass(slots=True)
class _StepInstruction:
    """单个 step 对应的正文片段。"""

    heading: str
    body: str
    prompt_template: str | None


@dataclass(slots=True)
class ContractExecutionOutcome:
    """Contract Skill 执行结果。"""

    contract_result: ContractResult
    final_text: str
    output_level: OutputLevel | None


class ContractSkillExecutor:
    """将 Markdown Skill 正文和 SkillContract 绑定成可执行工作流。"""

    def __init__(
        self,
        *,
        skill_name: str,
        instruction: str,
        contract: SkillContract,
        tool_registry: Any,
        resolver: Any,
        callback: EventCallback,
    ) -> None:
        self._skill_name = skill_name
        self._instruction = instruction
        self._contract = contract
        self._tool_registry = tool_registry
        self._resolver = resolver
        self._callback = callback
        self._shared_context, self._step_instructions = self._parse_instruction(instruction)

    async def execute(
        self,
        *,
        session: Any,
        user_message: str,
        skill_arguments: str = "",
    ) -> ContractExecutionOutcome:
        """执行完整 contract，并返回最终文本。"""
        runner = ContractRunner(
            contract=self._contract,
            skill_name=self._skill_name,
            callback=self._callback,
        )
        runner._step_executor = self._execute_step  # type: ignore[attr-defined]

        initial_inputs = self._build_initial_inputs(
            user_message=user_message,
            skill_arguments=skill_arguments,
        )

        if session is not None:
            setattr(session, "_active_contract_runner", runner)
        try:
            contract_result = await runner.run(session=session, inputs=initial_inputs)
        finally:
            if session is not None and getattr(session, "_active_contract_runner", None) is runner:
                setattr(session, "_active_contract_runner", None)

        final_step_id = self._contract.steps[-1].id if self._contract.steps else ""
        final_output = runner.get_step_output(final_step_id)
        final_text = self._stringify_step_output(final_output).strip()
        output_level = self._infer_output_level(final_text)

        if not final_text:
            final_text = self._build_fallback_text(contract_result)
        return ContractExecutionOutcome(
            contract_result=contract_result,
            final_text=final_text,
            output_level=output_level,
        )

    async def _execute_step(
        self,
        step: SkillStep,
        session: Any,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """执行单个 step。"""
        if self._should_execute_tool(step):
            return await self._execute_tool_step(step, session, inputs)
        return await self._execute_llm_step(step, inputs)

    def _should_execute_tool(self, step: SkillStep) -> bool:
        """判断当前 step 是否应走真实工具调用。"""
        tool_name = str(step.tool_hint or "").strip()
        if not tool_name or tool_name in _NON_EXECUTABLE_TOOL_HINTS:
            return False
        if self._tool_registry is None or not hasattr(self._tool_registry, "get"):
            return False
        return self._tool_registry.get(tool_name) is not None

    async def _execute_tool_step(
        self,
        step: SkillStep,
        session: Any,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """先生成工具参数，再走真实工具执行。"""
        tool_name = str(step.tool_hint or "").strip()
        tool = self._tool_registry.get(tool_name) if self._tool_registry is not None else None
        if tool is None:
            raise RuntimeError(f"工具 {tool_name} 未注册，无法执行 contract step")

        tool_definition = tool.get_tool_definition()
        planned_arguments = await self._plan_tool_arguments(
            step=step,
            tool_definition=tool_definition,
            inputs=inputs,
        )

        if session is not None:
            tool_call_id = f"contract-{step.id}-{uuid.uuid4().hex[:8]}"
            session.add_tool_call(
                tool_call_id,
                tool_name,
                json.dumps(planned_arguments, ensure_ascii=False),
            )
        else:
            tool_call_id = ""

        result = await self._tool_registry.execute_with_fallback(
            tool_name,
            session=session,
            **planned_arguments,
        )
        if not isinstance(result, dict):
            result = {"success": False, "message": f"工具 {tool_name} 返回了非法结果"}

        serialized_result = json.dumps(result, ensure_ascii=False, default=str)
        if session is not None and tool_call_id:
            session.add_tool_result(
                tool_call_id,
                serialized_result,
                tool_name=tool_name,
                status="success" if result.get("success", False) else "error",
            )

        summary_text = self._summarize_tool_result(result)
        payload = dict(result)
        payload.setdefault("content", summary_text)
        if summary_text and "message" not in payload:
            payload["message"] = summary_text
        output_level = self._infer_output_level(summary_text)
        if output_level is not None:
            payload.setdefault("output_level", output_level.value)
        return payload

    async def _execute_llm_step(
        self,
        step: SkillStep,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """执行纯 LLM step。"""
        prompt = self._build_llm_step_prompt(step, inputs)
        response = await self._chat_complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你正在执行一个已结构化的 Markdown Contract Skill。"
                        "当前只允许完成指定步骤，不得跳到未来步骤。"
                        "输出应保持中文，并显式保留不确定项。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            purpose="analysis",
            temperature=0.2,
            max_tokens=2200,
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise RuntimeError(f"步骤 {step.id} 未生成任何文本输出")

        output_level = self._infer_output_level(text)
        payload: dict[str, Any] = {
            "success": True,
            "content": text,
            "message": text,
            "data": {"text": text},
        }
        if output_level is not None:
            payload["output_level"] = output_level.value
        return payload

    async def _plan_tool_arguments(
        self,
        *,
        step: SkillStep,
        tool_definition: dict[str, Any],
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """调用模型为工具 step 生成参数。"""
        tool_name = str(tool_definition.get("function", {}).get("name", "")).strip()
        schema = tool_definition.get("function", {}).get("parameters", {})
        prompt = self._build_tool_arguments_prompt(step=step, tool_name=tool_name, inputs=inputs)

        response = await self._chat_complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 contract skill 的工具参数规划器。"
                        "如果工具无参数，返回空对象；如果参数缺失，优先使用技能文档中的默认建议。"
                        "不要输出解释，只返回工具调用或 JSON。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            tools=[tool_definition],
            purpose="analysis",
            temperature=0.0,
            max_tokens=1200,
        )

        tool_calls = getattr(response, "tool_calls", []) or []
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            function_info = item.get("function")
            if not isinstance(function_info, dict):
                continue
            if str(function_info.get("name", "")).strip() != tool_name:
                continue
            raw_arguments = function_info.get("arguments")
            if isinstance(raw_arguments, str) and raw_arguments.strip():
                try:
                    parsed = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"工具 {tool_name} 的参数 JSON 解析失败: {exc}") from exc
                if isinstance(parsed, dict):
                    return parsed

        raw_text = str(getattr(response, "text", "") or "").strip()
        if raw_text:
            parsed = self._extract_json_object(raw_text)
            if isinstance(parsed, dict):
                return parsed

        if isinstance(schema, dict) and not schema.get("required"):
            return {}
        raise RuntimeError(f"步骤 {step.id} 未生成工具 {tool_name} 的有效参数")

    def _build_tool_arguments_prompt(
        self,
        *,
        step: SkillStep,
        tool_name: str,
        inputs: dict[str, Any],
    ) -> str:
        """构造工具参数生成提示。"""
        step_instruction = self._step_instructions.get(step.id)
        rendered_template = self._render_step_prompt_template(step, inputs)
        known_context = self._format_known_context(inputs)
        sections = [
            f"Skill: {self._skill_name}",
            f"当前步骤: {step.name} ({step.id})",
            f"工具: {tool_name}",
            f"步骤描述: {step.description}",
            "已知上下文：",
            known_context,
        ]
        if self._shared_context:
            sections.extend(["Skill 全局约束：", self._truncate_text(self._shared_context)])
        if step_instruction is not None and step_instruction.body:
            sections.extend(
                [
                    "当前步骤正文：",
                    self._truncate_text(step_instruction.body),
                ]
            )
        if rendered_template:
            sections.extend(
                [
                    "已渲染的步骤提示模板：",
                    self._truncate_text(rendered_template),
                ]
            )
        sections.append(
            "请只为当前步骤生成一次工具调用参数。"
            "若技能文档提供默认值，可直接采用；不要为未知事实捏造精确数字。"
        )
        return "\n\n".join(sections)

    def _build_llm_step_prompt(self, step: SkillStep, inputs: dict[str, Any]) -> str:
        """构造纯 LLM step 的提示。"""
        step_instruction = self._step_instructions.get(step.id)
        rendered_template = self._render_step_prompt_template(step, inputs)
        known_context = self._format_known_context(inputs)
        sections = [
            f"Skill: {self._skill_name}",
            f"当前步骤: {step.name} ({step.id})",
            f"步骤描述: {step.description}",
            "已知上下文：",
            known_context,
        ]
        if self._shared_context:
            sections.extend(["Skill 全局约束：", self._truncate_text(self._shared_context)])
        if step_instruction is not None and step_instruction.body:
            sections.extend(["当前步骤正文：", self._truncate_text(step_instruction.body)])
        if rendered_template:
            sections.extend(["已渲染的步骤提示模板：", self._truncate_text(rendered_template)])
        sections.append(
            "请只完成当前步骤，输出可被后续步骤继续引用的草稿结果。"
            "如果存在待确认项，必须明确标注，不得伪装成已验证结论。"
        )
        return "\n\n".join(sections)

    async def _chat_complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        purpose: str,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """兼容仅实现 chat() 的测试解析器。"""
        if hasattr(self._resolver, "chat_complete"):
            return await self._resolver.chat_complete(
                messages,
                tools=tools,
                purpose=purpose,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        async for chunk in self._resolver.chat(
            messages,
            tools=tools,
            purpose=purpose,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            text_parts.append(str(getattr(chunk, "text", "") or ""))
            raw_tool_calls = getattr(chunk, "tool_calls", []) or []
            if isinstance(raw_tool_calls, list):
                tool_calls.extend(item for item in raw_tool_calls if isinstance(item, dict))

        @dataclass(slots=True)
        class _CompatResponse:
            text: str
            tool_calls: list[dict[str, Any]]

        return _CompatResponse(text="".join(text_parts), tool_calls=tool_calls)

    def _build_initial_inputs(
        self,
        *,
        user_message: str,
        skill_arguments: str,
    ) -> dict[str, Any]:
        """构造 contract 初始输入。"""
        normalized_arguments = skill_arguments.strip() or user_message.strip()
        inputs: dict[str, Any] = {
            "user_message": user_message,
            "skill_arguments": normalized_arguments,
            "request": normalized_arguments,
        }

        properties = self._contract.input_schema.get("properties")
        if isinstance(properties, dict):
            for field_name, field_schema in properties.items():
                if field_name in inputs:
                    continue
                if not isinstance(field_schema, dict):
                    continue
                field_type = str(field_schema.get("type", "")).strip()
                if field_type == "string":
                    inputs[field_name] = normalized_arguments
                elif field_type == "array":
                    inputs[field_name] = []
        return inputs

    def _format_known_context(self, inputs: dict[str, Any]) -> str:
        """将 step 上下文格式化为稳定文本。"""
        step_outputs = inputs.get("_contract_step_outputs")
        output_aliases = inputs.get("_contract_output_aliases")
        base_inputs = {
            key: value for key, value in inputs.items() if not key.startswith("_contract_")
        }
        payload = {
            "inputs": base_inputs,
            "completed_steps": {
                key: self._stringify_step_output(value)
                for key, value in (
                    step_outputs.items() if isinstance(step_outputs, Mapping) else []
                )
            },
            "output_aliases": {
                key: self._stringify_step_output(value)
                for key, value in (
                    output_aliases.items() if isinstance(output_aliases, Mapping) else []
                )
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _render_step_prompt_template(self, step: SkillStep, inputs: dict[str, Any]) -> str:
        """根据已完成步骤结果渲染当前 step 的正文模板。"""
        step_instruction = self._step_instructions.get(step.id)
        if step_instruction is None or not step_instruction.prompt_template:
            return ""

        template_values: dict[str, str] = {}
        for key, value in inputs.items():
            if key.startswith("_contract_"):
                continue
            template_values[key] = self._stringify_value(value)

        step_outputs = inputs.get("_contract_step_outputs")
        if isinstance(step_outputs, Mapping):
            for step_id, value in step_outputs.items():
                template_values[str(step_id)] = self._stringify_step_output(value)
                template_values[f"{step_id}_output"] = self._stringify_step_output(value)

        output_aliases = inputs.get("_contract_output_aliases")
        if isinstance(output_aliases, Mapping):
            for key, value in output_aliases.items():
                template_values[str(key)] = self._stringify_step_output(value)
                template_values[f"{key}_output"] = self._stringify_step_output(value)

        return _PLACEHOLDER_RE.sub(
            lambda match: template_values.get(match.group(1), match.group(0)),
            step_instruction.prompt_template,
        )

    @classmethod
    def _parse_instruction(cls, instruction: str) -> tuple[str, dict[str, _StepInstruction]]:
        """解析共享上下文与 step 级正文。"""
        stripped = str(instruction or "").strip()
        matches = list(_STEP_HEADING_RE.finditer(stripped))
        if not matches:
            return stripped, {}

        shared_context = stripped[: matches[0].start()].strip()
        parsed_steps: dict[str, _StepInstruction] = {}
        for index, match in enumerate(matches):
            step_id = match.group(1).strip()
            section_start = match.start()
            section_end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
            section_text = stripped[section_start:section_end].strip()
            prompt_match = _PROMPT_TEMPLATE_RE.search(section_text)
            parsed_steps[step_id] = _StepInstruction(
                heading=match.group(0).strip(),
                body=section_text,
                prompt_template=prompt_match.group(1).strip() if prompt_match else None,
            )
        return shared_context, parsed_steps

    def _build_fallback_text(self, contract_result: ContractResult) -> str:
        """当最后一步未产出文本时给出稳定降级说明。"""
        if contract_result.status == "completed":
            return f"{self._skill_name} 已完成，但最后一步未生成可展示文本。"
        if contract_result.error_message:
            return f"{self._skill_name} 执行未完成：{contract_result.error_message}"
        return f"{self._skill_name} 执行状态：{contract_result.status}"

    def _summarize_tool_result(self, result: Mapping[str, Any]) -> str:
        """将工具结果压缩为适合后续 step 继续引用的文本。"""
        message = str(result.get("message", "") or "").strip()
        data = result.get("data")
        if isinstance(data, Mapping):
            compact = json.dumps(data, ensure_ascii=False, default=str)
            if message and compact:
                return f"{message}\n{compact}"
            if compact:
                return compact
        return message or json.dumps(result, ensure_ascii=False, default=str)

    def _stringify_step_output(self, value: Any) -> str:
        """将 step 输出转换为模板可复用文本。"""
        if isinstance(value, Mapping):
            for key in ("content", "message", "text"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            data = value.get("data")
            if isinstance(data, Mapping):
                for key in ("text", "summary", "message"):
                    candidate = data.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
                return json.dumps(data, ensure_ascii=False, default=str)
            return json.dumps(value, ensure_ascii=False, default=str)
        return self._stringify_value(value)

    @staticmethod
    def _stringify_value(value: Any) -> str:
        """将任意值稳定转成文本。"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        return json.dumps(value, ensure_ascii=False, default=str)

    def _infer_output_level(self, text: str) -> OutputLevel | None:
        """从文本或 trust ceiling 推断输出等级。"""
        normalized = str(text or "").lower()
        for level in OutputLevel:
            if level.value in normalized:
                return level

        allowed_levels = TRUST_CEILING_MAP.get(self._contract.trust_ceiling, [])
        return allowed_levels[-1] if allowed_levels else None

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        """从文本中提取首个 JSON 对象。"""
        match = _JSON_BLOCK_RE.search(text)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("contract 工具参数解析失败，原始文本=%s", text)
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _truncate_text(text: str) -> str:
        """控制注入模型的上下文长度。"""
        normalized = str(text or "").strip()
        if len(normalized) <= _MAX_STEP_PROMPT_CHARS:
            return normalized
        return normalized[:_MAX_STEP_PROMPT_CHARS] + "...(截断)"
