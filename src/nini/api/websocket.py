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
from starlette.websockets import WebSocketState

from nini.agent.runner import AgentRunner
from nini.agent.events import EventType
from nini.agent.session import Session, session_manager
from nini.agent.title_generator import generate_title
from nini.harness.runner import HarnessRunner
from nini.models.schemas import WSEvent
from nini.tools.registry import ToolRegistry
from nini.workspace import WorkspaceManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 运行时注入的 tool_registry
# 注意：虽然变量名保持 _tool_registry 以向后兼容，但类型是 ToolRegistry
_tool_registry: ToolRegistry | None = None


def set_tool_registry(registry: ToolRegistry) -> None:
    """设置工具注册中心。"""
    global _tool_registry
    _tool_registry = registry


def get_tool_registry() -> ToolRegistry | None:
    """获取工具注册中心。"""
    return _tool_registry


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
    # 可选 API Key 认证（通过 query param token 验证）
    from nini.config import settings as _settings
    import secrets as _secrets

    if _settings.api_key:
        token = ws.query_params.get("token", "")
        if not _secrets.compare_digest(token, _settings.api_key):
            await ws.close(code=4401, reason="未授权：需要有效的 API Key")
            return

    await ws.accept()
    logger.info("WebSocket 连接已建立")

    # 启动保活任务
    keepalive_task = asyncio.create_task(_keepalive(ws))
    # 多会话并发：按 session_id 索引各自的后台任务和停止事件
    active_chat_tasks: dict[str, asyncio.Task[None]] = {}
    active_stop_events: dict[str, asyncio.Event] = {}
    pending_question_futures: dict[str, asyncio.Future[dict[str, str]]] = {}
    # tool_call_id → session_id，用于精确取消指定会话的挂起提问
    pending_question_session_map: dict[str, str] = {}

    def _cancel_pending_questions(target_session_id: str | None = None) -> None:
        """取消等待中的 ask_user_question 回答。

        target_session_id 为 None 时取消全部；否则只取消该会话的 futures。
        """
        if target_session_id is None:
            # 全量取消
            for future in list(pending_question_futures.values()):
                if not future.done():
                    future.cancel()
            pending_question_futures.clear()
            pending_question_session_map.clear()
        else:
            # 只取消属于目标会话的 futures
            to_cancel = [
                tcid
                for tcid, sid in list(pending_question_session_map.items())
                if sid == target_session_id
            ]
            for tcid in to_cancel:
                future = pending_question_futures.pop(tcid, None)
                pending_question_session_map.pop(tcid, None)
                if future is not None and not future.done():
                    future.cancel()

    def _trigger_memory_consolidation(s: Any) -> None:
        """安全地异步触发会话记忆沉淀，忽略导入或运行错误。"""
        if s is None:
            return
        try:
            from nini.memory.long_term_memory import consolidate_session_memories

            asyncio.create_task(consolidate_session_memories(s.id))
        except Exception:
            logger.debug("记忆沉淀触发失败，忽略", exc_info=True)

    async def _wait_for_ask_user_question_answers(
        session: Session,
        tool_call_id: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """挂起等待前端提交 ask_user_question 回答。"""
        _ = payload
        if not tool_call_id:
            raise ValueError("ask_user_question 缺少 tool_call_id")

        loop = asyncio.get_running_loop()
        future = pending_question_futures.get(tool_call_id)
        if future is None or future.done():
            future = loop.create_future()
            pending_question_futures[tool_call_id] = future
        # 记录 tool_call_id → session_id 的映射，用于精确取消
        pending_question_session_map[tool_call_id] = session.id
        try:
            return await future
        finally:
            pending_question_futures.pop(tool_call_id, None)
            pending_question_session_map.pop(tool_call_id, None)

    async def _run_chat(
        session: Session,
        content: str,
        *,
        append_user_message: bool,
    ) -> None:
        runner = HarnessRunner(
            agent_runner=AgentRunner(
                tool_registry=_tool_registry,
                ask_user_question_handler=_wait_for_ask_user_question_answers,
            ),
        )
        stop_event = active_stop_events.get(session.id) or asyncio.Event()

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
        previous_event_callback = getattr(session, "event_callback", None)

        async def _forward_session_event(event: Any) -> None:
            """转发工具运行时通过 session.event_callback 推送的事件。"""
            if previous_event_callback is not None:
                result = previous_event_callback(event)
                if asyncio.iscoroutine(result):
                    await result

            await _send_event(
                ws,
                event.type.value,
                data=event.data,
                session_id=session.id,
                tool_call_id=getattr(event, "tool_call_id", None),
                tool_name=getattr(event, "tool_name", None),
                turn_id=getattr(event, "turn_id", None),
                metadata=getattr(event, "metadata", None),
                active_stop_events=active_stop_events,
            )

        session.event_callback = _forward_session_event

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
                    # 记录 tool_call_id → session_id 映射
                    pending_question_session_map[event.tool_call_id] = session.id

                await _send_event(
                    ws,
                    event.type.value,
                    data=event.data,
                    session_id=session.id,
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    turn_id=event.turn_id,
                    metadata=event.metadata,
                    active_stop_events=active_stop_events,
                )
                # 分析思路事件：通知前端刷新工作区（已保存为产物）
                if (
                    event.type == EventType.REASONING
                    and isinstance(event.metadata, dict)
                    and event.metadata.get("workspace_update") == "add"
                ):
                    await _send_event(
                        ws,
                        EventType.WORKSPACE_UPDATE.value,
                        data={"action": "add"},
                        session_id=session.id,
                        active_stop_events=active_stop_events,
                    )
                # 产物或图片生成后通知前端刷新工作区面板
                if event.type in (EventType.ARTIFACT, EventType.IMAGE):
                    await _send_event(
                        ws,
                        EventType.WORKSPACE_UPDATE.value,
                        data={"action": "add"},
                        session_id=session.id,
                        active_stop_events=active_stop_events,
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
                        logger.debug("代码执行参数解析失败", exc_info=True)
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
                        payload = result_data.get("data")
                        execution_id = ""
                        if isinstance(payload, dict):
                            execution_id = str(payload.get("execution_id", "")).strip()
                        exec_record = wm.get_code_execution(execution_id) if execution_id else None
                        if exec_record is None:
                            exec_record = wm.save_code_execution(
                                code=paired_code,
                                output=str(
                                    result_data.get("message", result_data.get("output", ""))
                                ),
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
                            EventType.CODE_EXECUTION.value,
                            data=exec_record,
                            session_id=session.id,
                            active_stop_events=active_stop_events,
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
            _cancel_pending_questions(session.id)
        except Exception as e:
            logger.error("WebSocket 聊天任务异常: %s", e, exc_info=True)
            with suppress(Exception):
                await _send_event(
                    ws,
                    "error",
                    data="服务器内部错误，请重试",
                    session_id=session.id,
                    active_stop_events=active_stop_events,
                )
        finally:
            session.event_callback = previous_event_callback
            _cancel_pending_questions(session.id)
            # 从字典中移除该会话的任务和停止事件
            active_chat_tasks.pop(session.id, None)
            active_stop_events.pop(session.id, None)

    try:
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send_event(
                    ws,
                    "error",
                    data="消息格式错误，请发送 JSON",
                    active_stop_events=active_stop_events,
                )
                continue

            msg_type = msg.get("type", "chat")

            if msg_type == "ping":
                await _send_event(
                    ws,
                    EventType.PONG.value,
                    active_stop_events=active_stop_events,
                )
                continue

            if msg_type == "stop":
                stop_session_id = msg.get("session_id")
                if stop_session_id:
                    # 停止指定会话的任务
                    task = active_chat_tasks.get(stop_session_id)
                    if task and not task.done():
                        stop_ev = active_stop_events.get(stop_session_id)
                        if stop_ev:
                            stop_ev.set()
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                        _cancel_pending_questions(stop_session_id)
                        stopped_session = session_manager.get_or_create(stop_session_id)
                        _trigger_memory_consolidation(stopped_session)
                        await _send_event(
                            ws,
                            EventType.STOPPED.value,
                            data="已停止当前请求",
                            session_id=stop_session_id,
                            active_stop_events=active_stop_events,
                        )
                    else:
                        await _send_event(
                            ws,
                            EventType.STOPPED.value,
                            data="当前没有进行中的请求",
                            session_id=stop_session_id,
                            active_stop_events=active_stop_events,
                        )
                else:
                    # 向后兼容：无 session_id 时停止所有运行中任务
                    if active_chat_tasks:
                        for sid, task in list(active_chat_tasks.items()):
                            if not task.done():
                                stop_ev = active_stop_events.get(sid)
                                if stop_ev:
                                    stop_ev.set()
                                task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await task
                                stopped_session = session_manager.get_or_create(sid)
                                _trigger_memory_consolidation(stopped_session)
                        _cancel_pending_questions()
                        await _send_event(
                            ws,
                            EventType.STOPPED.value,
                            data="已停止所有进行中请求",
                            active_stop_events=active_stop_events,
                        )
                    else:
                        await _send_event(
                            ws,
                            EventType.STOPPED.value,
                            data="当前没有进行中的请求",
                            active_stop_events=active_stop_events,
                        )
                continue

            if msg_type == "ask_user_question_answer":
                tool_call_id = msg.get("tool_call_id")
                answers_raw = msg.get("answers")

                if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                    await _send_event(
                        ws,
                        "error",
                        data="ask_user_question_answer 缺少 tool_call_id",
                        active_stop_events=active_stop_events,
                    )
                    continue
                if not isinstance(answers_raw, dict):
                    await _send_event(
                        ws,
                        "error",
                        data="ask_user_question_answer 缺少 answers 对象",
                        active_stop_events=active_stop_events,
                    )
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
                    await _send_event(
                        ws,
                        "error",
                        data="当前没有待回答的 ask_user_question 请求",
                        active_stop_events=active_stop_events,
                    )
                    continue

                future.set_result(answers)
                continue

            if msg_type == "retry":
                session_id = msg.get("session_id")
                if not isinstance(session_id, str) or not session_id.strip():
                    await _send_event(
                        ws,
                        "error",
                        data="重试需要有效的 session_id",
                        active_stop_events=active_stop_events,
                    )
                    continue

                # 检查该会话是否已有运行中任务
                existing_task = active_chat_tasks.get(session_id)
                if existing_task and not existing_task.done():
                    await _send_event(
                        ws,
                        "error",
                        data="当前有进行中的请求，请先停止后再重试",
                        session_id=session_id,
                        active_stop_events=active_stop_events,
                    )
                    continue

                retry_session = session_manager.get_or_create(session_id)
                retry_content = retry_session.rollback_last_turn()
                append_user_message = False
                if not retry_content:
                    raw_content = msg.get("content", "")
                    retry_content = raw_content.strip() if isinstance(raw_content, str) else ""
                    append_user_message = True

                if not retry_content:
                    await _send_event(
                        ws,
                        "error",
                        data="没有可重试的用户消息",
                        session_id=session_id,
                        active_stop_events=active_stop_events,
                    )
                    continue

                # 返回 session_id 方便客户端追踪
                await _send_event(
                    ws,
                    EventType.SESSION.value,
                    data={"session_id": retry_session.id},
                    active_stop_events=active_stop_events,
                )

                # 运行 Agent（后台任务，按 session_id 注册）
                stop_event = asyncio.Event()
                active_stop_events[retry_session.id] = stop_event
                active_chat_tasks[retry_session.id] = asyncio.create_task(
                    _run_chat(
                        retry_session,
                        retry_content,
                        append_user_message=append_user_message,
                    )
                )
                continue

            if msg_type == "chat":
                content = msg.get("content", "").strip()
                if not content:
                    await _send_event(
                        ws,
                        "error",
                        data="消息内容不能为空",
                        active_stop_events=active_stop_events,
                    )
                    continue

                session_id = msg.get("session_id")
                chat_session = session_manager.get_or_create(session_id)

                # 检查该会话是否已有运行中任务（不阻塞其他会话）
                existing_task = active_chat_tasks.get(chat_session.id)
                if existing_task and not existing_task.done():
                    await _send_event(
                        ws,
                        "error",
                        data="当前有进行中的请求，请等待完成或先停止",
                        session_id=chat_session.id,
                        active_stop_events=active_stop_events,
                    )
                    continue

                # 返回 session_id 方便客户端追踪
                await _send_event(
                    ws,
                    EventType.SESSION.value,
                    data={"session_id": chat_session.id},
                    active_stop_events=active_stop_events,
                )

                # 运行 Agent（后台任务，按 session_id 注册）
                stop_event = asyncio.Event()
                active_stop_events[chat_session.id] = stop_event
                active_chat_tasks[chat_session.id] = asyncio.create_task(
                    _run_chat(chat_session, content, append_user_message=True)
                )
                continue

            await _send_event(
                ws,
                "error",
                data=f"不支持的消息类型: {msg_type}",
                active_stop_events=active_stop_events,
            )

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    except Exception as e:
        logger.error("WebSocket 异常: %s", e, exc_info=True)
        try:
            await _send_event(
                ws,
                "error",
                data="服务器内部错误，请重试",
                active_stop_events=active_stop_events,
            )
        except Exception:
            pass
    finally:
        _cancel_pending_questions()
        # 断开连接时 cancel 所有会话的后台任务，并触发各自的记忆沉淀
        for sid, stop_ev in list(active_stop_events.items()):
            stop_ev.set()
        for sid, task in list(active_chat_tasks.items()):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            # 断开连接时触发各会话的记忆沉淀
            disconnected_session = session_manager.get_or_create(sid)
            _trigger_memory_consolidation(disconnected_session)
        active_chat_tasks.clear()
        active_stop_events.clear()
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
                EventType.SESSION_TITLE.value,
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
            if ws.client_state == WebSocketState.DISCONNECTED:
                break
            try:
                await _send_event(ws, EventType.PONG.value)
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


def _normalize_wire_event_data(event_type: str, data: Any) -> Any:
    """兼容旧前端/测试的事件载荷格式。"""
    safe_data = _to_json_safe(data)

    # 兼容旧协议：text 事件 data 直接为字符串
    if event_type == EventType.TEXT.value and isinstance(safe_data, dict):
        content = safe_data.get("content")
        if isinstance(content, str):
            return content

    # 兼容旧协议：tool_result 将 data.result 提升到顶层 result 字段
    if event_type == EventType.TOOL_RESULT.value and isinstance(safe_data, dict):
        nested_data = safe_data.get("data")
        if isinstance(nested_data, dict) and "result" in nested_data and "result" not in safe_data:
            return {**safe_data, "result": nested_data.get("result")}

    # 兼容旧协议：error 事件 data 直接为字符串消息
    if event_type == EventType.ERROR.value and isinstance(safe_data, dict):
        message = safe_data.get("message")
        if isinstance(message, str):
            return message

    return safe_data


async def _send_event(
    ws: WebSocket,
    event_type: str,
    data: Any = None,
    session_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    active_stop_events: dict[str, asyncio.Event] | None = None,
) -> None:
    """发送 WebSocket 事件。使用自定义编码器兜底处理 numpy 类型。"""
    # 检查连接是否仍然打开
    if ws.client_state == WebSocketState.DISCONNECTED:
        logger.debug("WebSocket 已断开，跳过发送事件: %s", event_type)
        return

    try:
        event = WSEvent(
            type=event_type,
            data=_normalize_wire_event_data(event_type, data),
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            turn_id=turn_id,
            metadata=metadata or {},
        )
        event_dict = event.model_dump(exclude_none=True)
        await ws.send_text(json.dumps(event_dict, cls=_NumpySafeEncoder, ensure_ascii=False))
    except RuntimeError as e:
        # 连接可能在发送过程中关闭，通知对应会话的 Agent 停止
        if "close message has been sent" in str(e):
            logger.debug("WebSocket 连接已关闭，无法发送事件: %s", event_type)
            if active_stop_events is not None and session_id and session_id in active_stop_events:
                active_stop_events[session_id].set()
        else:
            raise
