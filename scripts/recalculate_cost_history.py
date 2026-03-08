"""按当前定价表重算历史会话成本记录。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nini.config import settings
from nini.utils.token_counter import estimate_cost


def _recalculate_record(data: dict) -> tuple[dict, bool]:
    """按当前定价重算单条记录的 cost_usd。"""
    model = str(data.get("model", "unknown"))
    input_tokens = int(data.get("input_tokens", 0) or 0)
    output_tokens = int(data.get("output_tokens", 0) or 0)
    new_cost, _status = estimate_cost(model, input_tokens, output_tokens)
    changed = data.get("cost_usd") != new_cost
    data["cost_usd"] = new_cost
    return data, changed


def _iter_cost_files(root: Path) -> list[Path]:
    """查找所有会话成本文件。"""
    if not root.exists():
        return []
    return sorted(root.glob("*/cost.jsonl"))


def main() -> int:
    parser = argparse.ArgumentParser(description="按当前 pricing 重算历史 cost.jsonl")
    parser.add_argument(
        "--session-id",
        help="仅重算指定会话 ID；不传则重算全部会话",
    )
    args = parser.parse_args()

    sessions_dir = Path(settings.sessions_dir)
    if args.session_id:
        target_files = [sessions_dir / args.session_id / "cost.jsonl"]
    else:
        target_files = _iter_cost_files(sessions_dir)

    updated_files = 0
    updated_records = 0

    for cost_file in target_files:
        if not cost_file.exists():
            continue

        changed = False
        new_lines: list[str] = []

        for raw_line in cost_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(raw_line)
                continue

            next_data, record_changed = _recalculate_record(data)
            changed = changed or record_changed
            if record_changed:
                updated_records += 1
            new_lines.append(json.dumps(next_data, ensure_ascii=False))

        if changed:
            cost_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            updated_files += 1

    print(f"updated_files={updated_files}")
    print(f"updated_records={updated_records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
