"""Harness trace 本地存储与聚合分析。"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from nini.config import settings
from nini.harness.models import HarnessRunSummary, HarnessTraceRecord
from nini.models.database import get_db, init_db


class HarnessTraceStore:
    """管理 harness trace 的本地存储。"""

    _schema_ready = False
    _schema_lock = asyncio.Lock()

    def _base_dir(self, session_id: str) -> Path:
        return settings.sessions_dir / session_id / "harness" / "traces"

    def _trace_path(self, session_id: str, run_id: str) -> Path:
        return self._base_dir(session_id) / f"{run_id}.json"

    def _jsonl_path(self, session_id: str) -> Path:
        return self._base_dir(session_id) / "runs.jsonl"

    async def save_run(self, record: HarnessTraceRecord) -> HarnessRunSummary:
        """保存运行明细与 SQLite 摘要。"""
        base_dir = self._base_dir(record.session_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        trace_path = self._trace_path(record.session_id, record.run_id)
        trace_path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with self._jsonl_path(record.session_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

        summary = HarnessRunSummary(
            run_id=record.run_id,
            session_id=record.session_id,
            turn_id=record.turn_id,
            status=record.status,
            failure_tags=record.failure_tags,
            duration_ms=self._duration_ms(record),
            input_tokens=int(record.summary.get("input_tokens", 0) or 0),
            output_tokens=int(record.summary.get("output_tokens", 0) or 0),
            estimated_cost_usd=float(record.summary.get("estimated_cost_usd", 0.0) or 0.0),
            trace_path=str(trace_path),
            created_at=record.started_at,
            updated_at=record.finished_at or record.started_at,
        )
        await self._save_summary(summary)
        return summary

    async def _save_summary(self, summary: HarnessRunSummary) -> None:
        await self._ensure_schema()
        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO harness_runs(
                    run_id, session_id, turn_id, status, failure_tags,
                    duration_ms, input_tokens, output_tokens, estimated_cost_usd,
                    trace_path, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    failure_tags=excluded.failure_tags,
                    duration_ms=excluded.duration_ms,
                    input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,
                    estimated_cost_usd=excluded.estimated_cost_usd,
                    trace_path=excluded.trace_path,
                    updated_at=excluded.updated_at
                """,
                (
                    summary.run_id,
                    summary.session_id,
                    summary.turn_id,
                    summary.status,
                    json.dumps(summary.failure_tags, ensure_ascii=False),
                    summary.duration_ms,
                    summary.input_tokens,
                    summary.output_tokens,
                    summary.estimated_cost_usd,
                    summary.trace_path,
                    summary.created_at,
                    summary.updated_at,
                ),
            )
            await db.commit()

    @classmethod
    async def _ensure_schema(cls) -> None:
        if cls._schema_ready:
            return
        async with cls._schema_lock:
            if cls._schema_ready:
                return
            await init_db()
            cls._schema_ready = True

    async def list_runs(
        self,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[HarnessRunSummary]:
        """读取摘要列表。"""
        query = (
            "SELECT run_id, session_id, turn_id, status, failure_tags, duration_ms, "
            "input_tokens, output_tokens, estimated_cost_usd, trace_path, created_at, updated_at "
            "FROM harness_runs"
        )
        params: list[Any] = []
        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with await get_db() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [
            HarnessRunSummary(
                run_id=str(row["run_id"]),
                session_id=str(row["session_id"]),
                turn_id=str(row["turn_id"]),
                status=str(row["status"]),
                failure_tags=json.loads(str(row["failure_tags"] or "[]")),
                duration_ms=int(row["duration_ms"] or 0),
                input_tokens=int(row["input_tokens"] or 0),
                output_tokens=int(row["output_tokens"] or 0),
                estimated_cost_usd=float(row["estimated_cost_usd"] or 0.0),
                trace_path=str(row["trace_path"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def load_run(self, run_id: str, session_id: str | None = None) -> HarnessTraceRecord:
        """读取单次运行明细。"""
        if session_id:
            candidate = self._trace_path(session_id, run_id)
            if candidate.exists():
                return HarnessTraceRecord.model_validate_json(candidate.read_text(encoding="utf-8"))

        for path in settings.sessions_dir.glob(f"*/harness/traces/{run_id}.json"):
            return HarnessTraceRecord.model_validate_json(path.read_text(encoding="utf-8"))
        raise FileNotFoundError(run_id)

    def replay_run(self, run_id: str, session_id: str | None = None) -> dict[str, Any]:
        """返回单次运行的可读回放摘要。"""
        record = self.load_run(run_id, session_id=session_id)
        return {
            "run_id": record.run_id,
            "session_id": record.session_id,
            "turn_id": record.turn_id,
            "status": record.status,
            "failure_tags": record.failure_tags,
            "completion_checks": [
                item.model_dump(mode="json") for item in record.completion_checks
            ],
            "blocked": record.blocked.model_dump(mode="json") if record.blocked else None,
            "events": [event.model_dump(mode="json") for event in record.events],
        }

    async def aggregate_failures(self, session_id: str | None = None) -> dict[str, Any]:
        """聚合失败标签分布。"""
        summaries = await self.list_runs(session_id=session_id, limit=500)
        counter: Counter[str] = Counter()
        for item in summaries:
            if item.failure_tags:
                counter.update(item.failure_tags)
            elif item.status != "completed":
                counter.update(["unknown_failure"])

        return {
            "total_runs": len(summaries),
            "failure_distribution": dict(counter),
        }

    @staticmethod
    def _duration_ms(record: HarnessTraceRecord) -> int:
        if not record.finished_at:
            return 0
        started = datetime.fromisoformat(record.started_at)
        finished = datetime.fromisoformat(record.finished_at)
        return max(0, int((finished - started).total_seconds() * 1000))
