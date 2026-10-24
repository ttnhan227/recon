from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from recon.agent.master_agent import ReconMasterAgent, extract_url_from_text
from recon.llm.provider import MockProvider


def test_extract_url_from_text():
    assert extract_url_from_text("check http://localhost:8000 now") == "http://localhost:8000"
    assert extract_url_from_text("navigate to https://vnexpress.net/thoi-su please") == "https://vnexpress.net/thoi-su"
    assert extract_url_from_text("is localhost:3000 running?") == "http://localhost:3000"
    assert extract_url_from_text("no url here at all") is None


def test_parse_llm_tool_choice():
    agent = ReconMasterAgent(provider=MockProvider())

    valid_json = json.dumps({"tool": "browser", "url": "http://localhost:3000", "goal": "test checkout"})
    parsed = agent._parse_llm_tool_choice(valid_json)
    assert parsed["tool"] == "browser"

    markdown_json = f"```json\n{valid_json}\n```"
    parsed_md = agent._parse_llm_tool_choice(markdown_json)
    assert parsed_md["tool"] == "browser"

    raw_text = "I don't think any tool is needed."
    parsed_fallback = agent._parse_llm_tool_choice(raw_text)
    assert parsed_fallback["tool"] == "reply"


@pytest.mark.asyncio
async def test_execute_prompt_browser_route():
    mock_provider = MockProvider(mock_responses=[
        json.dumps({"tool": "browser", "url": "http://localhost:3000", "goal": "buy shoes"}),
        json.dumps({"thought": "Finished buying shoes", "action": "finish"}),
    ])
    agent = ReconMasterAgent(provider=mock_provider)

    with patch.object(agent, "_execute_browser", new_callable=AsyncMock) as mock_browser:
        mock_browser.return_value = {
            "status": "PASSED",
            "final_url": "http://localhost:3000/success",
            "summary": "Completed shoes checkout",
            "errors": [],
            "steps_count": 2,
        }

        res = await agent.execute_prompt("Buy shoes on localhost:3000")
        assert "Browser task finished" in res
        assert "Completed shoes checkout" in res
        mock_browser.assert_called_once()


@pytest.mark.asyncio
async def test_execute_prompt_api_route():
    mock_provider = MockProvider(mock_responses=[
        json.dumps({
            "tool": "api_probe",
            "url": "http://localhost:8000",
            "endpoint": "/api/users",
            "method": "GET"
        })
    ])
    agent = ReconMasterAgent(provider=mock_provider)

    with patch.object(agent, "_execute_api_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {
            "status_code": 200,
            "response": [{"id": 1}],
            "success": True,
        }

        res = await agent.execute_prompt("Check if /api/users returns 200 on localhost:8000")
        assert "HTTP 200" in res
        mock_probe.assert_called_once()


def test_ensure_api_key_configured_non_interactive():
    import typer

    from recon.apps.cli.main import ensure_api_key_configured
    with patch.dict("os.environ", {}, clear=True), patch("recon.apps.cli.config_cli.read_env_file", return_value={}):
        with pytest.raises(typer.Exit) as exc_info:
            ensure_api_key_configured(interactive=False)
        assert exc_info.value.exit_code == 1


