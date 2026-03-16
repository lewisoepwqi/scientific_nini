"""重建并检查发送给智谱的 messages 负载。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from nini.agent.runner import AgentRunner
from nini.agent.session import Session
from nini.agent.providers.chinese_providers import ZhipuClient
from nini.agent.providers.openai_provider import summarize_messages_for_debug
from nini.config import settings
from nini.config_manager import (
    get_default_model_for_mode,
    get_effective_config,
    infer_api_mode_from_base_url,
)


def _collect_raw_tool_call_issues(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """扫描原始会话消息中的 tool_call 附加字段。"""
    issues: list[dict[str, Any]] = []
    for message_index, message in enumerate(messages, start=1):
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_index, tool_call in enumerate(tool_calls, start=1):
            if not isinstance(tool_call, dict):
                issues.append(
                    {
                        "message_index": message_index,
                        "tool_index": tool_index,
                        "issue": "tool_call 不是对象",
                    }
                )
                continue

            extra_keys = sorted(
                key for key in tool_call.keys() if key not in {"id", "type", "function"}
            )
            function_raw = tool_call.get("function")
            function_extra_keys: list[str] = []
            if isinstance(function_raw, dict):
                function_extra_keys = sorted(
                    key for key in function_raw.keys() if key not in {"name", "arguments"}
                )
            elif function_raw is not None:
                issues.append(
                    {
                        "message_index": message_index,
                        "tool_index": tool_index,
                        "issue": "function 字段不是对象",
                    }
                )
                continue

            if extra_keys or function_extra_keys:
                issues.append(
                    {
                        "message_index": message_index,
                        "tool_index": tool_index,
                        "tool_call_id": str(tool_call.get("id") or "").strip(),
                        "tool_name": (
                            str(function_raw.get("name") or "").strip()
                            if isinstance(function_raw, dict)
                            else ""
                        ),
                        "tool_call_extra_keys": extra_keys,
                        "function_extra_keys": function_extra_keys,
                    }
                )
    return issues


async def _build_messages(session_id: str, *, conversation_only: bool) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """加载会话并重建待发送消息。"""
    session = Session(id=session_id, load_persisted_messages=True)
    raw_messages = list(session.messages)

    if conversation_only:
        from nini.agent.components.context_utils import (
            filter_valid_messages,
            prepare_messages_for_llm,
        )

        valid_messages = filter_valid_messages(raw_messages)
        return raw_messages, prepare_messages_for_llm(valid_messages)

    runner = AgentRunner()
    built_messages, _ = await runner._build_messages_and_retrieval(session)  # noqa: SLF001
    return raw_messages, built_messages


async def _resolve_zhipu_runtime_config(
    args: argparse.Namespace,
) -> tuple[str | None, str | None, str | None]:
    """优先读取当前生效的智谱配置（DB > .env > CLI 默认）。"""
    effective_config = await get_effective_config("zhipu")

    api_key = args.api_key or effective_config.get("api_key") or settings.zhipu_api_key
    model = args.model or effective_config.get("model") or settings.zhipu_model
    base_url = args.base_url or effective_config.get("base_url") or settings.zhipu_base_url
    return (
        str(api_key).strip() if isinstance(api_key, str) and api_key.strip() else None,
        str(model).strip() if isinstance(model, str) and model.strip() else None,
        str(base_url).strip() if isinstance(base_url, str) and base_url.strip() else None,
    )


async def _send_probe(
    client: ZhipuClient,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
    first_chunk_only: bool,
) -> dict[str, Any]:
    """可选地真实发送一次请求，验证服务端响应。"""
    chunks: list[dict[str, Any]] = []
    async for chunk in client.chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        chunks.append(
            {
                "text": getattr(chunk, "text", ""),
                "reasoning": getattr(chunk, "reasoning", ""),
                "finish_reason": getattr(chunk, "finish_reason", None),
                "tool_calls": getattr(chunk, "tool_calls", []),
            }
        )
        if first_chunk_only:
            break

    return {
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重建智谱请求 messages 并输出调试摘要")
    parser.add_argument("session_id", help="待检查的会话 ID")
    parser.add_argument(
        "--model",
        default=None,
        help="智谱模型名；未指定时按 DB 生效配置 > .env 配置回退",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="智谱 base_url；未指定时按 DB 生效配置 > .env 配置回退",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="智谱 API Key；未指定时按 DB 生效配置 > .env 配置回退",
    )
    parser.add_argument(
        "--conversation-only",
        action="store_true",
        help="仅重建对话历史，不拼接 system/runtime context",
    )
    parser.add_argument(
        "--dump-output",
        type=Path,
        default=None,
        help="可选：将完整报告写入指定 JSON 文件",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="在输出摘要后，真实向智谱发送一次请求做验证",
    )
    parser.add_argument(
        "--first-chunk-only",
        action="store_true",
        help="验证时只读取首个 chunk，用于快速判断请求是否被服务端接受",
    )
    parser.add_argument("--temperature", type=float, default=0.3, help="发送验证时的温度")
    parser.add_argument("--max-tokens", type=int, default=512, help="发送验证时的最大 token")
    return parser.parse_args()


async def _main_async(args: argparse.Namespace) -> int:
    raw_messages, built_messages = await _build_messages(
        args.session_id,
        conversation_only=bool(args.conversation_only),
    )
    api_key, model, base_url = await _resolve_zhipu_runtime_config(args)

    client = ZhipuClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    normalized_messages = client._normalize_messages_for_provider(built_messages)  # noqa: SLF001

    api_mode = infer_api_mode_from_base_url("zhipu", base_url)
    default_model = get_default_model_for_mode("zhipu", api_mode) if api_mode else None
    raw_tool_call_issues = _collect_raw_tool_call_issues(raw_messages)

    warnings: list[str] = []
    if api_mode == "coding_plan" and default_model and model != default_model:
        warnings.append(
            "当前是智谱 Coding Plan 端点，但模型不是仓库默认推荐值；"
            f"默认模型为 {default_model}，当前传入为 {model}。"
        )
    if not raw_tool_call_issues:
        warnings.append("原始会话中的 tool_calls 未发现嵌套附加字段，messages 本身看起来较干净。")

    report: dict[str, Any] = {
        "session_id": args.session_id,
        "conversation_only": bool(args.conversation_only),
        "provider_id": "zhipu",
        "model": model,
        "base_url": base_url,
        "api_mode": api_mode,
        "default_model_for_mode": default_model,
        "raw_message_count": len(raw_messages),
        "built_message_count": len(built_messages),
        "normalized_message_count": len(normalized_messages),
        "warnings": warnings,
        "raw_tool_call_issues": raw_tool_call_issues,
        "built_messages_summary": summarize_messages_for_debug(built_messages),
        "normalized_messages_summary": summarize_messages_for_debug(normalized_messages),
    }

    if args.send:
        if not api_key:
            raise RuntimeError("--send 需要可用的智谱 API Key")
        report["probe_result"] = await _send_probe(
            client,
            built_messages,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            first_chunk_only=bool(args.first_chunk_only),
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.dump_output:
        args.dump_output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
