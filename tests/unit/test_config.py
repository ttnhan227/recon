from __future__ import annotations

from pathlib import Path

from recon.common.config import get_project_slug, get_recon_home, settings


def test_get_project_slug():
    # From URL (when cwd is generic)
    generic_cwd = Path("projects")
    assert get_project_slug("http://localhost:8000", cwd=generic_cwd) == "localhost_8000"
    assert get_project_slug("http://localhost:8080/api/v1", cwd=generic_cwd) == "localhost_8080"
    assert get_project_slug("https://api.my-app.com/v1", cwd=generic_cwd) == "api_my-app_com"

    # From Directory Path
    assert get_project_slug(cwd=Path("Groundwork")) == "groundwork"
    assert get_project_slug(cwd=Path("Groundwork/server")) == "groundwork"
    assert get_project_slug(cwd=Path("Groundwork/client/src")) == "groundwork"
    assert get_project_slug(cwd=Path("VeriSpend")) == "verispend"


def test_recon_home_and_settings():
    home = get_recon_home()
    assert home.exists()
    assert home.name == ".recon"
    assert settings.reports_dir == home / "reports"
    assert "recon.db" in settings.database_url


def test_api_key_connection_verification_mock():
    from recon.apps.cli.config_cli import test_api_key_connection
    is_valid, msg = test_api_key_connection("mock", "dummy_key")
    assert is_valid is True


def test_api_key_connection_verification_failure():
    from unittest.mock import patch

    from recon.apps.cli.config_cli import test_api_key_connection

    with patch("recon.llm.provider.OpenAIProvider.complete", side_effect=Exception("401 Unauthorized: Invalid API key")):
        is_valid, msg = test_api_key_connection("openai", "sk-invalid-key")
        assert is_valid is False
        assert "401" in msg


def test_set_model_command():
    from unittest.mock import patch

    from recon.apps.cli.config_cli import set_model_command

    with patch("recon.apps.cli.config_cli.update_env_file") as mock_update:
        set_model_command(model="gemini-4-argon", provider="gemini", local=True)
        mock_update.assert_called_once_with({"RECON_GEMINI_MODEL": "gemini-4-argon"}, is_local=True)


def test_api_key_connection_verification_deepseek():
    from unittest.mock import AsyncMock, patch

    from recon.apps.cli.config_cli import test_api_key_connection

    with patch("recon.llm.provider.OpenAICompatibleProvider.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "ok"
        is_valid, msg = test_api_key_connection("deepseek", "sk-test-deepseek")
        assert is_valid is True
        assert "verified successfully" in msg



