"""内置 API Key 的轻量混淆编码工具。"""

from __future__ import annotations

import base64
import struct

# 固定密钥派生材料（混淆用，非真正安全密钥）
_SALT = b"nini-builtin-v1\x00"
_XOR_KEY = b"Sc13nc3N1n1K3y!!"  # 16 字节 XOR 掩码


def _derive_mask(length: int) -> bytes:
    """从固定盐值循环派生掩码（简单 XOR 混淆）。"""
    return (_XOR_KEY * ((length // len(_XOR_KEY)) + 1))[:length]


def encrypt_key(plain: str) -> str:
    """加密明文 API Key，返回 Base64 编码字符串。"""
    data = plain.encode("utf-8")
    mask = _derive_mask(len(data))
    xored = bytes(a ^ b for a, b in zip(data, mask))
    payload = struct.pack(">H", len(data)) + _SALT[:4] + xored
    return base64.b64encode(payload).decode("ascii")


def decrypt_key(encrypted: str) -> str:
    """解密加密后的 API Key。"""
    try:
        payload = base64.b64decode(encrypted.encode("ascii"))
        if len(payload) < 6:
            return ""
        length = struct.unpack(">H", payload[:2])[0]
        xored = payload[6 : 6 + length]
        if len(xored) != length:
            return ""
        mask = _derive_mask(length)
        return bytes(a ^ b for a, b in zip(xored, mask)).decode("utf-8")
    except Exception:
        return ""
