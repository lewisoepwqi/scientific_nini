"""构建时脚本：加密打包版内置密钥，写入 src/nini/_builtin_key.py。

用法：
    NINI_BUILTIN_DASHSCOPE_API_KEY=sk-xxx python scripts/encrypt_builtin_key.py
    NINI_TRIAL_API_KEY=sk-xxx python scripts/encrypt_builtin_key.py
    NINI_BUILTIN_DASHSCOPE_API_KEY=sk-xxx NINI_TRIAL_API_KEY=sk-xxx python scripts/encrypt_builtin_key.py

输出文件 src/nini/_builtin_key.py 应加入 .gitignore，仅用于打包产物。
运行时 model_resolver 优先读取 settings 中的明文配置，
若为空则回退读取本文件中的加密 blob 并解密。
"""

import os
import sys
from pathlib import Path

from nini.builtin_key_crypto import decrypt_key, encrypt_key


def _encrypt_env_value(env_name: str) -> str | None:
    """读取并加密指定环境变量。"""
    plain = os.environ.get(env_name, "").strip()
    if not plain:
        return None

    encrypted = encrypt_key(plain)
    decrypted = decrypt_key(encrypted)
    if decrypted != plain:
        print(f"错误：{env_name} 加密验证失败，请检查脚本逻辑", file=sys.stderr)
        sys.exit(1)
    return encrypted


def main() -> None:
    builtin_key = _encrypt_env_value("NINI_BUILTIN_DASHSCOPE_API_KEY")
    trial_key = _encrypt_env_value("NINI_TRIAL_API_KEY")

    if not builtin_key and not trial_key:
        print(
            "错误：环境变量 NINI_BUILTIN_DASHSCOPE_API_KEY / NINI_TRIAL_API_KEY 至少设置一个",
            file=sys.stderr,
        )
        sys.exit(1)

    out_path = Path(__file__).resolve().parent.parent / "src" / "nini" / "_builtin_key.py"
    out_path.write_text(
        f'''"""构建时生成的加密内置 Key（仅打包产物包含，不提交 git）。

此文件由 scripts/encrypt_builtin_key.py 自动生成。
"""

# 加密后的内置 API Key（运行时由 model_resolver 解密）
ENCRYPTED_BUILTIN_KEY: str = {builtin_key!r}

# 加密后的试用 API Key（运行时由 model_resolver 解密）
ENCRYPTED_TRIAL_KEY: str = {trial_key!r}
''',
        encoding="utf-8",
    )

    print(f"已写入: {out_path}")
    if builtin_key:
        print(f"NINI_BUILTIN_DASHSCOPE_API_KEY 已写入（前 20 字符）: {builtin_key[:20]}...")
    if trial_key:
        print(f"NINI_TRIAL_API_KEY 已写入（前 20 字符）: {trial_key[:20]}...")
    print("验证通过：解密结果与原始 Key 一致")


if __name__ == "__main__":
    main()
