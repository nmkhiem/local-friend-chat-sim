from __future__ import annotations

import os
from typing import Any

import httpx


class ApiModelError(RuntimeError):
    pass


class ApiModelClient:
    def __init__(
        self,
        *,
        provider_name: str = "API",
        env_prefix: str = "OPENAI",
        default_base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
    ) -> None:
        self.provider_name = provider_name
        self.env_prefix = env_prefix
        self.base_url = os.getenv(f"{env_prefix}_BASE_URL", default_base_url).rstrip("/")
        self.api_key = os.getenv(f"{env_prefix}_API_KEY", "")
        self.model = os.getenv(f"{env_prefix}_MODEL", default_model)
        self.timeout = float(os.getenv(f"{env_prefix}_TIMEOUT", "60"))

    def set_model(self, model: str) -> None:
        model = model.strip()
        if not model:
            raise ValueError("Model name is required.")
        self.model = model

    async def model_status(self) -> dict[str, Any]:
        configured = bool(self.api_key.strip())
        return {
            "base_url": self.base_url,
            "current_model": self.model,
            "connected": configured,
            "api_key_configured": configured,
            "models": [
                {
                    "name": self.model,
                    "installed": configured,
                    "size": None,
                    "modified_at": None,
                }
            ],
        }

    async def generate(self, prompt: str) -> str:
        if not self.api_key.strip():
            raise ApiModelError(f"{self.env_prefix}_API_KEY is not set.")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ApiModelError(
                f"{self.provider_name} generation timed out for model '{self.model}' after {self.timeout:g}s."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:240].strip()
            message = (
                f"{self.provider_name} generation failed for model '{self.model}' "
                f"with HTTP {exc.response.status_code}."
            )
            if detail:
                message = f"{message} {detail}"
            raise ApiModelError(message) from exc
        except httpx.HTTPError as exc:
            raise ApiModelError(f"{self.provider_name} generation failed for model '{self.model}': {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ApiModelError(f"{self.provider_name} returned a non-JSON response.") from exc

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ApiModelError(f"{self.provider_name} response did not include choices.")

        first = choices[0]
        if not isinstance(first, dict):
            raise ApiModelError(f"{self.provider_name} response included an invalid choice.")

        message = first.get("message")
        if not isinstance(message, dict):
            raise ApiModelError(f"{self.provider_name} response did not include a message.")

        content = message.get("content")
        if not isinstance(content, str):
            raise ApiModelError(f"{self.provider_name} response did not include text.")

        return content.strip()
