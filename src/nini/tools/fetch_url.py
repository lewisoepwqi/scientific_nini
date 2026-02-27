"""网页抓取工具：将 URL 内容转换为 Markdown 文本。

用于科研场景中抓取在线文档、论文摘要、统计方法参考等。
自动识别 JSON/HTML 响应，HTML 转 Markdown 输出。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from nini.agent.session import Session
from nini.config import settings
from nini.tools.base import Skill, SkillResult

logger = logging.getLogger(__name__)

# 请求超时（秒）
_TIMEOUT = 15
# 响应文本最大字符数
_MAX_CHARS = 5000
# URL 最大长度
_MAX_URL_LENGTH = 2048
# 允许的 URL scheme
_ALLOWED_SCHEMES = {"http", "https", "file"}
# 禁止访问的域名（安全考虑）
_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}
# 本地文件最大大小（字节）
_MAX_LOCAL_FILE_BYTES = 2 * 1024 * 1024
# file:// 允许读取的文本后缀
_ALLOWED_LOCAL_FILE_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".py",
    ".r",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".tsv",
    ".ini",
    ".cfg",
    ".sql",
    ".jinja",
    ".j2",
}


class FetchURLSkill(Skill):
    """抓取网页内容并转换为 Markdown 文本。"""

    @property
    def name(self) -> str:
        return "fetch_url"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def description(self) -> str:
        return (
            "抓取指定 URL 的网页内容并转换为 Markdown 格式。"
            "适用于查阅在线文档、论文摘要、统计方法参考等。"
            "自动处理 HTML→Markdown 转换，支持 JSON 响应的格式化输出。"
            "同时支持读取白名单技能目录下的 file:// 本地文本文件。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "要抓取的 URL（支持 http/https，"
                        "以及白名单技能目录下的 file:// 本地文本文件）"
                    ),
                },
            },
            "required": ["url"],
        }

    async def execute(self, session: Session, **kwargs: Any) -> SkillResult:
        url = kwargs.get("url", "").strip()
        if not url:
            return SkillResult(success=False, message="URL 不能为空")

        # 验证 URL 安全性
        error = self._validate_url(url)
        if error:
            return SkillResult(success=False, message=error)

        try:
            content = await self._fetch(url)
            return SkillResult(
                success=True,
                message=f"已成功抓取 {url}",
                data={"url": url, "content": content, "length": len(content)},
            )
        except Exception as e:
            logger.warning("网页抓取失败: url=%s error=%s", url, e)
            return SkillResult(success=False, message=f"抓取失败: {e}")

    @staticmethod
    def _validate_url(url: str) -> str | None:
        """验证 URL 安全性，返回错误信息或 None。"""
        if len(url) > _MAX_URL_LENGTH:
            return f"URL 长度超过限制（最大 {_MAX_URL_LENGTH} 字符）"

        try:
            parsed = urlparse(url)
        except Exception:
            return "无效的 URL 格式"

        scheme = parsed.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            return f"不支持的协议: {parsed.scheme}，仅支持 http/https/file"

        if scheme == "file":
            return FetchURLSkill._validate_local_file_url(parsed)

        host = (parsed.hostname or "").lower()
        if not host:
            return "URL 缺少域名"

        if host in _BLOCKED_HOSTS:
            return f"禁止访问内部地址: {host}"

        # 使用 ipaddress 模块精确检测私有/本地 IP
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return f"禁止访问私有/本地 IP 地址: {host}"
        except ValueError:
            # 不是 IP 地址，是域名 → 做 DNS 解析验证
            try:
                addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC)
                for _, _, _, _, sockaddr in addr_info:
                    resolved_ip = ipaddress.ip_address(sockaddr[0])
                    if (
                        resolved_ip.is_private
                        or resolved_ip.is_loopback
                        or resolved_ip.is_link_local
                        or resolved_ip.is_reserved
                    ):
                        return f"域名 {host} 解析到私有地址 {resolved_ip}，禁止访问"
            except (socket.gaierror, OSError):
                return f"域名 {host} 无法解析"

        return None

    @staticmethod
    def _resolve_local_file_path(parsed: Any) -> Path:
        """将 file URL 解析为本地绝对路径。"""
        raw_path = unquote(parsed.path or "")
        if raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
            # 兼容 file:///C:/... 形式
            raw_path = raw_path[1:]
        return Path(raw_path).expanduser().resolve()

    @staticmethod
    def _validate_local_file_url(parsed: Any) -> str | None:
        """校验 file:// URL 的安全性（仅允许 skills 目录文本文件）。"""
        host = (parsed.netloc or "").strip().lower()
        if host not in ("", "localhost"):
            return f"不支持的 file 主机: {host}"

        path = FetchURLSkill._resolve_local_file_path(parsed)
        if not path.exists():
            return f"本地文件不存在: {path}"
        if not path.is_file():
            return f"本地路径不是文件: {path}"

        allowed_roots = [root.expanduser().resolve() for root in settings.skills_search_dirs]
        if not any(path.is_relative_to(root) for root in allowed_roots):
            return "禁止访问技能目录之外的本地文件"

        suffix = path.suffix.lower()
        if suffix and suffix not in _ALLOWED_LOCAL_FILE_SUFFIXES:
            return f"不支持读取该文件类型: {suffix}"

        try:
            size = path.stat().st_size
        except OSError:
            return f"无法读取本地文件: {path}"
        if size > _MAX_LOCAL_FILE_BYTES:
            return f"本地文件过大（{size} 字节），最大 {_MAX_LOCAL_FILE_BYTES} 字节"

        return None

    @staticmethod
    async def _fetch(url: str) -> str:
        """抓取 URL 内容并转换为文本。"""
        parsed = urlparse(url)
        if parsed.scheme.lower() == "file":
            path = FetchURLSkill._resolve_local_file_path(parsed)
            data = path.read_bytes()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"本地文件不是 UTF-8 文本: {path}") from exc
            if len(text) > _MAX_CHARS:
                text = text[:_MAX_CHARS] + f"\n\n... (内容已截断，原文共 {len(text)} 字符)"
            return text

        import httpx

        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=False,
            headers={
                "User-Agent": "Nini-Scientific-Agent/0.1 (Research Assistant)",
                "Accept": "text/html,application/json,text/plain,*/*",
            },
        ) as client:
            response = await client.get(url)
            # 处理重定向：验证目标地址安全性
            if response.is_redirect:
                location = response.headers.get("location", "")
                redirect_err = FetchURLSkill._validate_url(location)
                if redirect_err:
                    raise ValueError(f"重定向目标不安全: {redirect_err}")
                response = await client.get(location)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # JSON 响应直接格式化
            if "json" in content_type:
                import json

                try:
                    data = response.json()
                    text = json.dumps(data, ensure_ascii=False, indent=2)
                except Exception:
                    text = response.text
            # HTML 响应转 Markdown
            elif "html" in content_type:
                text = _html_to_markdown(response.text)
            # 其他文本类型直接返回
            else:
                text = response.text

            # 截断
            if len(text) > _MAX_CHARS:
                text = text[:_MAX_CHARS] + f"\n\n... (内容已截断，原文共 {len(response.text)} 字符)"

            return text


def _html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown 文本。"""
    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.ignore_emphasis = False
        converter.body_width = 0  # 不自动换行
        converter.skip_internal_links = True
        converter.ignore_tables = False
        return converter.handle(html).strip()
    except ImportError:
        # html2text 未安装时的简单回退
        import re

        # 移除 script 和 style
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # 移除标签
        text = re.sub(r"<[^>]+>", " ", text)
        # 合并空白
        text = re.sub(r"\s+", " ", text).strip()
        return text
