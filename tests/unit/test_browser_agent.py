from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from recon.common.models import AgentAction
from recon.execution.browser.agent import ReconBrowserAgent
from recon.llm.provider import MockProvider


def test_agent_action_parsing_valid_json():
    agent = ReconBrowserAgent(provider=MockProvider())
    raw = json.dumps(
        {
            "action": "click",
            "selector": "a[href*='suc-khoe']",
            "thought": "Navigate to the health section on VnExpress",
        }
    )
    action = agent._parse_action(raw)
    assert action.action == "click"
    assert action.selector == "a[href*='suc-khoe']"
    assert "health" in action.thought.lower()


def test_agent_action_parsing_markdown_code_block():
    agent = ReconBrowserAgent(provider=MockProvider())
    raw = """```json
    {
        "action": "fill",
        "selector": "input[name='q']",
        "value": "COVID-19 updates",
        "thought": "Search for health articles"
    }
    ```"""
    action = agent._parse_action(raw)
    assert action.action == "fill"
    assert action.selector == "input[name='q']"
    assert action.value == "COVID-19 updates"


def test_agent_action_parsing_invalid_json_fallback():
    agent = ReconBrowserAgent(provider=MockProvider())
    raw = "I think you should click the button!"
    action = agent._parse_action(raw)
    assert action.action == "finish"
    assert "could not parse" in action.thought.lower()


@pytest.mark.asyncio
async def test_agent_action_execution_click():
    agent = ReconBrowserAgent(provider=MockProvider())
    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.click = AsyncMock()

    action = AgentAction(action="click", selector="button.submit", thought="Submit the form")

    success, err = await agent._execute_action(mock_page, action)
    assert success is True
    assert err is None
    mock_page.wait_for_selector.assert_called_once_with(
        "button.submit", timeout=8000, state="visible"
    )
    mock_page.click.assert_called_once_with("button.submit", timeout=8000)


@pytest.mark.asyncio
async def test_agent_action_execution_fill():
    agent = ReconBrowserAgent(provider=MockProvider())
    mock_page = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.fill = AsyncMock()

    action = AgentAction(
        action="fill", selector="input#username", value="test_user", thought="Enter username"
    )

    success, err = await agent._execute_action(mock_page, action)
    assert success is True
    assert err is None
    mock_page.fill.assert_called_once_with("input#username", "test_user", timeout=8000)


@pytest.mark.asyncio
async def test_agent_action_execution_finish():
    agent = ReconBrowserAgent(provider=MockProvider())
    mock_page = AsyncMock()

    action = AgentAction(action="finish", thought="Goal achieved")

    success, err = await agent._execute_action(mock_page, action)
    assert success is True
    assert err is None


@pytest.mark.asyncio
async def test_agent_action_execution_unknown():
    agent = ReconBrowserAgent(provider=MockProvider())
    mock_page = AsyncMock()

    action = AgentAction(action="fly_to_moon", thought="Impossible action")

    success, err = await agent._execute_action(mock_page, action)
    assert success is False
    assert err is not None and "Unknown action" in err
