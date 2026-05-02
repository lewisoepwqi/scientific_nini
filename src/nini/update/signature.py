"""Windows Authenticode 签名校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignatureVerificationResult:
    """安装包签名校验结果。"""

    trusted: bool
    status: str
    thumbprint: str = ""
    subject: str = ""
    message: str = ""


class SignatureVerificationError(RuntimeError):
    """安装包签名不可信。"""


def _split_csv(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def verify_authenticode_signature(
    path: Path,
    *,
    allowed_thumbprints: str = "",
    allowed_publishers: str = "",
    enabled: bool = True,
) -> SignatureVerificationResult:
    """校验 Windows 安装包 Authenticode 签名。

    安全策略：
    - 生产环境（打包构建）强制启用签名校验，忽略 enabled 参数
    - 开发环境（源码运行）允许通过 enabled=False 禁用签名校验
    """
    # 生产环境强制启用签名校验，防止通过配置绕过安全检查
    from nini.config import IS_FROZEN

    if IS_FROZEN and not enabled:
        logger.warning("生产环境强制启用签名校验，忽略 enabled=False 配置")
        enabled = True

    if not enabled:
        return SignatureVerificationResult(
            trusted=True, status="disabled", message="签名校验已禁用"
        )
    if sys.platform != "win32":
        return SignatureVerificationResult(
            trusted=True,
            status="skipped",
            message="非 Windows 环境跳过 Authenticode 校验",
        )
    if not path.exists():
        raise SignatureVerificationError("安装包不存在，无法校验签名")

    script = (
        "$sig = Get-AuthenticodeSignature -LiteralPath $args[0];"
        "$cert = $sig.SignerCertificate;"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;"
        "@{Status=$sig.Status.ToString();"
        "Thumbprint=if($cert){$cert.Thumbprint}else{''};"
        "Subject=if($cert){$cert.Subject}else{''};"
        "StatusMessage=$sig.StatusMessage} | ConvertTo-Json -Compress"
    )
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if proc.returncode != 0:
        error_msg = (proc.stderr or "").strip() or "签名校验命令执行失败"
        raise SignatureVerificationError(error_msg)

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SignatureVerificationError("签名校验输出无法解析") from exc

    status = str(payload.get("Status") or "")
    thumbprint = str(payload.get("Thumbprint") or "").lower()
    subject = str(payload.get("Subject") or "")
    message = str(payload.get("StatusMessage") or "")
    if status != "Valid":
        raise SignatureVerificationError(message or f"安装包签名状态无效: {status}")

    allowed_fingerprints = _split_csv(allowed_thumbprints)
    if allowed_fingerprints and thumbprint not in allowed_fingerprints:
        raise SignatureVerificationError("安装包签名证书指纹不在允许列表中")

    allowed_subjects = _split_csv(allowed_publishers)
    if allowed_subjects and not any(item in subject.lower() for item in allowed_subjects):
        raise SignatureVerificationError("安装包签名发布者不在允许列表中")

    return SignatureVerificationResult(
        trusted=True,
        status=status,
        thumbprint=thumbprint,
        subject=subject,
        message=message,
    )
