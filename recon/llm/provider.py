from __future__ import annotations

import abc
import asyncio
import json
import os
import re
from typing import Any

from recon.common.config import settings
from recon.common.exceptions import LLMProviderError
from recon.common.logging import logger


def _format_http_error(provider: str, e: Exception) -> str:
    import httpx

    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        try:
            err_json = e.response.json()
            err_msg = (
                err_json.get("error", {}).get("message")
                or err_json.get("message")
                or err_json.get("detail")
            )
            if err_msg:
                return f"{provider} API returned HTTP {code}: {err_msg}"
        except Exception:
            pass
        text = e.response.text.strip()
        return (
            f"{provider} API returned HTTP {code}: {text[:200]}"
            if text
            else f"{provider} API returned HTTP {code}"
        )
    elif isinstance(e, httpx.TimeoutException):
        return f"{provider} request timed out after 30s. Check your network or API endpoint availability."
    elif isinstance(e, httpx.RequestError):
        msg = str(e).strip() or type(e).__name__
        return f"{provider} network error: {msg}"
    return f"{provider} request failed: {str(e).strip() or type(e).__name__}"


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

        # Check if this is a master agent tool planning request
        if "autonomous master qa engineer" in (system_prompt or "").lower() or "select the best tool" in prompt_lower:
            if "browser" in prompt_lower or "navigate" in prompt_lower or "click" in prompt_lower or "cart" in prompt_lower:
                return json.dumps({
                    "tool": "browser",
                    "goal": "Accomplish user browser task",
                })
            elif "fix" in prompt_lower or "patch" in prompt_lower or "bug" in prompt_lower:
                return json.dumps({
                    "tool": "code_fix",
                    "defect_description": "Fix defect identified in prompt",
                })
            elif "scan" in prompt_lower or "discover" in prompt_lower:
                return json.dumps({
                    "tool": "scan",
                })
            elif "api" in prompt_lower or "endpoint" in prompt_lower or "500" in prompt_lower:
                return json.dumps({
                    "tool": "api_probe",
                    "endpoint": "/api/orders",
                    "method": "POST",
                })
            return json.dumps({
                "tool": "reply",
                "message": "I processed your request successfully."
            })

        # Check if this is an autonomous browser agent request
        if "autonomous qa browser agent" in (system_prompt or "").lower() or "what is the next action?" in prompt_lower:
            if "step 1 of" in prompt_lower:
                if "health" in prompt_lower or "sức khỏe" in prompt_lower:
                    return json.dumps({
                        "thought": "Found health section link ('Sức khỏe'). Navigating there.",
                        "action": "click",
                        "selector": "a[href*='suc-khoe']"
                    })
                return json.dumps({
                    "thought": "Navigating to target element on page.",
                    "action": "click",
                    "selector": "a"
                })
            return json.dumps({
                "thought": "Goal successfully accomplished.",
                "action": "finish"
            })

        # Check if this is a test generation request
        if (
            "propose additional" in prompt_lower
            or "generate exploratory test cases" in prompt_lower
        ):
            return json.dumps(
                {
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
                }
            )

        # Code Patching request (Self-Healing / recon fix)
        if (
            "modified_full_content" in (system_prompt or "")
            or "autonomous debugging agent" in (system_prompt or "").lower()
        ):
            match = re.search(r"```(?:\w+)?\n([\s\S]*?)\n```", prompt)
            source_content = match.group(1) if match else ""
            fixed_content = source_content
            explanation = "Provide default fallback for optional order.currency to prevent unhandled 500 error."
            if (
                "if not order.currency:" in source_content
                and "HTTP_500_INTERNAL_SERVER_ERROR" in source_content
            ):
                fixed_content = re.sub(
                    r"if not order\.currency:\s+raise HTTPException\([\s\S]*?\n\s*\)",
                    '# Fix: Gracefully fallback currency to USD if omitted\n    currency = order.currency or "USD"',
                    source_content,
                ).replace(
                    '"currency": order.currency.upper()',
                    '"currency": (order.currency or "USD").upper()',
                )
                explanation = (
                    "Default omitted currency to USD instead of throwing 500 Internal Server Error."
                )
            elif "order.currency.upper()" in source_content:
                fixed_content = source_content.replace(
                    "currency_code = order.currency.upper()",
                    'currency_code = (order.currency or "USD").upper()',
                )
            elif "def " in source_content:
                fixed_content = f"# Autonomous bugfix applied\n{source_content}"
                explanation = "Applied defensive edge case handling."

            return json.dumps(
                {
                    "explanation": explanation,
                    "modified_full_content": fixed_content,
                }
            )

        # Failure Analysis request
        if "currency" in prompt_lower:
            return json.dumps(
                {
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
                }
            )

        if "login" in prompt_lower or "typeerror" in prompt_lower:
            return json.dumps(
                {
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
                }
            )

        # Generic analysis response
        return json.dumps(
            {
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
            }
        )


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model if model is not None else settings.gemini_model

    async def complete(self, prompt: str, system_prompt: str | None = None) -> str:
        if not self.api_key:
            raise LLMProviderError("GEMINI_API_KEY is not set.")

        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        )
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
                raise LLMProviderError(_format_http_error("Gemini", e)) from e


