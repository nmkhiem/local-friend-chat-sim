from __future__ import annotations

import os
from typing import Any, Literal

from api_client import ApiModelClient
from ollama_client import OllamaClient


ProviderName = Literal["ollama", "openai", "groq"]


class ModelProviderError(RuntimeError):
    pass


class ModelClient:
    def __init__(self) -> None:
        self.ollama = OllamaClient()
        self.api = ApiModelClient(provider_name="OpenAI API")
        self.groq = ApiModelClient(
            provider_name="Groq API",
            env_prefix="GROQ",
            default_base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.1-8b-instant",
            default_model_options=(
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-20b",
                "openai/gpt-oss-120b",
            ),
        )
        self.provider: ProviderName = self._normalize_provider(os.getenv("MODEL_PROVIDER", "ollama"))

    @property
    def model(self) -> str:
        return self._active_client().model

    def set_model(self, model: str | None = None, provider: str | None = None) -> None:
        if provider is not None:
            self.provider = self._normalize_provider(provider)
        if model is not None:
            self._active_client().set_model(model)

    async def pull_model(self, model: str | None) -> bool:
        if not model:
            raise ValueError("Model name is required.")
        self.provider = "ollama"
        return await self.ollama.pull_model(model)

    async def model_status(self) -> dict[str, Any]:
        provider = self.provider
        status = await self._client_for_provider(provider).model_status()
        status["provider"] = provider
        status["providers"] = [
            {"id": "ollama", "name": "Ollama local"},
            {"id": "groq", "name": "Groq API"},
            {"id": "openai", "name": "API key"},
        ]
        return status

    async def generate(self, prompt: str) -> str:
        return await self._active_client().generate(prompt)

    def _active_client(self) -> OllamaClient | ApiModelClient:
        return self._client_for_provider(self.provider)

    def _client_for_provider(self, provider: ProviderName) -> OllamaClient | ApiModelClient:
        if provider == "openai":
            return self.api
        if provider == "groq":
            return self.groq
        return self.ollama

    def _normalize_provider(self, provider: str) -> ProviderName:
        normalized = provider.strip().lower()
        if normalized in {"ollama", "local"}:
            return "ollama"
        if normalized in {"openai", "api", "api-key", "api_key"}:
            return "openai"
        if normalized in {"groq", "groq-api", "groq_api"}:
            return "groq"
        raise ModelProviderError("Provider must be 'ollama', 'groq', or 'openai'.")
