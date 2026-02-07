"""WebSocket Agent 交互端点。"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

import numpy as np

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from nini.agent.runner import AgentRunner, EventType
from nini.agent.session import session_manager
from nini.agent.title_generator import generate_title
from nini.models.schemas import WSEvent
from nini.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

# 运行时注入的 skill_registry
_skill_registry: SkillRegistry | None = None


def set_skill_registry(registry: SkillRegistry) -> None:
    global _skill_registry
    _skill_registry = registry


@router.websocket("/ws")
async def websocket_agent(ws: WebSocket):
    """WebSocket Agent 交互。

    客户端发送：
        {"type": "chat", "content": "...", "session_id": "..."}

    服务端推送事件流：
        {"type": "text", "data": "...", "session_id": "..."}
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

            if msg_type == "chat":
                content = msg.get("content", "").strip()
                if not content:
                    await _send_event(ws, "error", data="消息内容不能为空")
                    continue

                session_id = msg.get("session_id")
                session = session_manager.get_or_create(session_id)

                # 返回 session_id 方便客户端追踪
                await _send_event(ws, "session", data={"session_id": session.id})

                # 运行 Agent
                runner = AgentRunner(skill_registry=_skill_registry)
                async for event in runner.run(session, content):
                    await _send_event(
                        ws,
                        event.type.value,
                        data=event.data,
                        session_id=session.id,
                        tool_call_id=event.tool_call_id,
                        tool_name=event.tool_name,
                        turn_id=event.turn_id,
                    )

                # 对话完成后异步生成会话标题（首次对话时）
                logger.debug(
                    "检查标题生成条件: title=%s, messages=%d",
                    session.title,
                    len(session.messages),
                )
                if session.title == "新会话" and len(session.messages) >= 2:
                    logger.info("触发会话标题自动生成: session_id=%s", session.id)
                    asyncio.create_task(_auto_generate_title(ws, session))
                else:
                    logger.debug(
                        "跳过标题生成: title=%s, messages=%d",
                        session.title,
                        len(session.messages),
                    )

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    except Exception as e:
        logger.error("WebSocket 异常: %s", e, exc_info=True)
        try:
            await _send_event(ws, "error", data=f"服务器错误: {e}")
        except Exception:
            pass
    finally:
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


async def _send_event(
    ws: WebSocket,
    event_type: str,
    data: Any = None,
    session_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    turn_id: str | None = None,
) -> None:
    """发送 WebSocket 事件。使用自定义编码器兜底处理 numpy 类型。"""
    # 检查连接是否仍然打开
    if ws.client_state.name == "DISCONNECTED":
        logger.debug("WebSocket 已断开，跳过发送事件: %s", event_type)
        return

    try:
        event = WSEvent(
            type=event_type,
            data=data,
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            turn_id=turn_id,
        )
        event_dict = event.model_dump(exclude_none=True)
        await ws.send_text(
            json.dumps(event_dict, cls=_NumpySafeEncoder, ensure_ascii=False)
        )
    except RuntimeError as e:
        # 连接可能在发送过程中关闭
        if "close message has been sent" in str(e):
            logger.debug("WebSocket 连接已关闭，无法发送事件: %s", event_type)
        else:
            raise
