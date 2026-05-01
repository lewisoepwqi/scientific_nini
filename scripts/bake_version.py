"""将构建版本号烧录到 src/nini/__init__.py 和 src/nini/version.py。

在 PyInstaller 打包前调用，确保冻结环境中 get_current_version() 返回正确版本。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _update_file(path: Path, pattern: str, replacement: str, label: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated = re.sub(pattern, replacement, original, count=1)
    if updated == original:
        print(f"[WARN] {label}: 未找到匹配模式，文件未变更: {path}")
        return
    path.write_text(updated, encoding="utf-8")
    print(f"[OK] {label} → {path}")


def main(argv: list[str] | None = None) -> int:
    args = (argv or sys.argv)[1:]
    if not args:
        print("用法: bake_version.py <version>", file=sys.stderr)
        return 1

    version = args[0].strip()
    if not version:
        print("版本号不能为空", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parent.parent

    _update_file(
        root / "src" / "nini" / "__init__.py",
        r'__version__\s*=\s*["\'][^"\']*["\']',
        f'__version__ = "{version}"',
        "__version__",
    )

    _update_file(
        root / "src" / "nini" / "version.py",
        r'FALLBACK_VERSION\s*=\s*["\'][^"\']*["\']',
        f'FALLBACK_VERSION = "{version}"',
        "FALLBACK_VERSION",
    )

    _update_file(
        root / "pyproject.toml",
        r'(?m)^version\s*=\s*["\'][^"\']*["\']',
        f'version = "{version}"',
        "pyproject.toml version",
    )

    print(f"版本烧录完成: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
