"""AGENTS.md 项目级上下文读取逻辑。"""

from __future__ import annotations

import logging

from nini import config as nini_config

logger = logging.getLogger(__name__)


def scan_agents_md(*, max_chars: int) -> str:
    """从项目根目录及一级子目录收集 AGENTS.md。"""
    root = nini_config._get_bundle_root()
    parts: list[str] = []

    agents_file = root / "AGENTS.md"
    if agents_file.exists() and agents_file.is_file():
        try:
            content = agents_file.read_text(encoding="utf-8")
            if content.strip():
                parts.append(f"# {agents_file}\n\n{content.strip()}")
        except Exception as exc:
            logger.debug("读取根目录 AGENTS.md 失败: %s", exc)

    try:
        for subdir in sorted(root.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            sub_agents = subdir / "AGENTS.md"
            if not sub_agents.exists() or not sub_agents.is_file():
                continue
            try:
                content = sub_agents.read_text(encoding="utf-8")
                if content.strip():
                    parts.append(f"# {sub_agents}\n\n{content.strip()}")
            except Exception as exc:
                logger.debug("读取子目录 AGENTS.md 失败: %s", exc)
    except Exception as exc:
        logger.debug("扫描 AGENTS.md 失败: %s", exc)

    combined = "\n\n---\n\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "...(截断)"
    return combined
