from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_MODEL_OPTIONS = (
    "llama3.2:3b",
    "llama3.2:1b",
    "llama3.1",
    "mistral",
    "qwen2.5",
    "gemma2",
)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "120"))

    def set_model(self, model: str) -> None:
        model = model.strip()
        if not model:
            raise ValueError("Model name is required.")
        self.model = model

    async def pull_model(self, model: str) -> bool:
        model = model.strip()
        if not model:
            raise ValueError("Model name is required.")

        timeout = httpx.Timeout(float(os.getenv("OLLAMA_PULL_TIMEOUT", "600")), connect=5)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model, "stream": False},
                )
                response.raise_for_status()
        except httpx.HTTPError:
            return False

        self.model = model
        return True

    async def model_status(self) -> dict[str, Any]:
        installed = await self._installed_models()
        configured = self._configured_model_options()
        installed_models = installed or {}
        names = sorted(
            {*configured, *installed_models.keys()},
            key=lambda name: (name not in installed_models, name),
        )
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

    async def generate(self, prompt: str) -> str:
        model = await self._generation_model()
        payload = {"model": model, "prompt": prompt, "stream": False, "format": "json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise OllamaError(f"Ollama generation timed out for model '{model}' after {self.timeout:g}s.") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:240].strip()
            message = f"Ollama generation failed for model '{model}' with HTTP {exc.response.status_code}."
            if detail:
                message = f"{message} {detail}"
            raise OllamaError(message) from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama generation failed for model '{model}': {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise OllamaError("Ollama returned a non-JSON response.") from exc

        text = body.get("response")
        if not isinstance(text, str):
            raise OllamaError("Ollama response did not include text.")

        return text.strip().strip('"')

    async def _generation_model(self) -> str:
        installed = await self._installed_models()
        if installed is None:
            raise OllamaError(f"Ollama is not reachable at {self.base_url}.")
        if not installed:
            raise OllamaError("No Ollama models are installed.")
        if self.model in installed:
            return self.model

        configured = self._configured_model_options()
        for model in configured:
            if model in installed:
                self.model = model
                return model

        self.model = sorted(installed)[0]
        return self.model

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