class OpenAIProvider(LLMProvider):
    """OpenAI provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model if model is not None else settings.openai_model

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
                resp = await _post_with_retry(
                    client,
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json_data=payload,
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except Exception as e:
                raise LLMProviderError(_format_http_error("OpenAI", e)) from e


class MistralProvider(LLMProvider):
    """Mistral AI provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.mistral_api_key
        self.model = model if model is not None else settings.mistral_model

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
                resp = await _post_with_retry(
                    client,
                    "https://api.mistral.ai/v1/chat/completions",
                    headers=headers,
                    json_data=payload,
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except Exception as e:
                raise LLMProviderError(_format_http_error("Mistral", e)) from e


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using REST API with httpx."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self.model = model if model is not None else settings.anthropic_model

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
                resp = await _post_with_retry(
                    client,
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json_data=payload,
                )
                data = resp.json()
                content = data.get("content", [])
                return content[0].get("text", "") if content else ""
            except Exception as e:
                raise LLMProviderError(_format_http_error("Anthropic", e)) from e


class OpenAICompatibleProvider(LLMProvider):
    """Universal provider for any OpenAI-compatible API (Ollama, Groq, DeepSeek, OpenRouter, Together, vLLM)."""

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, model: str | None = None
    ):
        self.api_key = (
            api_key or settings.openai_api_key or os.getenv("RECON_LLM_API_KEY") or "none"
        )
        self.base_url = (base_url or settings.llm_base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
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
                raise LLMProviderError(_format_http_error("Compatible/OpenAI", e)) from e


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Factory function for LLM provider."""
    name = (provider_name or settings.llm_provider).lower()
    if name == "gemini":
        return GeminiProvider()
    elif name == "mistral":
        return MistralProvider()
    elif name == "deepseek":
        api_key = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        model = settings.deepseek_model or "deepseek-chat"
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            model=model,
        )
    elif name in ("anthropic", "claude"):
        return AnthropicProvider()
    elif name in ("ollama", "local"):
        base_url = settings.llm_base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1"
        model = settings.custom_model if (settings.custom_model and settings.custom_model != "default") else "qwen3-coder:30b"
        return OpenAICompatibleProvider(
            api_key="ollama",
            base_url=base_url,
            model=model,
        )
    elif name in ("lmstudio", "lm-studio"):
        base_url = settings.llm_base_url or "http://127.0.0.1:1234/v1"
        model = settings.custom_model if (settings.custom_model and settings.custom_model != "default") else "local-model"
        return OpenAICompatibleProvider(
            api_key="lmstudio",
            base_url=base_url,
            model=model,
        )
    elif name in ("custom", "compatible", "groq", "openrouter", "together", "vllm"):
        return OpenAICompatibleProvider()
    elif name == "openai":
        return OpenAIProvider()
    return MockProvider()
