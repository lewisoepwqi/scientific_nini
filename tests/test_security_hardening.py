"""安全加固测试：覆盖 assert 替换、路径验证、异步任务管理等安全修复。"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Assert 替换 —— AllowedToolDecision.approval_key 为 None 时抛出 RuntimeError
# ---------------------------------------------------------------------------
from nini.agent.runner import AgentRunner, AllowedToolDecision, EventType
from nini.agent.session import Session


class TestApprovalKeyValidation:
    """验证 approval_key 安全校验不依赖 assert。"""

    def test_allowed_tool_decision_approval_key_none(self):
        """AllowedToolDecision 允许 approval_key 为 None（由调用处校验）。"""
        decision = AllowedToolDecision(mode="require_confirmation", risk_level="high")
        assert decision.approval_key is None

    def test_allowed_tool_decision_approval_key_set(self):
        """AllowedToolDecision 正常设置 approval_key。"""
        decision = AllowedToolDecision(
            mode="require_confirmation",
            risk_level="high",
            approval_key="run_code::exec",
        )
        assert decision.approval_key == "run_code::exec"

    @pytest.mark.asyncio
    async def test_runner_raises_runtime_error_when_approval_key_missing(self):
        """高风险工具确认缺少 approval_key 时应显式抛出 RuntimeError。"""

        class _KnowledgeLoader:
            def select_with_hits(self, *args, **kwargs):
                return "", []

        class _Resolver:
            async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
                class _Chunk:
                    def __init__(self):
                        self.text = ""
                        self.reasoning = ""
                        self.raw_text = ""
                        self.tool_calls = [
                            {
                                "id": "call_workspace_1",
                                "type": "function",
                                "function": {
                                    "name": "workspace_session",
                                    "arguments": json.dumps(
                                        {
                                            "operation": "write",
                                            "file_path": "notes/test.md",
                                            "content": "hello",
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ]
                        self.usage = None

                yield _Chunk()

        class _Registry:
            def get_tool_definitions(self):
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": "workspace_session",
                            "description": "工作区工具",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ]

            async def execute(self, tool_name: str, session: Session, **kwargs):
                raise AssertionError("approval_key 缺失时不应真正执行工具")

            async def execute_with_fallback(self, tool_name: str, session: Session, **kwargs):
                return await self.execute(tool_name, session=session, **kwargs)

        session = Session()
        runner = AgentRunner(
            resolver=_Resolver(),
            tool_registry=_Registry(),
            knowledge_loader=_KnowledgeLoader(),
        )

        with (
            patch.object(
                runner,
                "_resolve_allowed_tool_recommendations",
                return_value=(["run_code"], ["security-test"]),
            ),
            patch.object(
                runner,
                "_decide_allowed_tool_handling",
                return_value=AllowedToolDecision(
                    mode="require_confirmation",
                    risk_level="high",
                    approval_key=None,
                    operation="write",
                ),
            ),
            patch("nini.config_manager.get_active_provider_id", new=AsyncMock(return_value="test")),
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new=AsyncMock(return_value=["test"]),
            ),
        ):
            with pytest.raises(RuntimeError, match="approval_key 不应为 None"):
                async for _event in runner.run(
                    session,
                    "/guarded-skill 执行流程",
                    stage_override="security-test",
                ):
                    pass


# ---------------------------------------------------------------------------
# 2. 对话引用路径验证
# ---------------------------------------------------------------------------


class TestConversationPathValidation:
    """验证 _validate_ref_path 拒绝路径遍历。"""

    @pytest.fixture
    def conversation_dir(self, tmp_path):
        """创建模拟的会话目录结构。"""
        artifacts_dir = tmp_path / "workspace" / "artifacts"
        artifacts_dir.mkdir(parents=True)
        # 创建一个合法文件
        (artifacts_dir / "chart.png").write_bytes(b"fake png")
        return tmp_path

    def test_reject_absolute_path(self, conversation_dir):
        """绝对路径应被拒绝。"""
        from nini.memory.conversation import _validate_ref_path

        result = _validate_ref_path("/etc/passwd", conversation_dir)
        assert result is None

    def test_reject_traversal_path(self, conversation_dir):
        """包含 .. 的路径应被拒绝。"""
        from nini.memory.conversation import _validate_ref_path

        result = _validate_ref_path("../../etc/passwd", conversation_dir)
        assert result is None

    def test_accept_normal_path(self, conversation_dir):
        """正常相对路径应被接受。"""
        from nini.memory.conversation import _validate_ref_path

        result = _validate_ref_path("chart.png", conversation_dir)
        assert result is not None
        assert result.name == "chart.png"

    def test_reject_traversal_with_warning_log(self, conversation_dir, caplog):
        """路径遍历应记录 warning 日志。"""
        from nini.memory.conversation import _validate_ref_path

        with caplog.at_level(logging.WARNING):
            _validate_ref_path("../../etc/passwd", conversation_dir)
        assert "路径遍历" in caplog.text


# ---------------------------------------------------------------------------
# 3. 异步任务生命周期管理
# ---------------------------------------------------------------------------


class TestBackgroundTaskTracking:
    """验证 track_background_task 的强引用和清理逻辑。"""

    @pytest.fixture(autouse=True)
    def _import_tracker(self):
        from nini.utils.background_tasks import _background_tasks, track_background_task

        self._background_tasks = _background_tasks
        self._track = track_background_task

    async def test_task_added_and_removed_on_completion(self):
        """任务完成后应自动从集合中移除。"""

        async def noop():
            return 42

        task = self._track(noop())
        assert task in self._background_tasks
        await task
        # done_callback 在下一个事件循环迭代执行
        await asyncio.sleep(0)
        assert task not in self._background_tasks

    async def test_task_removed_on_exception(self, caplog):
        """任务异常后仍应移除，并记录 warning 日志。"""

        async def fail():
            raise ValueError("模拟失败")

        with caplog.at_level(logging.WARNING):
            task = self._track(fail())
            assert task in self._background_tasks
            await asyncio.sleep(0.05)
            assert task not in self._background_tasks
            assert "模拟失败" in caplog.text


# ---------------------------------------------------------------------------
# 4. Agent 分层超时
# ---------------------------------------------------------------------------


class TestAgentTimeoutConfig:
    """验证 Agent 分层超时配置与行为。"""

    def test_config_has_timeout_field(self):
        """Settings 类应包含 Agent 分层超时配置字段。"""
        from nini.config import Settings

        # 验证字段存在于模型定义中
        assert "agent_active_execution_timeout_seconds" in Settings.model_fields
        assert "agent_run_wall_clock_timeout_seconds" in Settings.model_fields
        assert "agent_max_timeout_seconds" in Settings.model_fields

    def test_default_timeout_value(self):
        """默认主动执行超时回退为 600 秒（支持 PDCA 多步分析），wall-clock 兜底默认不限。"""
        from nini.config import Settings

        assert Settings.model_fields["agent_active_execution_timeout_seconds"].default is None
        assert Settings.model_fields["agent_run_wall_clock_timeout_seconds"].default == 0
        assert Settings.model_fields["agent_max_timeout_seconds"].default == 600

    @pytest.mark.asyncio
    async def test_runner_stops_on_active_execution_timeout_and_emits_error_event(
        self, monkeypatch
    ):
        """主动执行超时触发后应返回 error 事件并保留已写入的会话消息。"""

        class _Resolver:
            def __init__(self) -> None:
                self.calls = 0

            async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
                self.calls += 1
                if False:
                    yield None
                raise AssertionError("timeout 前不应调用 resolver")

        resolver = _Resolver()
        session = Session()
        runner = AgentRunner(
            resolver=resolver, tool_registry=MagicMock(), knowledge_loader=MagicMock()
        )

        monkeypatch.setattr("nini.agent.runner.settings.agent_active_execution_timeout_seconds", 1)
        monkeypatch.setattr("nini.agent.runner.settings.agent_run_wall_clock_timeout_seconds", 0)

        with (
            patch(
                "nini.agent.runner.monotonic",
                side_effect=[100.0, 102.5, 102.5, 102.5],
            ),
            patch("nini.config_manager.get_active_provider_id", new=AsyncMock(return_value="test")),
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new=AsyncMock(return_value=["test"]),
            ),
        ):
            events = [
                event
                async for event in runner.run(
                    session,
                    "请继续分析",
                    stage_override="security-test",
                )
            ]

        assert resolver.calls == 0
        assert session.messages[-1]["content"] == "请继续分析"
        assert any(
            event.type == EventType.ERROR
            and isinstance(event.data, dict)
            and "主动执行超时" in str(event.data.get("message", ""))
            for event in events
        )

    @pytest.mark.asyncio
    async def test_runner_excludes_ask_user_question_wait_from_timeout(
        self,
        monkeypatch,
    ):
        """等待用户回答的时长不应计入 Agent 超时预算。"""

        class _Chunk:
            def __init__(self, *, text: str = "", tool_calls: list[dict] | None = None):
                self.text = text
                self.reasoning = ""
                self.raw_text = text
                self.tool_calls = tool_calls or []
                self.usage = None

        class _Resolver:
            def __init__(self) -> None:
                self.calls = 0

            async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    yield _Chunk(
                        tool_calls=[
                            {
                                "id": "call_ask_1",
                                "type": "function",
                                "function": {
                                    "name": "ask_user_question",
                                    "arguments": json.dumps(
                                        {
                                            "questions": [
                                                {
                                                    "question": "请选择输出格式",
                                                    "header": "输出格式",
                                                    "options": [
                                                        {
                                                            "label": "交互式图表",
                                                            "description": "Plotly",
                                                        },
                                                        {
                                                            "label": "静态图片",
                                                            "description": "PNG",
                                                        },
                                                    ],
                                                }
                                            ]
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ]
                    )
                    return

                yield _Chunk(text="已根据用户选择继续执行。")

        async def _ask_handler(session: Session, tool_call_id: str, payload: dict[str, object]):
            await asyncio.sleep(1.1)
            return {"请选择输出格式": "交互式图表"}

        class _KnowledgeLoader:
            def select_with_hits(self, *args, **kwargs):
                return "", []

        resolver = _Resolver()
        runner = AgentRunner(
            resolver=resolver,
            tool_registry=MagicMock(),
            knowledge_loader=_KnowledgeLoader(),
            ask_user_question_handler=_ask_handler,
        )
        session = Session()

        monkeypatch.setattr("nini.agent.runner.settings.agent_active_execution_timeout_seconds", 1)
        monkeypatch.setattr("nini.agent.runner.settings.agent_run_wall_clock_timeout_seconds", 0)

        with (
            patch("nini.config_manager.get_active_provider_id", new=AsyncMock(return_value="test")),
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new=AsyncMock(return_value=["test"]),
            ),
        ):
            events = [
                event
                async for event in runner.run(
                    session,
                    "请继续分析并在必要时询问我",
                    stage_override="security-test",
                )
            ]

        assert resolver.calls == 2
        assert not any(
            event.type == EventType.ERROR
            and isinstance(event.data, dict)
            and "运行超时" in str(event.data.get("message", ""))
            for event in events
        )
        assert any(
            event.type == EventType.TEXT
            and isinstance(event.data, dict)
            and "已根据用户选择继续执行" in str(event.data.get("content", ""))
            for event in events
        )

    @pytest.mark.asyncio
    async def test_runner_stops_on_wall_clock_timeout_when_configured(self, monkeypatch):
        """当配置 wall-clock 兜底时，应按整轮总时长终止。"""

        class _Resolver:
            def __init__(self) -> None:
                self.calls = 0

            async def chat(self, messages, tools=None, temperature=None, max_tokens=None, **kwargs):
                self.calls += 1
                if False:
                    yield None
                raise AssertionError("timeout 前不应调用 resolver")

        resolver = _Resolver()
        session = Session()
        runner = AgentRunner(
            resolver=resolver, tool_registry=MagicMock(), knowledge_loader=MagicMock()
        )

        monkeypatch.setattr("nini.agent.runner.settings.agent_active_execution_timeout_seconds", 0)
        monkeypatch.setattr("nini.agent.runner.settings.agent_run_wall_clock_timeout_seconds", 1)

        with (
            patch(
                "nini.agent.runner.monotonic",
                side_effect=[100.0, 102.5, 102.5, 102.5],
            ),
            patch("nini.config_manager.get_active_provider_id", new=AsyncMock(return_value="test")),
            patch(
                "nini.config_manager.list_user_configured_provider_ids",
                new=AsyncMock(return_value=["test"]),
            ),
        ):
            events = [
                event
                async for event in runner.run(
                    session,
                    "请继续分析",
                    stage_override="security-test",
                )
            ]

        assert resolver.calls == 0
        assert any(
            event.type == EventType.ERROR
            and isinstance(event.data, dict)
            and "运行总时长超时" in str(event.data.get("message", ""))
            for event in events
        )


# ---------------------------------------------------------------------------
# 5. Guardrail 路径检测增强
# ---------------------------------------------------------------------------


class TestGuardrailPathDetection:
    """验证 Guardrail 路径遍历和系统路径检测。"""

    @pytest.fixture
    def guardrail(self):
        from nini.tools.guardrails import DangerousPatternGuardrail

        return DangerousPatternGuardrail()

    def test_block_path_traversal(self, guardrail):
        """../../etc/passwd 应触发 BLOCK。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("run_code", {"file_path": "../../etc/passwd"})
        assert result.decision == GuardrailAction.BLOCK

    def test_block_proc_path(self, guardrail):
        """/proc/self/environ 应触发 BLOCK。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("run_code", {"file_path": "/proc/self/environ"})
        assert result.decision == GuardrailAction.BLOCK

    def test_allow_normal_filename(self, guardrail):
        """正常文件名不应触发误报。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("load_dataset", {"file_path": "data_cleaned.csv"})
        assert result.decision == GuardrailAction.ALLOW

    def test_allow_relative_safe_path(self, guardrail):
        """安全的相对路径不应触发误报。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("load_dataset", {"file_path": "output/results.csv"})
        assert result.decision == GuardrailAction.ALLOW

    def test_block_dev_path(self, guardrail):
        """/dev/null 应触发 BLOCK。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("run_code", {"output": "/dev/null"})
        assert result.decision == GuardrailAction.BLOCK

    def test_block_root_ssh(self, guardrail):
        """~/.ssh/id_rsa 应触发 BLOCK。"""
        from nini.tools.guardrails import GuardrailAction

        result = guardrail.evaluate("fetch_url", {"path": "~/.ssh/id_rsa"})
        assert result.decision == GuardrailAction.BLOCK
