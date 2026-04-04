"""Harness trace 本地存储与聚合分析。"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, cast

from nini.config import settings
from nini.harness.models import HarnessRunSummary, HarnessSessionSnapshot, HarnessTraceRecord
from nini.models.database import get_db, init_db


class HarnessTraceStore:
    """管理 harness trace 的本地存储。"""

    _schema_ready_db_paths: set[str] = set()
    _schema_lock = asyncio.Lock()

    def _base_dir(self, session_id: str) -> Path:
        return settings.sessions_dir / session_id / "harness" / "traces"

    def _trace_path(self, session_id: str, run_id: str) -> Path:
        return self._base_dir(session_id) / f"{run_id}.json"

    def _jsonl_path(self, session_id: str) -> Path:
        return self._base_dir(session_id) / "runs.jsonl"

    def _snapshot_dir(self, session_id: str) -> Path:
        return settings.sessions_dir / session_id / "harness" / "snapshots"

    def _snapshot_path(self, session_id: str, turn_id: str) -> Path:
        return self._snapshot_dir(session_id) / f"{turn_id}.json"

    async def save_run(self, record: HarnessTraceRecord) -> HarnessRunSummary:
        """保存运行明细与 SQLite 摘要。"""
        base_dir = self._base_dir(record.session_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        trace_path = self._trace_path(record.session_id, record.run_id)
        trace_path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        runtime_snapshot_payload = None
        if isinstance(record.summary, dict):
            raw_snapshot = record.summary.get("runtime_snapshot")
            if isinstance(raw_snapshot, dict):
                runtime_snapshot_payload = dict(raw_snapshot)
        if runtime_snapshot_payload is not None:
            runtime_snapshot_payload["trace_ref"] = str(trace_path)
            snapshot = HarnessSessionSnapshot.model_validate(runtime_snapshot_payload)
            self._save_snapshot(snapshot)

        with self._jsonl_path(record.session_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")

        summary = HarnessRunSummary(
            run_id=record.run_id,
            session_id=record.session_id,
            turn_id=record.turn_id,
            task_id=record.task_id,
            recipe_id=record.recipe_id,
            status=record.status,
            failure_tags=record.failure_tags,
            recovery_count=(record.task_metrics.recovery_count if record.task_metrics else 0),
            budget_warning_count=len(record.budget_warnings),
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

    def _save_snapshot(self, snapshot: HarnessSessionSnapshot) -> None:
        snapshot_dir = self._snapshot_dir(snapshot.session_id)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_path(snapshot.session_id, snapshot.turn_id).write_text(
            json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _save_summary(self, summary: HarnessRunSummary) -> None:
        await self._ensure_schema()
        async with await get_db() as db:
            await db.execute(
                """
                INSERT INTO harness_runs(
                    run_id, session_id, turn_id, task_id, recipe_id, status, failure_tags,
                    recovery_count, budget_warning_count,
                    duration_ms, input_tokens, output_tokens, estimated_cost_usd,
                    trace_path, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    task_id=excluded.task_id,
                    recipe_id=excluded.recipe_id,
                    status=excluded.status,
                    failure_tags=excluded.failure_tags,
                    recovery_count=excluded.recovery_count,
                    budget_warning_count=excluded.budget_warning_count,
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
                    summary.task_id,
                    summary.recipe_id,
                    summary.status,
                    json.dumps(summary.failure_tags, ensure_ascii=False),
                    summary.recovery_count,
                    summary.budget_warning_count,
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
        db_path = str(settings.db_path.resolve())
        if db_path in cls._schema_ready_db_paths:
            return
        async with cls._schema_lock:
            if db_path in cls._schema_ready_db_paths:
                return
            await init_db()
            async with await get_db() as db:
                for ddl in (
                    "ALTER TABLE harness_runs ADD COLUMN task_id TEXT",
                    "ALTER TABLE harness_runs ADD COLUMN recipe_id TEXT",
                    "ALTER TABLE harness_runs ADD COLUMN recovery_count INTEGER DEFAULT 0",
                    "ALTER TABLE harness_runs ADD COLUMN budget_warning_count INTEGER DEFAULT 0",
                ):
                    try:
                        await db.execute(ddl)
                    except Exception:
                        pass
                await db.commit()
            cls._schema_ready_db_paths.add(db_path)

    async def list_runs(
        self,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[HarnessRunSummary]:
        """读取摘要列表。"""
        await self._ensure_schema()
        query = (
            "SELECT run_id, session_id, turn_id, task_id, recipe_id, status, failure_tags, "
            "recovery_count, budget_warning_count, duration_ms, input_tokens, output_tokens, "
            "estimated_cost_usd, trace_path, created_at, updated_at "
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

        summaries: list[HarnessRunSummary] = []
        for row in rows:
            row_data = cast(Mapping[str, Any], row)
            summaries.append(
                HarnessRunSummary(
                    run_id=str(row_data["run_id"]),
                    session_id=str(row_data["session_id"]),
                    turn_id=str(row_data["turn_id"]),
                    task_id=str(row_data["task_id"]) if row_data["task_id"] is not None else None,
                    recipe_id=(
                        str(row_data["recipe_id"]) if row_data["recipe_id"] is not None else None
                    ),
                    status=str(row_data["status"]),
                    failure_tags=json.loads(str(row_data["failure_tags"] or "[]")),
                    recovery_count=int(row_data["recovery_count"] or 0),
                    budget_warning_count=int(row_data["budget_warning_count"] or 0),
                    duration_ms=int(row_data["duration_ms"] or 0),
                    input_tokens=int(row_data["input_tokens"] or 0),
                    output_tokens=int(row_data["output_tokens"] or 0),
                    estimated_cost_usd=float(row_data["estimated_cost_usd"] or 0.0),
                    trace_path=str(row_data["trace_path"]),
                    created_at=str(row_data["created_at"]),
                    updated_at=str(row_data["updated_at"]),
                )
            )
        return summaries

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
            "task_id": record.task_id,
            "recipe_id": record.recipe_id,
            "status": record.status,
            "failure_tags": record.failure_tags,
            "budget_warnings": [item.model_dump(mode="json") for item in record.budget_warnings],
            "task_metrics": (
                record.task_metrics.model_dump(mode="json") if record.task_metrics else None
            ),
            "completion_checks": [
                item.model_dump(mode="json") for item in record.completion_checks
            ],
            "blocked": record.blocked.model_dump(mode="json") if record.blocked else None,
            "events": [event.model_dump(mode="json") for event in record.events],
        }

    def load_snapshot(self, session_id: str, turn_id: str) -> HarnessSessionSnapshot:
        """读取指定轮次的运行快照。"""
        path = self._snapshot_path(session_id, turn_id)
        if not path.exists():
            raise FileNotFoundError(turn_id)
        return HarnessSessionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def load_latest_snapshot(self, session_id: str) -> HarnessSessionSnapshot:
        """读取指定会话最近一轮的运行快照。"""
        snapshot_dir = self._snapshot_dir(session_id)
        if not snapshot_dir.exists():
            raise FileNotFoundError(session_id)
        candidates = sorted(
            snapshot_dir.glob("*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(session_id)
        return HarnessSessionSnapshot.model_validate_json(candidates[0].read_text(encoding="utf-8"))

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

    def _evaluate_core_recipe_benchmarks_from_summaries(
        self,
        summaries: list[HarnessRunSummary],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """基于摘要列表评估核心 Recipe 基准集。"""
        config_path = Path(__file__).resolve().parents[1] / "config" / "core_recipe_benchmarks.json"
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        thresholds = payload.get("gate_thresholds", {})
        benchmark_defs = payload.get("benchmarks", [])

        latest_by_recipe: dict[str, HarnessRunSummary] = {}
        for item in summaries:
            recipe_id = str(item.recipe_id or "").strip()
            if recipe_id and recipe_id not in latest_by_recipe:
                latest_by_recipe[recipe_id] = item

        results: list[dict[str, Any]] = []
        required_total = 0
        required_present = 0
        passed_total = 0
        for item in benchmark_defs:
            if not isinstance(item, dict):
                continue
            recipe_id = str(item.get("recipe_id", "")).strip()
            expected_status = str(item.get("expected_status", "completed")).strip() or "completed"
            required = bool(item.get("required", False))
            benchmark_id = str(item.get("benchmark_id", recipe_id)).strip() or recipe_id
            if required:
                required_total += 1
            matched = latest_by_recipe.get(recipe_id)
            if matched is not None and required:
                required_present += 1
            passed = matched is not None and matched.status == expected_status
            if passed:
                passed_total += 1
            results.append(
                {
                    "benchmark_id": benchmark_id,
                    "recipe_id": recipe_id,
                    "expected_status": expected_status,
                    "required": required,
                    "run_id": matched.run_id if matched is not None else None,
                    "actual_status": matched.status if matched is not None else "missing",
                    "failure_tags": matched.failure_tags if matched is not None else [],
                    "passed": passed,
                }
            )

        total = len(results)
        pass_rate = (passed_total / total) if total else 0.0
        coverage = (required_present / required_total) if required_total else 1.0
        min_pass_rate = float(thresholds.get("min_pass_rate", 1.0) or 1.0)
        required_coverage = float(thresholds.get("required_coverage", 1.0) or 1.0)
        gate_passed = pass_rate >= min_pass_rate and coverage >= required_coverage
        gate_failure_counter: Counter[str] = Counter()
        for item in summaries:
            if item.failure_tags:
                gate_failure_counter.update(item.failure_tags)
            elif item.status != "completed":
                gate_failure_counter.update(["unknown_failure"])
        for item in results:
            if item.get("passed"):
                continue
            actual_status = str(item.get("actual_status", "missing")).strip() or "missing"
            gate_failure_counter.update([f"benchmark:{actual_status}"])

        return {
            "total_runs": len(summaries),
            "failure_distribution": dict(gate_failure_counter),
            "core_recipe_benchmarks": {
                "gate_passed": gate_passed,
                "gate_thresholds": {
                    "min_pass_rate": min_pass_rate,
                    "required_coverage": required_coverage,
                },
                "pass_rate": round(pass_rate, 4),
                "required_coverage": round(coverage, 4),
                "top_failure_tags": gate_failure_counter.most_common(5),
                "sample_results": results,
            },
        }

    async def evaluate_core_recipe_benchmarks_async(
        self, session_id: str | None = None
    ) -> dict[str, Any]:
        """异步评估核心 Recipe 基准集。"""
        summaries = await self.list_runs(session_id=session_id, limit=500)
        return self._evaluate_core_recipe_benchmarks_from_summaries(
            summaries, session_id=session_id
        )

    def evaluate_core_recipe_benchmarks(self, session_id: str | None = None) -> dict[str, Any]:
        """评估核心 Recipe 基准集的最近一次回放结果。"""
        summaries = asyncio.run(self.list_runs(session_id=session_id, limit=500))
        return self._evaluate_core_recipe_benchmarks_from_summaries(
            summaries, session_id=session_id
        )

    @staticmethod
    def _duration_ms(record: HarnessTraceRecord) -> int:
        if not record.finished_at:
            return 0
        started = datetime.fromisoformat(record.started_at)
        finished = datetime.fromisoformat(record.finished_at)
        return max(0, int((finished - started).total_seconds() * 1000))
