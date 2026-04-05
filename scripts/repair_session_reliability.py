"""修复会话可靠性问题的回填脚本。

修复范围：
1. 清理/降级历史遗留的非阻塞 pending actions（如 task_state 幂等冲突）。
2. 修复 AnalysisMemory 中缺失统计值却被误判为不显著的相关分析结果。
3. 删除被错误统计记忆污染的长期记忆条目，并回写正确结果。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr

from nini.config import settings
from nini.memory.db import get_session_db, load_meta_from_db, upsert_meta_fields
from nini.memory.compression import AnalysisMemory, StatisticResult, list_session_analysis_memories
from nini.memory.long_term_memory import consolidate_session_memories, get_long_term_memory_store

_CORRELATION_TEST_RE = re.compile(r"^(Pearson|Spearman|Kendall) 相关性分析")
_PAIRWISE_CORRELATION_RE = re.compile(
    r"^(Pearson|Spearman|Kendall) 相关性分析（(?P<left>.+?) vs (?P<right>.+?)）$"
)
_BINARY_READ_BLOCKED_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".xlsm",
    ".xlsb",
    ".ods",
    ".parquet",
    ".feather",
    ".arrow",
    ".npy",
    ".npz",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".zip",
}


def _load_meta(session_dir: Path) -> dict[str, Any]:
    try:
        conn = get_session_db(session_dir, create=False)
        if conn is not None:
            try:
                db_meta = load_meta_from_db(conn)
                if db_meta:
                    return db_meta
            finally:
                conn.close()
    except Exception:
        pass

    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_meta(session_dir: Path, meta: dict[str, Any]) -> None:
    meta_path = session_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    try:
        conn = get_session_db(session_dir, create=True)
        if conn is not None:
            try:
                upsert_meta_fields(conn, meta)
            finally:
                conn.close()
    except Exception:
        pass


def _load_session_messages(session_dir: Path) -> list[dict[str, Any]]:
    db_path = session_dir / "session.db"
    rows: list[str] = []
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT raw_json FROM messages ORDER BY id")
            rows.extend(row[0] for row in cursor.fetchall())
            cursor = conn.execute("SELECT raw_json FROM archived_messages ORDER BY id")
            rows.extend(row[0] for row in cursor.fetchall())
        finally:
            conn.close()
    else:
        for path in [session_dir / "memory.jsonl", *(session_dir / "archive").glob("*.json")]:
            if not path.exists():
                continue
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".jsonl":
                rows.extend(line for line in raw.splitlines() if line.strip())
            else:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, list):
                    rows.extend(
                        json.dumps(item, ensure_ascii=False)
                        for item in payload
                        if isinstance(item, dict)
                    )

    messages: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            messages.append(payload)
    return messages


def _extract_correlation_invocations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict) or function.get("name") != "stat_model":
                continue
            raw_arguments = function.get("arguments")
            if not isinstance(raw_arguments, str):
                continue
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                continue
            if arguments.get("method") != "correlation":
                continue
            columns = arguments.get("columns")
            if not isinstance(columns, list) or len(columns) < 2:
                continue
            dataset_name = str(arguments.get("dataset_name", "")).strip()
            correlation_method = str(arguments.get("correlation_method", "pearson")).strip().lower()
            invocations.append(
                {
                    "dataset_name": dataset_name,
                    "method": correlation_method or "pearson",
                    "columns": [str(column).strip() for column in columns if str(column).strip()],
                }
            )
    return invocations


def _resolve_dataset_path(session_dir: Path, dataset_name: str) -> Path | None:
    if not dataset_name:
        return None
    uploads_dir = session_dir / "workspace" / "uploads"
    if not uploads_dir.exists():
        return None
    candidates = sorted(uploads_dir.glob(f"*{dataset_name}"))
    if candidates:
        return candidates[0]
    exact = uploads_dir / dataset_name
    return exact if exact.exists() else None


def _compute_pairwise_correlation(
    session_dir: Path,
    *,
    dataset_name: str,
    method: str,
    columns: list[str],
) -> list[StatisticResult]:
    dataset_path = _resolve_dataset_path(session_dir, dataset_name)
    if dataset_path is None:
        return []

    if dataset_path.suffix.lower() == ".csv":
        df = pd.read_csv(dataset_path)
    else:
        df = pd.read_excel(dataset_path)
    data = df[columns].dropna()
    corr_func = {
        "pearson": pearsonr,
        "spearman": spearmanr,
        "kendall": kendalltau,
    }.get(method, pearsonr)
    corr_matrix = data.corr(method=method)

    results: list[StatisticResult] = []
    for index, left in enumerate(columns):
        for right in columns[index + 1 :]:
            coefficient = corr_matrix.loc[left, right]
            _, p_value = corr_func(data[left].values, data[right].values)
            results.append(
                StatisticResult(
                    test_name=f"{method.title()} 相关性分析（{left} vs {right}）",
                    p_value=float(p_value),
                    effect_size=float(coefficient),
                    effect_type=f"{method}_correlation",
                    significant=bool(p_value < 0.05),
                    metadata={
                        "dataset_name": dataset_name,
                        "method": method,
                        "sample_size": int(len(data)),
                        "variables": [left, right],
                        "var_a": left,
                        "var_b": right,
                        "coefficient": float(coefficient),
                    },
                )
            )
    return results


def _is_non_blocking_task_conflict(item: dict[str, Any]) -> bool:
    if str(item.get("type", "")).strip() != "tool_failure_unresolved":
        return False
    if str(item.get("source_tool", "")).strip() not in {"task_state", "task_write"}:
        return False
    summary = str(item.get("summary", "")).strip()
    key = str(item.get("key", "")).strip()
    return (
        "无法重新初始化" in summary
        or "无需重复设置" in summary
        or key.startswith('task_state::{"operation": "init"')
        or key.startswith('task_write::{"mode": "init"')
    )


def _extract_workspace_read_path(signature: str) -> str:
    prefix = "workspace_session::"
    if not signature.startswith(prefix):
        return ""
    try:
        payload = json.loads(signature[len(prefix) :])
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    if str(payload.get("operation", "")).strip() != "read":
        return ""
    return str(payload.get("file_path", "")).strip()


def _resolve_workspace_upload_target(session_dir: Path, file_path: str) -> Path | None:
    normalized = str(file_path or "").strip().strip("/")
    if not normalized:
        return None

    workspace_root = session_dir / "workspace"
    direct_path = workspace_root / normalized
    if direct_path.exists():
        return direct_path

    uploads_dir = workspace_root / "uploads"
    if not uploads_dir.exists():
        return None

    target_name = Path(normalized).name
    exact_path = uploads_dir / target_name
    if exact_path.exists():
        return exact_path

    candidates = sorted(uploads_dir.glob(f"*_{target_name}"))
    if candidates:
        return candidates[0]
    return None


def _is_non_blocking_workspace_read_failure(item: dict[str, Any], session_dir: Path) -> bool:
    if str(item.get("type", "")).strip() != "tool_failure_unresolved":
        return False
    if str(item.get("source_tool", "")).strip() != "workspace_session":
        return False

    signature = str(item.get("key", "")).strip()
    summary = str(item.get("summary", "")).strip()
    file_path = _extract_workspace_read_path(signature)
    if not file_path:
        return False

    resolved_target = _resolve_workspace_upload_target(session_dir, file_path)
    if (
        resolved_target is not None
        and "/" not in file_path
        and Path(file_path).name == file_path
        and "文件不存在" in summary
    ):
        return True

    suffix = Path(file_path).suffix.lower()
    if resolved_target is not None:
        suffix = resolved_target.suffix.lower()
    if suffix in _BINARY_READ_BLOCKED_EXTENSIONS and (
        "decode" in summary.lower()
        or "utf-8" in summary.lower()
        or "二进制" in summary
        or "excel" in summary.lower()
    ):
        return True

    return False


def repair_pending_actions(session_dir: Path, *, apply_changes: bool) -> dict[str, int]:
    meta = _load_meta(session_dir)
    pending_actions = meta.get("pending_actions")
    if not isinstance(pending_actions, list):
        return {"removed_pending_actions": 0}

    remaining = [
        item
        for item in pending_actions
        if not (
            isinstance(item, dict)
            and (
                _is_non_blocking_task_conflict(item)
                or _is_non_blocking_workspace_read_failure(item, session_dir)
            )
        )
    ]
    removed = len(pending_actions) - len(remaining)
    if removed and apply_changes:
        meta["pending_actions"] = remaining
        _save_meta(session_dir, meta)
    return {"removed_pending_actions": removed}


def _dedupe_statistics(statistics: list[StatisticResult]) -> list[StatisticResult]:
    deduped: list[StatisticResult] = []
    seen: set[tuple[Any, ...]] = set()
    for statistic in statistics:
        metadata = statistic.metadata if isinstance(statistic.metadata, dict) else {}
        signature = (
            statistic.test_name,
            statistic.test_statistic,
            statistic.p_value,
            statistic.effect_size,
            statistic.effect_type,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(statistic)
    return deduped


def repair_analysis_memories(
    session_id: str,
    *,
    session_dir: Path,
    apply_changes: bool,
) -> dict[str, int]:
    messages = _load_session_messages(session_dir)
    invocations = _extract_correlation_invocations(messages)
    invocations_by_dataset: dict[str, list[dict[str, Any]]] = {}
    for invocation in invocations:
        dataset_name = str(invocation.get("dataset_name", "")).strip()
        if dataset_name:
            invocations_by_dataset.setdefault(dataset_name, []).append(invocation)

    store = get_long_term_memory_store()
    deleted_ltm_ids: set[str] = set()
    repaired_statistics = 0
    downgraded_statistics = 0

    for memory in list_session_analysis_memories(session_id):
        next_statistics: list[StatisticResult] = []
        should_save = False
        used_rebuild = False

        latest_invocation = None
        dataset_invocations = invocations_by_dataset.get(memory.dataset_name, [])
        if dataset_invocations:
            latest_invocation = dataset_invocations[-1]

        for statistic in memory.statistics:
            pair_match = _PAIRWISE_CORRELATION_RE.match(statistic.test_name)
            generic_correlation = bool(_CORRELATION_TEST_RE.match(statistic.test_name))
            missing_values = (
                statistic.p_value is None
                and statistic.effect_size is None
                and statistic.test_statistic is None
            )

            if pair_match and missing_values:
                method = pair_match.group(1).lower()
                left = pair_match.group("left")
                right = pair_match.group("right")
                rebuilt = _compute_pairwise_correlation(
                    session_dir,
                    dataset_name=memory.dataset_name,
                    method=method,
                    columns=[left, right],
                )
                if rebuilt:
                    next_statistics.extend(rebuilt)
                    should_save = True
                    repaired_statistics += 1
                    if (
                        statistic.ltm_id
                        and statistic.ltm_id not in deleted_ltm_ids
                        and apply_changes
                    ):
                        store.delete_memory(statistic.ltm_id)
                        deleted_ltm_ids.add(statistic.ltm_id)
                    continue

            if generic_correlation and missing_values and latest_invocation is not None:
                rebuilt = _compute_pairwise_correlation(
                    session_dir,
                    dataset_name=memory.dataset_name,
                    method=str(latest_invocation.get("method", "pearson")),
                    columns=list(latest_invocation.get("columns", [])),
                )
                if rebuilt:
                    next_statistics.extend(rebuilt)
                    should_save = True
                    used_rebuild = True
                    repaired_statistics += len(rebuilt)
                    if (
                        statistic.ltm_id
                        and statistic.ltm_id not in deleted_ltm_ids
                        and apply_changes
                    ):
                        store.delete_memory(statistic.ltm_id)
                        deleted_ltm_ids.add(statistic.ltm_id)
                    continue

            if missing_values and statistic.significant is False:
                statistic.significant = None
                should_save = True
                downgraded_statistics += 1
                if statistic.ltm_id and statistic.ltm_id not in deleted_ltm_ids and apply_changes:
                    store.delete_memory(statistic.ltm_id)
                    deleted_ltm_ids.add(statistic.ltm_id)
                statistic.ltm_id = ""

            next_statistics.append(statistic)

        if used_rebuild:
            next_statistics = [
                item
                for item in next_statistics
                if not (
                    _CORRELATION_TEST_RE.match(item.test_name)
                    and item.p_value is None
                    and item.effect_size is None
                )
            ]

        if should_save and apply_changes:
            memory.statistics = _dedupe_statistics(next_statistics)
            memory.updated_at = __import__("time").time()
            from nini.memory.compression import save_analysis_memory

            save_analysis_memory(memory)

    if apply_changes and (repaired_statistics or downgraded_statistics):
        asyncio.run(consolidate_session_memories(session_id))

    return {
        "repaired_statistics": repaired_statistics,
        "downgraded_statistics": downgraded_statistics,
        "deleted_ltm_entries": len(deleted_ltm_ids),
    }


def repair_session(session_id: str, *, apply_changes: bool) -> dict[str, Any]:
    session_dir = settings.sessions_dir / session_id
    report = {"session_id": session_id}
    report.update(repair_pending_actions(session_dir, apply_changes=apply_changes))
    report.update(
        repair_analysis_memories(session_id, session_dir=session_dir, apply_changes=apply_changes)
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="修复会话统计记忆和 pending actions")
    parser.add_argument("--session-id", type=str, default=None, help="仅修复指定会话")
    parser.add_argument("--dry-run", action="store_true", help="仅输出预计修复内容，不写回")
    args = parser.parse_args()

    target_ids: list[str]
    if args.session_id:
        target_ids = [args.session_id]
    else:
        target_ids = [path.name for path in settings.sessions_dir.iterdir() if path.is_dir()]

    total = {
        "removed_pending_actions": 0,
        "repaired_statistics": 0,
        "downgraded_statistics": 0,
        "deleted_ltm_entries": 0,
    }

    for session_id in target_ids:
        report = repair_session(session_id, apply_changes=not args.dry_run)
        for key in total:
            total[key] += int(report.get(key, 0) or 0)
        print(json.dumps(report, ensure_ascii=False))

    print(json.dumps({"summary": total, "dry_run": bool(args.dry_run)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
