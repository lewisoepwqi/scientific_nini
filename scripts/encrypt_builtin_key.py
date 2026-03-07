"""构建时脚本：加密内置 API Key，写入 src/nini/_builtin_key.py。

用法：
    NINI_BUILTIN_DASHSCOPE_API_KEY=sk-xxx python scripts/encrypt_builtin_key.py

输出文件 src/nini/_builtin_key.py 应加入 .gitignore，仅用于打包产物。
运行时 model_resolver 优先读取 settings.builtin_dashscope_api_key（.env），
若为空则回退读取本文件中的加密 blob 并解密。
"""

import base64
import os
import struct
import sys
from pathlib import Path

# 固定密钥派生材料（混淆用，非真正安全密钥）
_SALT = b"nini-builtin-v1\x00"
_XOR_KEY = b"Sc13nc3N1n1K3y!!"  # 16 字节 XOR 掩码


def _derive_mask(length: int) -> bytes:
    """从固定盐值循环派生掩码（简单 XOR 混淆）。"""
    cycle = (_XOR_KEY * ((length // len(_XOR_KEY)) + 1))[:length]
    return cycle


def encrypt_key(plain: str) -> str:
    """加密明文 API Key，返回 Base64 编码字符串。"""
    data = plain.encode("utf-8")
    mask = _derive_mask(len(data))
    xored = bytes(a ^ b for a, b in zip(data, mask))
    # 添加长度前缀和盐后缀，增加识别难度
    payload = struct.pack(">H", len(data)) + _SALT[:4] + xored
    return base64.b64encode(payload).decode("ascii")


def decrypt_key(encrypted: str) -> str:
    """解密加密后的 API Key。"""
    try:
        payload = base64.b64decode(encrypted.encode("ascii"))
        if len(payload) < 6:
            return ""
        length = struct.unpack(">H", payload[:2])[0]
        # 跳过盐前缀
        xored = payload[6 : 6 + length]
        if len(xored) != length:
            return ""
        mask = _derive_mask(length)
        return bytes(a ^ b for a, b in zip(xored, mask)).decode("utf-8")
    except Exception:
        return ""


def main() -> None:
    plain_key = os.environ.get("NINI_BUILTIN_DASHSCOPE_API_KEY", "").strip()
    if not plain_key:
        print("错误：环境变量 NINI_BUILTIN_DASHSCOPE_API_KEY 未设置", file=sys.stderr)
        sys.exit(1)

    encrypted = encrypt_key(plain_key)

    # 验证加解密正确性
    decrypted = decrypt_key(encrypted)
    if decrypted != plain_key:
        print("错误：加密验证失败，请检查脚本逻辑", file=sys.stderr)
        sys.exit(1)

    out_path = Path(__file__).resolve().parent.parent / "src" / "nini" / "_builtin_key.py"
    out_path.write_text(
        f'''"""构建时生成的加密内置 Key（仅打包产物包含，不提交 git）。

此文件由 scripts/encrypt_builtin_key.py 自动生成。
"""

# 加密后的内置 API Key（运行时由 model_resolver 解密）
ENCRYPTED_BUILTIN_KEY: str = "{encrypted}"
''',
        encoding="utf-8",
    )

    print(f"已写入: {out_path}")
    print(f"加密结果（前 20 字符）: {encrypted[:20]}...")
    print("验证通过：解密结果与原始 Key 一致")


if __name__ == "__main__":
    main()
