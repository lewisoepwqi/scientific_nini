"""API Key 加密/解密工具。

使用 Fernet 对称加密，密钥自动生成并存储在 data 目录下。
"""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from nini.config import settings

logger = logging.getLogger(__name__)

# 密钥文件名
_KEY_FILENAME = ".nini_secret.key"


def _key_path() -> Path:
    """获取密钥文件路径。"""
    return settings.data_dir / _KEY_FILENAME


def _ensure_key() -> bytes:
    """确保密钥文件存在，不存在则自动生成。"""
    path = _key_path()
    if path.exists():
        return path.read_bytes().strip()

    # 自动生成新密钥
    key = Fernet.generate_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    # 限制文件权限（仅所有者可读写）
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows 等平台可能不支持
    logger.info("已生成加密密钥: %s", path)
    return key


def _get_fernet() -> Fernet:
    """获取 Fernet 实例。"""
    key = _ensure_key()
    return Fernet(key)


def encrypt_api_key(plain_key: str) -> str:
    """加密 API Key。

    Args:
        plain_key: 明文 API Key

    Returns:
        Base64 编码的加密字符串
    """
    if not plain_key:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str) -> str:
    """解密 API Key。

    Args:
        encrypted_key: 加密后的 API Key

    Returns:
        明文 API Key；解密失败返回空字符串
    """
    if not encrypted_key:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.warning("API Key 解密失败: %s", e)
        return ""


def mask_api_key(key: str) -> str:
    """脱敏显示 API Key。

    Args:
        key: 明文或部分 API Key

    Returns:
        脱敏后的字符串，如 ``sk-****1234``
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]

