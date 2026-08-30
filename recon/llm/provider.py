from __future__ import annotations

import abc
import asyncio
import json
import os
from typing import Any

from recon.common.config import settings
from recon.common.exceptions import LLMProviderError
from recon.common.logging import logger


class LLMProvider(abc.ABC):
    """Abstract interface for LLM completions."""

    @abc.abstractmethod
    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        """Sends prompt to the model and returns the string response."""
        pass


async def _post_with_retry(
    client: Any,
    url: str,
    headers: dict[str, str],
    json_data: dict[str, Any],
    max_retries: int = 3,
) -> Any:
    """Sends HTTP POST request with automatic exponential retry backoff on 429 Too Many Requests."""
    delay = 2.0
    for attempt in range(max_retries + 1):
        resp = await client.post(url, headers=headers, json=json_data)
        if resp.status_code == 429 and attempt < max_retries:
            logger.warning(
                f"Rate limit (429) received from LLM API. Backing off for {delay:.1f}s (attempt {attempt + 1}/{max_retries})..."
            )
            await asyncio.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp
    return resp


class MockProvider(LLMProvider):
    """Deterministic offline LLM simulation provider. Useful for offline runs, CI, and testing."""

    def __init__(self, mock_responses: list[str] | None = None):
        self.mock_responses = list(mock_responses) if mock_responses else []

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if self.mock_responses:
            return self.mock_responses.pop(0)

        prompt_lower = prompt.lower()

        # Check if this is a test generation request
        if "propose additional" in prompt_lower or "generate exploratory test cases" in prompt_lower:
            return json.dumps({
                "test_cases": [
                    {
                        "name": "AI Edge Case: Max Length & Unicode Input",
                        "category": "BOUNDARY",
                        "method": "POST",
                        "target": "/api/users",
                        "body": {
                            "name": "Tëst Üsér " * 20,
                            "email": "unicode.test+tag@sub.domain.co.uk",
                            "password": "P@ssword1234567890!@#$%^&*()",
                        },
                        "expected_status": [200, 201, 400, 422],
                    },
                    {
                        "name": "AI Edge Case: Unexpected Additional Fields",
                        "category": "NEGATIVE",
                        "method": "POST",
                        "target": "/api/orders",
                        "body": {
                            "item_id": "ITEM-100",
                            "quantity": 1,
                            "currency": "USD",
                            "__proto__": {"admin": True},
                            "unexpected_injected_field": "test",
                        },
                        "expected_status": [200, 201, 400, 422],
                    },
                ]
            })

        # Failure Analysis request
        if "currency" in prompt_lower:
            return json.dumps({
                "observed_facts": [
                    "HTTP POST /api/orders returned status 500 Internal Server Error",
                    "Server response contains NullReferenceException / NullPointerException",
                    "The failure occurs specifically when the 'currency' property is omitted from payload",
                ],
                "hypotheses": [
                    {
                        "hypothesis": "The server's order processing service attempts to read payment.currency without checking for null.",
                        "confidence": 0.92,
                        "explanation": "Stack trace and omission of 'currency' field in request directly correlate with the NullPointerException.",
                    }
                ],
                "suggested_fix": "Add mandatory input validation for 'currency' in the Order model before delegating to payment service.",
                "confidence_score": 0.92,
            })

        if "login" in prompt_lower or "typeerror" in prompt_lower:
            return json.dumps({
                "observed_facts": [
                    "Browser login button clicked",
                    "Navigation to /dashboard did not occur",
                    "Browser console recorded: Uncaught TypeError: Cannot read properties of undefined",
                ],
                "hypotheses": [
                    {
                        "hypothesis": "The click handler in app.js attempts to access user session properties before asynchronous authentication completes.",
                        "confidence": 0.89,
                        "explanation": "Console logs confirm an undefined variable access inside login submit handler.",
                    }
                ],
                "suggested_fix": "Add null check or await the authentication promise before accessing user profile attributes.",
                "confidence_score": 0.89,
            })

        # Generic analysis response
        return json.dumps({
            "observed_facts": [
                "Test execution detected a status or assertion mismatch",
                "Endpoint response did not conform to the expected specification",
            ],
            "hypotheses": [
                {
                    "hypothesis": "Application returned an unhandled error or rejected input unexpectedly.",
                    "confidence": 0.78,
                    "explanation": "Observed output deviates from documented specification.",
                }
            ],
            "suggested_fix": "Inspect backend route logic and ensure schema constraints are properly handled.",
            "confidence_score": 0.78,
        })


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY is not set.")

        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": settings.llm_temperature,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await _post_with_retry(client, url, headers=headers, json_data=payload)
                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return parts[0].get("text", "") if parts else ""
            except Exception as e:
                raise LLMProviderError(f"Gemini API request failed: {e}") from e


class OpenAIProvider(LLMProvider):
    """OpenAI provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or settings.openai_api_key
        self.model = model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("OPENAI_API_KEY is not set.")

        import httpx
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await _post_with_retry(client, "https://api.openai.com/v1/chat/completions", headers=headers, json_data=payload)
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except Exception as e:
                raise LLMProviderError(f"OpenAI API request failed: {e}") from e


class MistralProvider(LLMProvider):
    """Mistral AI provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.mistral_api_key
        self.model = model or settings.mistral_model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("MISTRAL_API_KEY is not set.")

        import httpx
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await _post_with_retry(client, "https://api.mistral.ai/v1/chat/completions", headers=headers, json_data=payload)
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except Exception as e:
                raise LLMProviderError(f"Mistral API request failed: {e}") from e


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("ANTHROPIC_API_KEY is not set.")

        import httpx
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.llm_temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await _post_with_retry(client, "https://api.anthropic.com/v1/messages", headers=headers, json_data=payload)
                data = resp.json()
                content = data.get("content", [])
                return content[0].get("text", "") if content else ""
            except Exception as e:
                raise LLMProviderError(f"Anthropic API request failed: {e}") from e


class OpenAICompatibleProvider(LLMProvider):
    """Universal provider for any OpenAI-compatible API (Ollama, Groq, DeepSeek, OpenRouter, Together, vLLM)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key or os.getenv("RECON_LLM_API_KEY") or "none"
        self.base_url = (base_url or settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model or settings.custom_model or settings.openai_model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        import httpx
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.llm_temperature,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await _post_with_retry(client, endpoint, headers=headers, json_data=payload)
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except Exception as e:
                raise LLMProviderError(f"Custom/Compatible LLM API request to {endpoint} failed: {e}") from e


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Factory function for LLM provider."""
    name = (provider_name or settings.llm_provider).lower()
    if name == "gemini":
        return GeminiProvider()
    elif name == "mistral":
        return MistralProvider()
    elif name in ("anthropic", "claude"):
        return AnthropicProvider()
    elif name in ("custom", "compatible", "ollama", "groq", "deepseek", "openrouter", "together"):
        return OpenAICompatibleProvider()
    elif name == "openai":
        return OpenAIProvider()
    return MockProvider()
