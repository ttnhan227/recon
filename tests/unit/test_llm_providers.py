import pytest
import httpx
from recon.llm.provider import (
    GeminiProvider,
    OpenAIProvider,
    AnthropicProvider,
    MistralProvider,
    OpenAICompatibleProvider,
    MockProvider,
    get_llm_provider,
)
from recon.common.exceptions import LLMProviderError


@pytest.mark.asyncio
async def test_gemini_provider_zero_sdk(monkeypatch):
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

    async def mock_post(url, headers, json):
        assert "generativelanguage.googleapis.com" in url
        assert headers["x-goog-api-key"] == "test-key"
        assert json["contents"][0]["parts"][0]["text"] == "Hello Gemini"
        assert json["systemInstruction"]["parts"][0]["text"] == "Be concise"

        response = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Hello from zero-SDK Gemini!"}]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", lambda self, url, **kwargs: mock_post(url, kwargs.get("headers"), kwargs.get("json")))

    result = await provider.complete(prompt="Hello Gemini", system_prompt="Be concise")
    assert result == "Hello from zero-SDK Gemini!"


@pytest.mark.asyncio
async def test_openai_provider_zero_sdk(monkeypatch):
    provider = OpenAIProvider(api_key="sk-test-key", model="gpt-4o-mini")

    async def mock_post(url, headers, json):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer sk-test-key"
        assert json["model"] == "gpt-4o-mini"
        assert json["messages"][0]["role"] == "system"
        assert json["messages"][1]["role"] == "user"

        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {"message": {"content": "Hello from zero-SDK OpenAI!"}}
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", lambda self, url, **kwargs: mock_post(url, kwargs.get("headers"), kwargs.get("json")))

    result = await provider.complete(prompt="Hello OpenAI", system_prompt="System instructions")
    assert result == "Hello from zero-SDK OpenAI!"


@pytest.mark.asyncio
async def test_anthropic_provider_zero_sdk(monkeypatch):
    provider = AnthropicProvider(api_key="sk-ant-test-key", model="claude-3-5-sonnet-20241022")

    async def mock_post(url, headers, json):
        assert url == "https://api.anthropic.com/v1/messages"
        assert headers["x-api-key"] == "sk-ant-test-key"
        assert json["system"] == "System text"

        return httpx.Response(
            status_code=200,
            json={"content": [{"text": "Hello from Anthropic!"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", lambda self, url, **kwargs: mock_post(url, kwargs.get("headers"), kwargs.get("json")))

    result = await provider.complete(prompt="Hi Claude", system_prompt="System text")
    assert result == "Hello from Anthropic!"


@pytest.mark.asyncio
async def test_missing_api_key_raises():
    gemini = GeminiProvider(api_key="")
    with pytest.raises(LLMProviderError):
        await gemini.complete("test")

    openai = OpenAIProvider(api_key="")
    with pytest.raises(LLMProviderError):
        await openai.complete("test")


@pytest.mark.asyncio
async def test_mock_provider():
    mock = MockProvider()
    resp = await mock.complete("generate exploratory test cases for /api/users")
    assert "test_cases" in resp
