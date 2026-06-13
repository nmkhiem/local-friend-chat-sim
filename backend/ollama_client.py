from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_MODEL_OPTIONS = (
    "llama3.2:1b",
    "llama3.2:3b",
    "llama3.1",
    "mistral",
    "qwen2.5",
    "gemma2",
)


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "8"))

    def set_model(self, model: str) -> None:
        model = model.strip()
        if not model:
            raise ValueError("Model name is required.")
        self.model = model

    async def model_status(self) -> dict[str, Any]:
        installed = await self._installed_models()
        configured = self._configured_model_options()
        installed_models = installed or {}
        names = sorted({*configured, *installed_models.keys()})
        models = [
            {
                "name": name,
                "installed": name in installed_models,
                "size": installed_models.get(name, {}).get("size"),
                "modified_at": installed_models.get(name, {}).get("modified_at"),
            }
            for name in names
        ]
        return {
            "base_url": self.base_url,
            "current_model": self.model,
            "connected": installed is not None,
            "models": models,
        }

    async def generate(self, prompt: str) -> str | None:
        payload = {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        try:
            body = response.json()
        except ValueError:
            return None

        text = body.get("response")
        if not isinstance(text, str):
            return None

        return text.strip().strip('"')

    async def _installed_models(self) -> dict[str, dict[str, Any]] | None:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        models = body.get("models")
        if not isinstance(models, list):
            return {}

        installed: dict[str, dict[str, Any]] = {}
        for model in models:
            if not isinstance(model, dict):
                continue
            name = model.get("name") or model.get("model")
            if isinstance(name, str):
                installed[name] = model
        return installed

    def _configured_model_options(self) -> list[str]:
        raw_options = os.getenv("OLLAMA_MODEL_OPTIONS")
        if raw_options:
            options = [option.strip() for option in raw_options.split(",") if option.strip()]
        else:
            options = list(DEFAULT_MODEL_OPTIONS)
        if self.model not in options:
            options.append(self.model)
        return options
