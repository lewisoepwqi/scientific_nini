"""知识库内部共享工具函数。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_knowledge_file_hashes(knowledge_dir: Path) -> dict[str, str]:
    """计算知识目录下所有 .md 文件的 SHA-256 哈希。

    排除 README.md 文件。

    Args:
        knowledge_dir: 知识库目录路径

    Returns:
        字典 {relative_path_str: sha256_hex}
    """
    hashes: dict[str, str] = {}
    if not knowledge_dir.is_dir():
        return hashes

    for md_path in sorted(knowledge_dir.rglob("*.md")):
        if md_path.name.lower() == "readme.md":
            continue
        try:
            content = md_path.read_bytes()
            relative_path = str(md_path.relative_to(knowledge_dir))
            hashes[relative_path] = hashlib.sha256(content).hexdigest()
        except Exception:
            # 跳过无法读取的文件（权限问题等）
            pass

    return hashes
