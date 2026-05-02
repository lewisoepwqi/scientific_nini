"""更新状态持久化。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from pathlib import Path

from nini.update.models import UpdateDownloadState

logger = logging.getLogger(__name__)


class UpdateStateStore:
    """将更新下载状态保存到本地 JSON 文件。

    完整性校验：
    - 使用 HMAC-SHA256 检测状态文件意外损坏
    - 签名密钥基于更新目录路径生成，不构成防定向篡改能力
    - 签名验证失败时返回空状态并记录警告
    """

    def __init__(self, path: Path, *, secret: str | None = None) -> None:
        self.path = path
        self.sig_path = path.with_suffix(path.suffix + ".sig")
        # 路径派生密钥仅用于完整性校验，不能作为防篡改密钥。
        self._secret = (secret or str(path.parent)).encode("utf-8")

    def _compute_hmac(self, data: bytes) -> str:
        """计算 HMAC-SHA256 签名。"""
        return hmac.new(self._secret, data, hashlib.sha256).hexdigest()

    def _verify_hmac(self, data: bytes, expected_sig: str) -> bool:
        """验证 HMAC 签名。"""
        actual_sig = self._compute_hmac(data)
        return hmac.compare_digest(actual_sig, expected_sig)

    def load(self) -> UpdateDownloadState:
        """读取下载状态；损坏、签名不匹配或缺失时返回空状态。"""
        if not self.path.exists():
            return UpdateDownloadState()

        try:
            data = self.path.read_bytes()

            # 验证 HMAC 签名
            if self.sig_path.exists():
                expected_sig = self.sig_path.read_text(encoding="utf-8").strip()
                if not self._verify_hmac(data, expected_sig):
                    logger.error("更新状态文件签名不匹配，已重置: %s", self.path)
                    # 清理 installer_path 指向的孤立文件
                    try:
                        parsed = json.loads(data)
                        installer = parsed.get("installer_path")
                        if installer:
                            installer_path = Path(installer)
                            if installer_path.exists():
                                installer_path.unlink()
                                logger.info("已清理签名不匹配的孤立安装包: %s", installer_path)
                    except Exception:
                        pass
                    return UpdateDownloadState(error="更新状态文件签名不匹配，已重置")
            else:
                logger.debug("更新状态文件签名文件不存在，跳过验证: %s", self.sig_path)

            return UpdateDownloadState.model_validate(json.loads(data))
        except json.JSONDecodeError:
            logger.warning("更新状态文件损坏，已重置: %s", self.path)
            return UpdateDownloadState(error="更新状态文件损坏，已重置")
        except Exception:
            logger.warning("更新状态文件读取异常，已重置: %s", self.path)
            return UpdateDownloadState(error="更新状态文件读取异常，已重置")

    def save(self, state: UpdateDownloadState) -> None:
        """保存下载状态及其 HMAC 签名。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 序列化状态
        data = json.dumps(state.model_dump(), ensure_ascii=False, indent=2).encode("utf-8")

        # 计算签名
        signature = self._compute_hmac(data)

        # 写入临时文件
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_bytes(data)

        # 写入签名文件
        temp_sig_path = self.sig_path.with_suffix(self.sig_path.suffix + ".tmp")
        temp_sig_path.write_text(signature, encoding="utf-8")

        # 原子替换
        temp_path.replace(self.path)
        temp_sig_path.replace(self.sig_path)


def build_state_store(updates_dir: Path) -> UpdateStateStore:
    """根据更新目录创建状态存储。"""
    return UpdateStateStore(updates_dir / "state.json")
