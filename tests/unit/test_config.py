from __future__ import annotations

from pathlib import Path
from recon.common.config import get_project_slug, get_recon_home, settings


def test_get_project_slug():
    # From URL (when cwd is generic)
    generic_cwd = Path("C:/projects")
    assert get_project_slug("http://localhost:8000", cwd=generic_cwd) == "localhost_8000"
    assert get_project_slug("http://localhost:8080/api/v1", cwd=generic_cwd) == "localhost_8080"
    assert get_project_slug("https://api.my-app.com/v1", cwd=generic_cwd) == "api_my-app_com"

    # From Directory Path
    assert get_project_slug(cwd=Path("C:/Users/test/Documents/projects/Groundwork")) == "groundwork"
    assert get_project_slug(cwd=Path("C:/Users/test/Documents/projects/Groundwork/server")) == "groundwork"
    assert get_project_slug(cwd=Path("C:/Users/test/Documents/projects/Groundwork/client/src")) == "groundwork"
    assert get_project_slug(cwd=Path("C:/Users/test/Documents/projects/VeriSpend")) == "verispend"


def test_recon_home_and_settings():
    home = get_recon_home()
    assert home.exists()
    assert home.name == ".recon"
    assert settings.reports_dir == home / "reports"
    assert "recon.db" in settings.database_url
