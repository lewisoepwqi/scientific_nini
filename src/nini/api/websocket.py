"""WebSocket Agent 交互端点。"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from contextlib import suppress
from typing import Any

import numpy as np
import pandas as pd

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import session_manager
from nini.agent.title_generator import generate_title
from nini.models.schemas import WSEvent
from nini.tools.registry import SkillRegistry
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 运行时注入的 skill_registry
_skill_registry: SkillRegistry | None = None


def set_skill_registry(registry: SkillRegistry) -> None:
    global _skill_registry
    _skill_registry = registry


def get_skill_registry() -> SkillRegistry | None:
    return _skill_registry


@router.websocket("/ws")
async def websocket_agent(ws: WebSocket):
    """WebSocket Agent 交互。

    客户端发送：
        {"type": "chat", "content": "...", "session_id": "..."}
        {"type": "stop"}
        {"type": "retry", "session_id": "..."}

    服务端推送事件流：
        {"type": "text", "data": "...", "session_id": "..."}
        {"type": "retrieval", "data": {"query": "...", "results": [...]}}
        {"type": "tool_call", ...}
        {"type": "tool_result", ...}
        {"type": "chart", "data": {...}}
        {"type": "done"}
        {"type": "error", "data": "..."}
    """
    await ws.accept()
    logger.info("WebSocket 连接已建立")

    # 启动保活任务
    keepalive_task = asyncio.create_task(_keepalive(ws))
    active_chat_task: asyncio.Task[None] | None = None
    active_stop_event: asyncio.Event | None = None
    pending_question_futures: dict[str, asyncio.Future[dict[str, str]]] = {}

    def _cancel_pending_questions() -> None:
        """取消所有等待中的 ask_user_question 回答。"""
        for future in list(pending_question_futures.values()):
            if not future.done():
                future.cancel()
        pending_question_futures.clear()

    async def _wait_for_ask_user_question_answers(
        session: Any,
        tool_call_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """挂起等待前端提交 ask_user_question 回答。"""
        _ = session, payload
        if not tool_call_id:
            raise ValueError("ask_user_question 缺少 tool_call_id")

        loop = asyncio.get_running_loop()
        future = pending_question_futures.get(tool_call_id)
        if future is None or future.done():
            future = loop.create_future()
            pending_question_futures[tool_call_id] = future
        try:
            return await future
        finally:
            pending_question_futures.pop(tool_call_id, None)

    async def _run_chat(
        session: Any,
        content: str,
        *,
        append_user_message: bool,
    ) -> None:
        nonlocal active_chat_task, active_stop_event
        runner = AgentRunner(
            skill_registry=_skill_registry,
            ask_user_question_handler=_wait_for_ask_user_question_answers,
        )
        stop_event = active_stop_event or asyncio.Event()

        # 会话首次恢复时，从工作空间补齐已上传数据集
        if not getattr(session, "workspace_hydrated", False):
            try:
                loaded = WorkspaceManager(session.id).hydrate_session_datasets(session)
                if loaded > 0:
                    logger.info(
                        "工作空间数据集已恢复: session_id=%s loaded=%d",
                        session.id,
                        loaded,
                    )
            except Exception as exc:
                logger.warning("恢复工作空间数据集失败: session_id=%s err=%s", session.id, exc)
            session.workspace_hydrated = True

        # 缓存代码执行工具的输入代码，用于配对 tool_call → tool_result
        _code_exec_tools = ("run_code", "run_r_code", "execute_code", "code_exec")
        _pending_code: dict[str, str] = {}
        _pending_tool_args: dict[str, dict] = {}

        try:
            async for event in runner.run(
                session,
                content,
                append_user_message=append_user_message,
                stop_event=stop_event,
            ):
                if event.type == EventType.ASK_USER_QUESTION and event.tool_call_id:
                    loop = asyncio.get_running_loop()
                    future = pending_question_futures.get(event.tool_call_id)
                    if future is None or future.done():
                        pending_question_futures[event.tool_call_id] = loop.create_future()

                await _send_event(
                    ws,
                    event.type.value,
                    data=event.data,
                    session_id=session.id,
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    turn_id=event.turn_id,
                    metadata=event.metadata,
                )
                # 分析思路事件：通知前端刷新工作区（已保存为产物）
                if (
                    event.type == EventType.REASONING
                    and isinstance(event.metadata, dict)
                    and event.metadata.get("workspace_update") == "add"
                ):
                    await _send_event(
                        ws,
                        "workspace_update",
                        data={"action": "add"},
                        session_id=session.id,
                    )
                # 产物或图片生成后通知前端刷新工作区面板
                if event.type in (EventType.ARTIFACT, EventType.IMAGE):
                    await _send_event(
                        ws,
                        "workspace_update",
                        data={"action": "add"},
                        session_id=session.id,
                    )
                # 工具调用：缓存代码执行工具的源代码
                if (
                    event.type == EventType.TOOL_CALL
                    and event.tool_name
                    and event.tool_name in _code_exec_tools
                    and event.tool_call_id
                ):
                    try:
                        call_data = event.data if isinstance(event.data, dict) else {}
                        args_raw = call_data.get("arguments", "{}")
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        code = args.get("code", "") if isinstance(args, dict) else ""
                        if code:
                            _pending_code[event.tool_call_id] = str(code)
                        # 缓存完整工具调用参数
                        _pending_tool_args[event.tool_call_id] = {
                            "tool_name": event.tool_name,
                            "tool_args": args if isinstance(args, dict) else {},
                            "intent": (
                                event.metadata.get("intent")
                                if isinstance(event.metadata, dict)
                                else None
                            ),
                        }
                    except Exception:
                        pass
                # 工具执行结果：如果是代码执行类工具，配对源代码后持久化并推送事件
                if (
                    event.type == EventType.TOOL_RESULT
                    and event.tool_name
                    and event.tool_name in _code_exec_tools
                ):
                    try:
                        result_data = event.data if isinstance(event.data, dict) else {}
                        # 从缓存中取出配对的源代码和工具参数
                        paired_code = _pending_code.pop(event.tool_call_id or "", "")
                        tool_info = _pending_tool_args.pop(event.tool_call_id or "", {})
                        # 计算当前上下文 token 数
                        from nini.utils.token_counter import count_messages_tokens

                        ctx_tokens = count_messages_tokens(session.messages)
                        wm = WorkspaceManager(session.id)
                        event_intent = (
                            event.metadata.get("intent")
                            if isinstance(event.metadata, dict)
                            else None
                        )
                        exec_record = wm.save_code_execution(
                            code=paired_code,
                            output=str(result_data.get("message", result_data.get("output", ""))),
                            status=str(result_data.get("status", "success")),
                            language=(
                                "r"
                                if str(tool_info.get("tool_name", "")) == "run_r_code"
                                else "python"
                            ),
                            tool_name=tool_info.get("tool_name"),
                            tool_args=tool_info.get("tool_args"),
                            context_token_count=ctx_tokens,
                            intent=event_intent or tool_info.get("intent"),
                        )
                        await _send_event(
                            ws,
                            "code_execution",
                            data=exec_record,
                            session_id=session.id,
                        )
                    except Exception as exc:
                        logger.debug("保存代码执行记录失败: %s", exc)

            # 对话完成后异步生成会话标题（首次对话时）
            logger.debug(
                "检查标题生成条件: title=%s, messages=%d",
                session.title,
                len(session.messages),
            )
            if not stop_event.is_set() and session.title == "新会话" and len(session.messages) >= 2:
                logger.info("触发会话标题自动生成: session_id=%s", session.id)
                asyncio.create_task(_auto_generate_title(ws, session))
            else:
                logger.debug(
                    "跳过标题生成: title=%s, messages=%d, stopped=%s",
                    session.title,
                    len(session.messages),
                    stop_event.is_set(),
                )
        except asyncio.CancelledError:
            logger.info("请求已取消: session_id=%s", session.id)
            _cancel_pending_questions()
        except Exception as e:
            logger.error("WebSocket 聊天任务异常: %s", e, exc_info=True)
            with suppress(Exception):
                await _send_event(ws, "error", data=f"服务器错误: {e}")
        finally:
            _cancel_pending_questions()
            if active_chat_task is asyncio.current_task():
                active_chat_task = None
                active_stop_event = None

    try:
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send_event(ws, "error", data="消息格式错误，请发送 JSON")
                continue

            msg_type = msg.get("type", "chat")

            if msg_type == "ping":
                await _send_event(ws, "pong")
                continue

            if msg_type == "stop":
                task = active_chat_task
                if task and not task.done():
                    if active_stop_event:
                        active_stop_event.set()
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    _cancel_pending_questions()
                    await _send_event(ws, "stopped", data="已停止当前请求")
                else:
                    await _send_event(ws, "stopped", data="当前没有进行中的请求")
                continue

            if msg_type == "ask_user_question_answer":
                tool_call_id = msg.get("tool_call_id")
                answers_raw = msg.get("answers")

                if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                    await _send_event(ws, "error", data="ask_user_question_answer 缺少 tool_call_id")
                    continue
                if not isinstance(answers_raw, dict):
                    await _send_event(ws, "error", data="ask_user_question_answer 缺少 answers 对象")
                    continue

                answers: dict[str, str] = {}
                for raw_key, raw_value in answers_raw.items():
                    if not isinstance(raw_key, str):
                        continue
                    key = raw_key.strip()
                    if not key:
                        continue

                    if isinstance(raw_value, str):
                        value = raw_value.strip()
                    elif isinstance(raw_value, (list, tuple)):
                        parts = [str(item).strip() for item in raw_value if str(item).strip()]
                        value = ", ".join(parts)
                    elif raw_value is None:
                        value = ""
                    else:
                        value = str(raw_value).strip()

                    answers[key] = value

                future = pending_question_futures.get(tool_call_id)
                if future is None or future.done():
                    await _send_event(ws, "error", data="当前没有待回答的 ask_user_question 请求")
                    continue

                future.set_result(answers)
                continue

            if msg_type == "retry":
                if active_chat_task and not active_chat_task.done():
                    await _send_event(
                        ws,
                        "error",
                        data="当前有进行中的请求，请先停止后再重试",
                    )
                    continue

                session_id = msg.get("session_id")
                if not isinstance(session_id, str) or not session_id.strip():
                    await _send_event(ws, "error", data="重试需要有效的 session_id")
                    continue

                session = session_manager.get_or_create(session_id)
                retry_content = session.rollback_last_turn()
                append_user_message = False
                if not retry_content:
                    raw_content = msg.get("content", "")
                    retry_content = raw_content.strip() if isinstance(raw_content, str) else ""
                    append_user_message = True

                if not retry_content:
                    await _send_event(ws, "error", data="没有可重试的用户消息")
                    continue

                # 返回 session_id 方便客户端追踪
                await _send_event(ws, "session", data={"session_id": session.id})

                # 运行 Agent（后台任务）
                active_stop_event = asyncio.Event()
                active_chat_task = asyncio.create_task(
                    _run_chat(
                        session,
                        retry_content,
                        append_user_message=append_user_message,
                    )
                )
                continue

            if msg_type == "chat":
                if active_chat_task and not active_chat_task.done():
                    await _send_event(
                        ws,
                        "error",
                        data="当前有进行中的请求，请等待完成或先停止",
                    )
                    continue

                content = msg.get("content", "").strip()
                if not content:
                    await _send_event(ws, "error", data="消息内容不能为空")
                    continue

                session_id = msg.get("session_id")
                session = session_manager.get_or_create(session_id)

                # 返回 session_id 方便客户端追踪
                await _send_event(ws, "session", data={"session_id": session.id})

                # 运行 Agent（后台任务）
                active_stop_event = asyncio.Event()
                active_chat_task = asyncio.create_task(
                    _run_chat(session, content, append_user_message=True)
                )
                continue

            await _send_event(ws, "error", data=f"不支持的消息类型: {msg_type}")

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    except Exception as e:
        logger.error("WebSocket 异常: %s", e, exc_info=True)
        try:
            await _send_event(ws, "error", data=f"服务器错误: {e}")
        except Exception:
            pass
    finally:
        _cancel_pending_questions()
        if active_stop_event:
            active_stop_event.set()
        task = active_chat_task
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass


async def _auto_generate_title(ws: WebSocket, session: Any) -> None:
    """异步生成会话标题并推送给客户端。"""
    try:
        title = await generate_title(session.messages)
        if title:
            session.title = title
            session_manager.save_session_title(session.id, title)
            await _send_event(
                ws,
                "session_title",
                data={"session_id": session.id, "title": title},
                session_id=session.id,
            )
    except Exception as e:
        logger.debug("自动生成会话标题失败: %s", e)


async def _keepalive(ws: WebSocket) -> None:
    """WebSocket 保活任务：每 15 秒发送一次 pong 保持连接活跃。"""
    try:
        while True:
            await asyncio.sleep(15)
            if ws.client_state.name == "DISCONNECTED":
                break
            try:
                await _send_event(ws, "pong")
            except Exception:
                # 发送失败，连接可能已断开
                break
    except asyncio.CancelledError:
        pass


class _NumpySafeEncoder(json.JSONEncoder):
    """兜底 JSON 编码器：将 numpy 标量/数组转为 Python 原生类型。"""

    def default(self, o: Any) -> Any:
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            v = float(o)
            if not math.isfinite(v):
                return None
            return v
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


def _dataframe_preview(df: pd.DataFrame, max_rows: int = 20) -> dict[str, Any]:
    """将 DataFrame 压缩为可传输预览，避免 WebSocket JSON 序列化失败。"""
    preview = df.head(max_rows)
    return {
        "__type__": "DataFrame",
        "rows": int(len(df)),
        "columns": [str(col) for col in df.columns.tolist()],
        "preview_rows": int(len(preview)),
        "preview": _to_json_safe(preview.to_dict(orient="records")),
    }


def _series_preview(series: pd.Series, max_rows: int = 20) -> dict[str, Any]:
    """将 Series 压缩为可传输预览。"""
    preview = series.head(max_rows).tolist()
    return {
        "__type__": "Series",
        "name": str(series.name) if series.name is not None else None,
        "length": int(len(series)),
        "preview_rows": int(min(max_rows, len(series))),
        "preview": _to_json_safe(preview),
    }


def _to_json_safe(value: Any) -> Any:
    """递归转换为 JSON 安全结构。"""
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        v = float(value)
        return v if math.isfinite(v) else None
    if isinstance(value, np.ndarray):
        return _to_json_safe(value.tolist())
    if isinstance(value, pd.DataFrame):
        return _dataframe_preview(value)
    if isinstance(value, pd.Series):
        return _series_preview(value)
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(v) for v in value]
    return str(value)


async def _send_event(
    ws: WebSocket,
    event_type: str,
    data: Any = None,
    session_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """发送 WebSocket 事件。使用自定义编码器兜底处理 numpy 类型。"""
    # 检查连接是否仍然打开
    if ws.client_state.name == "DISCONNECTED":
        logger.debug("WebSocket 已断开，跳过发送事件: %s", event_type)
        return

    try:
        event = WSEvent(
            type=event_type,
            data=_to_json_safe(data),
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            turn_id=turn_id,
            metadata=metadata or {},
        )
        event_dict = event.model_dump(exclude_none=True)
        await ws.send_text(json.dumps(event_dict, cls=_NumpySafeEncoder, ensure_ascii=False))
    except RuntimeError as e:
        # 连接可能在发送过程中关闭
        if "close message has been sent" in str(e):
            logger.debug("WebSocket 连接已关闭，无法发送事件: %s", event_type)
        else:
            raise
