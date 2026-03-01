"""Ollama Provider.

Ollama OpenAI-compatible API adapter for local models.
"""

from __future__ import annotations

from nini.config import settings

from .openai_provider import OpenAICompatibleClient


class OllamaClient(OpenAICompatibleClient):
    """Ollama OpenAI 兼容接口适配器。"""

    provider_id = "ollama"
    provider_name = "Ollama（本地）"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        resolved_base = (base_url or settings.ollama_base_url or "").rstrip("/")
        openai_compat_base = f"{resolved_base}/v1" if resolved_base else None
        super().__init__(
            api_key="ollama",
            base_url=openai_compat_base,
            model=model or settings.ollama_model,
        )

    def is_available(self) -> bool:
        return bool(self._base_url and self._model)

    def _supports_stream_usage(self) -> bool:
        # Ollama OpenAI 兼容端通常不返回 usage
        return False
