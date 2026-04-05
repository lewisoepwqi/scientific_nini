"""子 Agent 执行快照。

每次 SubAgent 执行结束后生成不可变快照，作为调试、回放和可观测性的统一数据源。
参考 claw-code RuntimeSession.as_markdown() 的设计思路：快照即文档，无需外部工具即可诊断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SubAgentRunSnapshot:
    """单次子 Agent 执行的不可变快照。

    字段说明：
    - run_id:            本次执行的唯一标识
    - agent_id:          Agent 定义 ID
    - agent_name:        Agent 显示名称
    - task:              分配的任务描述（截断至 500 字符）
    - stop_reason:       终止原因（'completed'/'timeout'/'error'/'stopped'/'missing_agent'/'max_retries'/'permission_denied'）
    - success:           是否成功
    - execution_time_ms: 执行耗时（毫秒）
    - tool_calls:        本次执行调用的工具名称列表
    - artifact_keys:     产生的 artifact key 列表
    - document_keys:     产生的 document key 列表
    - summary:           执行结果摘要（截断至 500 字符）
    - error:             错误信息（失败时）
    - attempt:           重试轮次（从 1 开始）
    - parent_session_id: 父会话 ID
    - child_session_id:  子会话 ID
    - created_at:        快照生成时间（ISO 8601 UTC）
    """

    run_id: str
    agent_id: str
    task: str
    stop_reason: str
    success: bool
    execution_time_ms: int
    agent_name: str = ""
    tool_calls: tuple[str, ...] = field(default_factory=tuple)
    artifact_keys: tuple[str, ...] = field(default_factory=tuple)
    document_keys: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""
    error: str = ""
    attempt: int = 1
    parent_session_id: str = ""
    child_session_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_result(cls, result: Any, *, attempt: int = 1) -> "SubAgentRunSnapshot":
        """从 SubAgentResult 构建快照。"""
        # 从 artifacts 中提取工具调用记录（若存在）
        artifacts = getattr(result, "artifacts", {}) or {}
        tool_calls: tuple[str, ...] = tuple(
            str(v) for v in artifacts.get("_tool_calls", [])
        ) if isinstance(artifacts.get("_tool_calls"), list) else ()

        stop_reason = getattr(result, "stop_reason", "") or ""
        if not stop_reason:
            if getattr(result, "stopped", False):
                stop_reason = "stopped"
            elif getattr(result, "success", False):
                stop_reason = "completed"
            else:
                stop_reason = "error"

        return cls(
            run_id=str(getattr(result, "run_id", "") or ""),
            agent_id=str(getattr(result, "agent_id", "") or ""),
            agent_name=str(getattr(result, "agent_name", "") or ""),
            task=str(getattr(result, "task", "") or "")[:500],
            stop_reason=stop_reason,
            success=bool(getattr(result, "success", False)),
            execution_time_ms=int(getattr(result, "execution_time_ms", 0) or 0),
            tool_calls=tool_calls,
            artifact_keys=tuple(k for k in artifacts if not k.startswith("_")),
            document_keys=tuple((getattr(result, "documents", {}) or {}).keys()),
            summary=str(getattr(result, "summary", "") or "")[:500],
            error=str(getattr(result, "error", "") or ""),
            attempt=attempt,
            parent_session_id=str(getattr(result, "parent_session_id", "") or ""),
            child_session_id=str(getattr(result, "child_session_id", "") or ""),
        )

    def as_markdown(self) -> str:
        """将快照渲染为可读的 Markdown 报告（参考 claw-code RuntimeSession.as_markdown()）。"""
        status = "✅ 成功" if self.success else ("⏹ 已停止" if self.stop_reason == "stopped" else "❌ 失败")
        lines = [
            f"# Sub-Agent 执行快照",
            f"",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| run_id | `{self.run_id}` |",
            f"| agent_id | `{self.agent_id}` |",
            f"| agent_name | {self.agent_name} |",
            f"| 状态 | {status} |",
            f"| stop_reason | `{self.stop_reason}` |",
            f"| 耗时 | {self.execution_time_ms} ms |",
            f"| 轮次 | {self.attempt} |",
            f"| 父会话 | `{self.parent_session_id}` |",
            f"| 子会话 | `{self.child_session_id}` |",
            f"| 生成时间 | {self.created_at} |",
            f"",
            f"## 任务",
            f"",
            self.task or "（无）",
            f"",
            f"## 摘要",
            f"",
            self.summary or "（无）",
        ]
        if self.error:
            lines += ["", "## 错误", "", self.error]
        if self.tool_calls:
            lines += ["", "## 工具调用", ""]
            lines += [f"- `{t}`" for t in self.tool_calls]
        if self.artifact_keys:
            lines += ["", "## 产出物", ""]
            lines += [f"- `{k}`" for k in self.artifact_keys]
        if self.document_keys:
            lines += ["", "## 文档", ""]
            lines += [f"- `{k}`" for k in self.document_keys]
        return "\n".join(lines)
