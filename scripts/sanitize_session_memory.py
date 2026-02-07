"""会话历史瘦身脚本。

目标：
1. 删除历史消息中的大载荷（chart_data/data_preview 等）。
2. 压缩 tool 消息中的 JSON 内容，保留关键字段。
3. 生成原文件备份，便于回滚。
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_EVENT_TYPES_TO_FLATTEN = {"chart", "data", "artifact", "image"}


def _summarize_tool_dict(data: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("success", "message", "error", "status"):
        if key in data:
            compact[key] = data[key]
    for key in ("has_chart", "has_dataframe"):
        if key in data:
            compact[key] = bool(data.get(key))

    data_obj = data.get("data")
    if isinstance(data_obj, dict):
        compact["data_keys"] = list(data_obj.keys())[:10]

    artifacts = data.get("artifacts")
    if isinstance(artifacts, list):
        compact["artifact_count"] = len(artifacts)

    images = data.get("images")
    if isinstance(images, list):
        compact["image_count"] = len(images)
    elif isinstance(images, str) and images:
        compact["image_count"] = 1

    if not compact:
        compact["message"] = "工具执行完成"
    return compact


def _compact_tool_content(content: Any) -> str:
    text = "" if content is None else str(content)
    parsed: Any = None
    if isinstance(content, dict):
        parsed = content
    elif isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None

    if isinstance(parsed, dict):
        text = json.dumps(_summarize_tool_dict(parsed), ensure_ascii=False, default=str)

    if len(text) > 2000:
        return text[:2000] + "...(截断)"
    return text


def sanitize_memory_file(memory_path: Path) -> tuple[int, int]:
    raw_lines = memory_path.read_text(encoding="utf-8").splitlines()
    before_size = sum(len(line) for line in raw_lines)
    sanitized_lines: list[str] = []

    for line in raw_lines:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if msg.get("role") == "assistant" and msg.get("event_type") in _EVENT_TYPES_TO_FLATTEN:
            # UI 事件消息仅保留纯文本，避免历史中残留大 JSON。
            msg.pop("event_type", None)
            msg.pop("chart_data", None)
            msg.pop("data_preview", None)
            msg.pop("artifacts", None)
            msg.pop("images", None)

        if msg.get("role") == "tool":
            msg["content"] = _compact_tool_content(msg.get("content"))

        sanitized_lines.append(json.dumps(msg, ensure_ascii=False, default=str))

    memory_path.write_text("\n".join(sanitized_lines) + "\n", encoding="utf-8")
    after_size = sum(len(line) for line in sanitized_lines)
    return before_size, after_size


def sanitize_session(session_dir: Path) -> tuple[int, int] | None:
    memory_path = session_dir / "memory.jsonl"
    if not memory_path.exists():
        return None

    backup_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = session_dir / f"memory.jsonl.bak.{backup_ts}"
    shutil.copy2(memory_path, backup_path)
    return sanitize_memory_file(memory_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="瘦身会话 memory.jsonl")
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=Path("data/sessions"),
        help="会话根目录（默认 data/sessions）",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="仅处理指定会话 ID；不填则处理全部会话",
    )
    args = parser.parse_args()

    root = args.sessions_root
    if not root.exists():
        raise SystemExit(f"会话目录不存在: {root}")

    target_dirs: list[Path]
    if args.session_id:
        target = root / args.session_id
        if not target.exists():
            raise SystemExit(f"指定会话不存在: {target}")
        target_dirs = [target]
    else:
        target_dirs = [p for p in root.iterdir() if p.is_dir()]

    total_before = 0
    total_after = 0
    processed = 0

    for session_dir in target_dirs:
        result = sanitize_session(session_dir)
        if result is None:
            continue
        before, after = result
        total_before += before
        total_after += after
        processed += 1
        print(
            f"[{session_dir.name}] before={before} chars, after={after} chars, "
            f"saved={before - after} chars"
        )

    print(
        f"processed={processed}, total_before={total_before}, "
        f"total_after={total_after}, saved={total_before - total_after}"
    )


if __name__ == "__main__":
    main()
