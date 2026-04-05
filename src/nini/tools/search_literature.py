"""文献检索工具。

通过 Semantic Scholar 与 CrossRef 两级降级链检索学术文献。
联网不可用或所有 API 均失败时，返回明确的手动替代建议。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from nini.agent.session import Session
from nini.plugins.base import DegradationInfo
from nini.plugins.network import NetworkPlugin
from nini.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

try:
    import httpx as httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

_SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_CROSSREF_SEARCH_URL = "https://api.crossref.org/works"
_SEMANTIC_SCHOLAR_FIELDS = "title,authors,year,abstract,citationCount,externalIds"
_DEFAULT_MAX_RESULTS = 20
_MAX_RESULTS_LIMIT = 50
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_JATS_TAG_RE = re.compile(r"<[^>]+>")


class SearchLiteratureTool(Tool):
    """检索学术文献的工具。"""

    def __init__(self, plugin_registry: Any | None = None) -> None:
        self._plugin_registry = plugin_registry
        self._rate_limit_lock = asyncio.Lock()
        self._last_semantic_scholar_request_at = 0.0

    @property
    def name(self) -> str:
        return "search_literature"

    @property
    def description(self) -> str:
        return (
            "检索学术文献，优先使用 Semantic Scholar，失败时自动降级到 CrossRef。"
            "支持按关键词、年份和排序方式筛选，返回标题、作者、年份、摘要、DOI 与引用次数。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "文献检索关键词，例如 'machine learning drug discovery'",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"返回结果上限，默认 {_DEFAULT_MAX_RESULTS}，最大 {_MAX_RESULTS_LIMIT}",
                    "default": _DEFAULT_MAX_RESULTS,
                    "minimum": 1,
                    "maximum": _MAX_RESULTS_LIMIT,
                },
                "year_from": {
                    "type": "integer",
                    "description": "可选的起始年份，仅返回该年份及之后的文献",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "date"],
                    "default": "relevance",
                    "description": "排序方式：relevance 为相关性，date 为年份倒序",
                },
            },
            "required": ["query"],
        }

    @property
    def category(self) -> str:
        return "utility"

    @property
    def research_domain(self) -> str:
        return "general"

    @property
    def typical_use_cases(self) -> list[str]:
        return [
            "为课题快速收集候选文献",
            "按年份缩小近年研究范围",
            "在离线时提示用户切换为手动文献提供模式",
        ]

    @property
    def output_types(self) -> list[str]:
        return ["json"]

    async def execute(self, session: Session, **kwargs: Any) -> ToolResult:
        del session  # 当前工具不依赖会话内容

        query = str(kwargs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, message="query 不能为空")

        try:
            max_results = self._normalize_max_results(kwargs.get("max_results"))
            year_from = self._normalize_year(kwargs.get("year_from"))
            sort_by = self._normalize_sort_by(kwargs.get("sort_by"))
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc))

        network_plugin = self._resolve_network_plugin()
        is_available = await self._check_network_available(network_plugin)
        if not is_available:
            return self._build_offline_result(network_plugin)

        try:
            client, owns_client = self._get_http_client(network_plugin)
        except RuntimeError as exc:
            return ToolResult(success=False, message=str(exc))

        semantic_error: str | None = None
        crossref_error: str | None = None
        try:
            try:
                papers = await self._search_semantic_scholar(
                    client=client,
                    query=query,
                    max_results=max_results,
                    year_from=year_from,
                    sort_by=sort_by,
                )
                if papers:
                    return self._build_success_result(
                        query=query,
                        source="semantic_scholar",
                        papers=papers,
                    )
                semantic_error = "Semantic Scholar 未返回结果"
            except Exception as exc:  # pragma: no cover - 由单测覆盖主要分支
                semantic_error = str(exc)
                logger.warning("Semantic Scholar 检索失败: query=%s error=%s", query, exc)

            try:
                papers = await self._search_crossref(
                    client=client,
                    query=query,
                    max_results=max_results,
                    year_from=year_from,
                    sort_by=sort_by,
                )
                if papers:
                    return self._build_success_result(
                        query=query,
                        source="crossref",
                        papers=papers,
                        fallback_from="semantic_scholar",
                        warnings=[semantic_error] if semantic_error else [],
                    )
                crossref_error = "CrossRef 未返回结果"
            except Exception as exc:  # pragma: no cover - 由单测覆盖主要分支
                crossref_error = str(exc)
                logger.warning("CrossRef 检索失败: query=%s error=%s", query, exc)

            return self._build_api_degraded_result(
                semantic_error=semantic_error,
                crossref_error=crossref_error,
            )
        finally:
            if owns_client:
                await client.aclose()

    def _normalize_max_results(self, raw_value: Any) -> int:
        if raw_value in (None, ""):
            return _DEFAULT_MAX_RESULTS
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_results 必须是整数") from exc
        if value < 1 or value > _MAX_RESULTS_LIMIT:
            raise ValueError(f"max_results 必须在 1 到 {_MAX_RESULTS_LIMIT} 之间")
        return value

    def _normalize_year(self, raw_value: Any) -> int | None:
        if raw_value in (None, ""):
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("year_from 必须是整数年份") from exc
        if value < 1900 or value > 2100:
            raise ValueError("year_from 超出合理范围")
        return value

    def _normalize_sort_by(self, raw_value: Any) -> str:
        sort_by = str(raw_value or "relevance").strip().lower()
        if sort_by not in {"relevance", "date"}:
            raise ValueError("sort_by 仅支持 relevance 或 date")
        return sort_by

    def _resolve_network_plugin(self) -> Any | None:
        registry = self._plugin_registry
        if registry is None or not hasattr(registry, "get"):
            return None
        return registry.get("network")

    async def _check_network_available(self, network_plugin: Any | None) -> bool:
        plugin = network_plugin or NetworkPlugin()
        if not hasattr(plugin, "is_available"):
            return False
        try:
            return bool(await plugin.is_available())
        except Exception as exc:  # pragma: no cover - 防御性保护
            logger.warning("NetworkPlugin 可用性检测异常: %s", exc)
            return False

    def _get_http_client(self, network_plugin: Any | None) -> tuple[Any, bool]:
        if network_plugin is not None:
            client = getattr(network_plugin, "_client", None)
            if client is not None and hasattr(client, "get"):
                return client, False

        if not _HTTPX_AVAILABLE or httpx is None:
            raise RuntimeError("httpx 未安装，无法执行在线文献检索")

        from nini.config import settings

        proxy = settings.network_proxy
        client_kwargs: dict[str, Any] = {
            "timeout": settings.network_timeout,
            "headers": {
                "User-Agent": "Nini-Scientific-Agent/0.1 (Literature Search)",
                "Accept": "application/json",
            },
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        client = httpx.AsyncClient(**client_kwargs)
        return client, True

    async def _search_semantic_scholar(
        self,
        *,
        client: Any,
        query: str,
        max_results: int,
        year_from: int | None,
        sort_by: str,
    ) -> list[dict[str, Any]]:
        await self._enforce_semantic_scholar_rate_limit()
        response = await client.get(
            _SEMANTIC_SCHOLAR_SEARCH_URL,
            params={
                "query": query,
                "limit": max_results,
                "fields": _SEMANTIC_SCHOLAR_FIELDS,
            },
        )
        response.raise_for_status()
        payload = response.json()
        raw_items = payload.get("data")
        if not isinstance(raw_items, list):
            raise ValueError("Semantic Scholar 响应格式不正确")

        papers = [self._normalize_semantic_scholar_item(item) for item in raw_items]
        return self._post_process_results(
            papers=papers,
            year_from=year_from,
            sort_by=sort_by,
            max_results=max_results,
        )

    async def _search_crossref(
        self,
        *,
        client: Any,
        query: str,
        max_results: int,
        year_from: int | None,
        sort_by: str,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "query": query,
            "rows": max_results,
            "order": "desc",
            "sort": "published" if sort_by == "date" else "relevance",
        }
        if year_from is not None:
            params["filter"] = f"from-pub-date:{year_from}-01-01"

        response = await client.get(_CROSSREF_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("CrossRef 响应格式不正确")
        raw_items = message.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("CrossRef 响应缺少 items 列表")

        papers = [self._normalize_crossref_item(item) for item in raw_items]
        return self._post_process_results(
            papers=papers,
            year_from=year_from,
            sort_by=sort_by,
            max_results=max_results,
        )

    async def _enforce_semantic_scholar_rate_limit(self) -> None:
        async with self._rate_limit_lock:
            now = self._monotonic()
            elapsed = now - self._last_semantic_scholar_request_at
            if elapsed < _MIN_REQUEST_INTERVAL_SECONDS:
                await self._sleep(_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
                now = self._monotonic()
            self._last_semantic_scholar_request_at = now

    def _monotonic(self) -> float:
        return time.monotonic()

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def _normalize_semantic_scholar_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return self._empty_paper(source="semantic_scholar")

        authors = []
        raw_authors = item.get("authors")
        if isinstance(raw_authors, list):
            for author in raw_authors:
                if not isinstance(author, dict):
                    continue
                name = str(author.get("name") or "").strip()
                if name:
                    authors.append(name)

        external_ids = item.get("externalIds")
        doi = None
        if isinstance(external_ids, dict):
            doi_value = external_ids.get("DOI")
            if doi_value is not None:
                doi = str(doi_value).strip() or None

        citation_count = item.get("citationCount")
        return {
            "title": str(item.get("title") or "").strip(),
            "authors": authors,
            "year": self._coerce_int(item.get("year")),
            "abstract": str(item.get("abstract") or "").strip() or None,
            "doi": doi,
            "citation_count": self._coerce_int(citation_count),
            "source": "semantic_scholar",
        }

    def _normalize_crossref_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return self._empty_paper(source="crossref")

        authors = []
        raw_authors = item.get("author")
        if isinstance(raw_authors, list):
            for author in raw_authors:
                if not isinstance(author, dict):
                    continue
                given = str(author.get("given") or "").strip()
                family = str(author.get("family") or "").strip()
                name = " ".join(part for part in (given, family) if part).strip()
                if name:
                    authors.append(name)

        titles = item.get("title")
        title = ""
        if isinstance(titles, list) and titles:
            title = str(titles[0] or "").strip()

        doi_value = str(item.get("DOI") or "").strip()
        return {
            "title": title,
            "authors": authors,
            "year": self._extract_crossref_year(item),
            "abstract": self._clean_crossref_abstract(item.get("abstract")),
            "doi": doi_value or None,
            "citation_count": self._coerce_int(item.get("is-referenced-by-count")),
            "source": "crossref",
        }

    def _post_process_results(
        self,
        *,
        papers: list[dict[str, Any]],
        year_from: int | None,
        sort_by: str,
        max_results: int,
    ) -> list[dict[str, Any]]:
        filtered = [paper for paper in papers if paper.get("title")]
        if year_from is not None:
            filtered = [
                paper
                for paper in filtered
                if (paper.get("year") is None or int(paper["year"]) >= year_from)
            ]
        if sort_by == "date":
            filtered.sort(
                key=lambda item: (item.get("year") or 0, item.get("title") or ""), reverse=True
            )
        return filtered[:max_results]

    def _build_success_result(
        self,
        *,
        query: str,
        source: str,
        papers: list[dict[str, Any]],
        fallback_from: str | None = None,
        warnings: list[str] | None = None,
    ) -> ToolResult:
        metadata: dict[str, Any] = {
            "source": source,
            "offline_mode": False,
            "manual_mode": False,
        }
        if fallback_from:
            metadata["fallback_from"] = fallback_from
        if warnings:
            metadata["warnings"] = [warning for warning in warnings if warning]

        label = "Semantic Scholar" if source == "semantic_scholar" else "CrossRef"
        return ToolResult(
            success=True,
            message=f"已从 {label} 检索到 {len(papers)} 篇文献",
            data={
                "query": query,
                "source": source,
                "count": len(papers),
                "papers": papers,
            },
            metadata=metadata,
        )

    def _build_offline_result(self, network_plugin: Any | None) -> ToolResult:
        degradation = self._get_degradation_info(network_plugin)
        message = "当前为离线模式，无法在线检索文献。请上传 PDF 或提供引用列表后继续。"
        if degradation is not None and degradation.reason:
            message = f"{message} 原因：{degradation.reason}"
        metadata: dict[str, Any] = {
            "offline_mode": True,
            "manual_mode": True,
            "source": "manual",
        }
        if degradation is not None:
            metadata["degradation"] = degradation.model_dump()
        return ToolResult(
            success=False,
            message=message,
            data={
                "papers": [],
                "source": "manual",
                "manual_mode": True,
                "alternatives": list(degradation.alternatives) if degradation else [],
            },
            metadata=metadata,
        )

    def _build_api_degraded_result(
        self,
        *,
        semantic_error: str | None,
        crossref_error: str | None,
    ) -> ToolResult:
        return ToolResult(
            success=False,
            message=("在线学术检索服务当前不可用。请稍后重试，或改为上传 PDF / 提供引用列表。"),
            retryable=True,
            data={
                "papers": [],
                "source": "manual",
                "manual_mode": True,
                "alternatives": [
                    "上传已下载的论文 PDF",
                    "粘贴已有参考文献列表",
                    "稍后重试在线检索",
                ],
            },
            metadata={
                "offline_mode": False,
                "manual_mode": True,
                "source": "manual",
                "semantic_scholar_error": semantic_error,
                "crossref_error": crossref_error,
            },
        )

    def _get_degradation_info(self, network_plugin: Any | None) -> DegradationInfo | None:
        plugin = network_plugin or NetworkPlugin()
        if hasattr(plugin, "get_degradation_info"):
            info = plugin.get_degradation_info()
            if isinstance(info, DegradationInfo):
                return info
        return None

    def _coerce_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _extract_crossref_year(self, item: dict[str, Any]) -> int | None:
        for field in ("published-print", "published-online", "created", "issued"):
            payload = item.get(field)
            if not isinstance(payload, dict):
                continue
            date_parts = payload.get("date-parts")
            if not isinstance(date_parts, list) or not date_parts:
                continue
            first = date_parts[0]
            if not isinstance(first, list) or not first:
                continue
            return self._coerce_int(first[0])
        return None

    def _clean_crossref_abstract(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = _JATS_TAG_RE.sub(" ", value)
        text = " ".join(text.split()).strip()
        return text or None

    def _empty_paper(self, *, source: str) -> dict[str, Any]:
        return {
            "title": "",
            "authors": [],
            "year": None,
            "abstract": None,
            "doi": None,
            "citation_count": None,
            "source": source,
        }
